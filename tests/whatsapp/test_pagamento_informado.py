"""
"Já paguei" por texto vale como comprovante (decisão de nov/2026: não pedir comprovante ao público 35+).
O fluxo reaproveita a confirmação do comprovante (grava pagamento e executa as ações do fluxo 'comprovante').
A trava → 13 é feita aqui (não no responder), depois da espera: a imagem do comprovante, se vier, tem prioridade.
"""
import pytest

from fluxos import fluxo_comprovante_dinamico as fluxo


@pytest.fixture
def ambiente(monkeypatch):
    estado = {'banco': {'valor_pago': 0, 'estado_id': 3}, 'estados': [], 'acoes': [], 'pagamentos': [],
              'travas': [], 'trava_ok': True}
    monkeypatch.setattr(fluxo, 'get_pedido', lambda _id: estado['banco'])
    monkeypatch.setattr(fluxo, 'get_produto_by_id', lambda _id: {'preco': 10})

    def travar(pid, estado_atual, estado_travado):
        estado['travas'].append((pid, estado_atual, estado_travado))
        return estado['trava_ok']
    monkeypatch.setattr(fluxo, 'tentar_travar_fluxo', travar)
    monkeypatch.setattr(fluxo, 'atualizar_estado_pedido', lambda pid, est: estado['estados'].append((pid, est)))
    monkeypatch.setattr(fluxo, 'atualizar_pedido_com_pagamento',
                        lambda pid, **k: estado['pagamentos'].append((pid, k['valor_pago'])))
    monkeypatch.setattr(fluxo, 'listar_acoes_fluxo', lambda *a, **k: [
        {'ordem': 1, 'acao': 'enviar_mensagem', 'condicao': 'pagamento_valido'}])
    monkeypatch.setattr(fluxo, 'filtrar_e_ordenar', lambda a, c: a)
    monkeypatch.setattr(fluxo, 'selecionar_variantes', lambda a: a)
    monkeypatch.setattr(fluxo, 'executar_acao', lambda *a, **k: estado['acoes'].append(a))
    monkeypatch.setattr(fluxo, 'criar_notificacao_admin', lambda *a, **k: None)
    return estado


PEDIDO = {'id': 7, 'produto_id': 11, 'estado_id': 3}


def test_trava_grava_valor_citado_e_executa_acoes(ambiente):
    fluxo.executar_pagamento_informado(PEDIDO, 'wamid.C', 20)
    assert ambiente['travas'] == [(7, 3, 13)]
    assert ambiente['pagamentos'] == [(7, 20.0)]
    assert len(ambiente['acoes']) == 1
    assert ambiente['estados'] == []


def test_usa_o_estado_relido_no_banco(ambiente):
    ambiente['banco'] = {'valor_pago': 0, 'estado_id': 4}
    fluxo.executar_pagamento_informado(PEDIDO, 'wamid.C', None)
    assert ambiente['travas'] == [(7, 4, 13)]


@pytest.mark.parametrize('valor', [None, 0, 'x', 1990, 51])
def test_sem_valor_usa_o_preco_do_produto(ambiente, valor):
    fluxo.executar_pagamento_informado(PEDIDO, 'wamid.C', valor)
    assert ambiente['pagamentos'] == [(7, 10.0)]


@pytest.mark.parametrize('banco', [
    {'valor_pago': 10, 'estado_id': 0},     # comprovante por imagem chegou na espera e pagou
    {'valor_pago': 0, 'estado_id': 13},     # comprovante por imagem em análise
    {'valor_pago': 0, 'estado_id': 1008},   # pedido do site (contribuição)
])
def test_nao_trava_nem_mexe_no_estado_quando_nao_esta_aguardando_pagamento(ambiente, banco):
    ambiente['banco'] = banco
    fluxo.executar_pagamento_informado(PEDIDO, 'wamid.C', 20)
    assert ambiente['travas'] == [] and ambiente['estados'] == []
    assert ambiente['pagamentos'] == [] and ambiente['acoes'] == []


