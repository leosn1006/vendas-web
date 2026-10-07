"""
Ritmo dos followups nos chips do gateway: no máximo N pedidos por chip em cada rodada, os mais antigos
primeiro, contando só os que de fato enviaram alguma ação.
"""
import pytest

from fluxos import _ritmo_wpp_web as ritmo_wpp_web
from fluxos import fluxo_followup_interesse_dinamico as followup_int

_PROVEDORES = {'web1': 'wpp_web', 'web2': 'wpp_web', 'meta1': 'meta'}


@pytest.fixture(autouse=True)
def provedores(monkeypatch):
    monkeypatch.setattr(ritmo_wpp_web, 'get_provedor_numero', lambda pid: _PROVEDORES.get(pid, 'meta'))


def _pedidos(chip, ids, produto_id=1):
    return [{'id': i, 'produto_id': produto_id, 'phone_number_id': chip} for i in ids]


def _rodar(ritmo, pedidos):
    """Simula a rodada: quem passa pelo ritmo envia e é registrado."""
    enviados = []
    for pedido in ritmo.ordenar(pedidos):
        if ritmo.pode_enviar(pedido):
            ritmo.registrar_envio(pedido)
            enviados.append(pedido['id'])
    return enviados


def test_limite_por_chip_libera_os_mais_antigos():
    """A rodada das 7h soltava o acumulado da noite de uma vez pelo chip do gateway."""
    pedidos = _pedidos('web1', [30, 10, 20]) + _pedidos('web2', [40])
    assert _rodar(ritmo_wpp_web.RitmoWppWeb(2, 'T'), pedidos) == [10, 20, 40]


def test_meta_nao_tem_limite():
    assert len(_rodar(ritmo_wpp_web.RitmoWppWeb(1, 'T'), _pedidos('meta1', range(1, 11)))) == 10


@pytest.fixture
def interesse_env(monkeypatch):
    """Produto 99 sem ações configuradas; os demais com uma ação."""
    acoes = [{'ordem': 1, 'acao': 'enviar_mensagem', 'condicao': 'sempre'}]
    monkeypatch.setattr(followup_int, 'listar_acoes_fluxo', lambda produto_id, _f: [] if produto_id == 99 else acoes)
    monkeypatch.setattr(followup_int, 'filtrar_e_ordenar', lambda a, c: a)
    monkeypatch.setattr(followup_int, 'selecionar_variantes', lambda a: a)
    enviados, marcados = [], []
    monkeypatch.setattr(followup_int, 'executar_acao', lambda acao, pedido, **k: enviados.append(pedido['id']))
    return enviados, marcados


def test_pedido_que_nunca_envia_nao_ocupa_a_vaga_do_chip(interesse_env):
    """Revisão: com limite 1, um pedido mais antigo sem ações (nunca marcado) travava a fila do chip até sair
    da janela de 22h."""
    enviados, marcados = interesse_env
    pedidos = _pedidos('web1', [1], produto_id=99) + _pedidos('web1', [2, 3])
    followup_int._executar_rodada(pedidos, 'followup_interesse_1', marcados.append)
    assert enviados == [2]       # o 1 não enviou nada e não gastou a vaga; o 3 fica para a próxima rodada
    assert marcados == [2]


def test_pedido_com_erro_nao_ocupa_a_vaga_do_chip(monkeypatch, interesse_env):
    enviados, marcados = interesse_env

    def executa(acao, pedido, **k):
        if pedido['id'] == 1:
            raise RuntimeError('falha')
        enviados.append(pedido['id'])

    monkeypatch.setattr(followup_int, 'executar_acao', executa)
    followup_int._executar_rodada(_pedidos('web1', [1, 2, 3]), 'followup_interesse_1', marcados.append)
    assert enviados == [2]