def test_valor_ate_5x_o_preco_e_aceito(ambiente):
    """Contribuição maior que o preço é comum (R$ 20, 30, 50 num livro de R$ 10); acima de 5x é erro de leitura
    ("fiz o pix de 1990") e iria direto para Financeiro e ROI."""
    fluxo.executar_pagamento_informado(PEDIDO, 'wamid.C', 50)
    assert ambiente['pagamentos'] == [(7, 50.0)]


def test_trava_falhou_nao_paga(ambiente):
    ambiente['trava_ok'] = False
    fluxo.executar_pagamento_informado(PEDIDO, 'wamid.C', 20)
    assert ambiente['pagamentos'] == [] and ambiente['estados'] == []


def test_estado_mudou_entre_leitura_e_trava_tenta_de_novo(ambiente, monkeypatch):
    """Follow-up moveu 3 → 4 nos 30 s de espera: relê e trava a partir do 4, sem perder o pagamento."""
    leituras = iter([{'valor_pago': 0, 'estado_id': 3}, {'valor_pago': 0, 'estado_id': 4}])
    monkeypatch.setattr(fluxo, 'get_pedido', lambda _id: next(leituras))
    travas = []

    def travar(pid, estado_atual, estado_travado):
        travas.append(estado_atual)
        return estado_atual == 4
    monkeypatch.setattr(fluxo, 'tentar_travar_fluxo', travar)
    fluxo.executar_pagamento_informado(PEDIDO, 'wamid.C', 20)
    assert travas == [3, 4]
    assert ambiente['pagamentos'] == [(7, 20.0)]


def test_erro_antes_de_pagar_volta_ao_estado_anterior(ambiente, monkeypatch):
    ambiente['banco'] = {'valor_pago': 0, 'estado_id': 4}
    monkeypatch.setattr(fluxo, 'get_produto_by_id', lambda _id: (_ for _ in ()).throw(RuntimeError('db')))
    with pytest.raises(RuntimeError):
        fluxo.executar_pagamento_informado(PEDIDO, 'wamid.C', 20)
    assert ambiente['estados'] == [(7, 4)]   # não força 3: preserva o ponto do follow-up


def test_erro_depois_de_pagar_fica_pago(ambiente, monkeypatch):
    def acao_falha(*_a, **_k):
        ambiente['banco'] = {'valor_pago': 20, 'estado_id': 0}  # o pagamento já foi gravado
        raise RuntimeError('chip fora do ar')
    monkeypatch.setattr(fluxo, 'executar_acao', acao_falha)
    with pytest.raises(RuntimeError):
        fluxo.executar_pagamento_informado(PEDIDO, 'wamid.C', 20)
    assert ambiente['estados'] == [(7, 0)]


@pytest.mark.parametrize('banco,anterior,esperado', [
    ({'valor_pago': 10}, 4, 0),     # pago antes do erro: fica pago
    ({'valor_pago': 0}, 4, 4),      # não pago: volta ao estado anterior (preserva o follow-up)
    ({'valor_pago': 0}, None, 3),   # sem estado anterior conhecido: 3
    ({'valor_pago': 0}, 13, 3),
])
def test_destravar_apos_erro(ambiente, banco, anterior, esperado):
    """Antes a task do comprovante sempre voltava para 3: um erro no envio do bônus tirava o pedido pago do ROI e
    um pedido no 4 recebia a cobrança de novo."""
    ambiente['banco'] = banco
    fluxo.destravar_apos_erro(7, anterior)
    assert ambiente['estados'] == [(7, esperado)]


def test_destravar_com_banco_fora_volta_ao_estado_anterior(ambiente, monkeypatch):
    """O erro pode ser o próprio banco: a releitura não pode impedir de sair do 13."""
    monkeypatch.setattr(fluxo, 'get_pedido', lambda _id: (_ for _ in ()).throw(RuntimeError('mysql')))
    fluxo.destravar_apos_erro(7, 4)
    assert ambiente['estados'] == [(7, 4)]
