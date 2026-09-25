"""
Comprovante repetido de um pedido que já estava pago.

Bug em produção (set/2026): o orquestrador trava o pedido em 13 ("Comprovante em análise") ao chegar uma
imagem; o fluxo via `ja_pago`, saía com `return` e NÃO devolvia o estado. O pedido ficava pago (valor e
data_pagamento) mas preso em 13: fora da contagem de estado 0 e da exportação de conversões ao Google Ads.
~11 pedidos por dia, todos com 2 comprovantes recebidos (o segundo depois do pagamento).
"""
import pytest

from fluxos import fluxo_comprovante_dinamico as fluxo


def _mensagem(tipo='image'):
    corpo = {'type': tipo, 'id': 'wamid.X', tipo: {'url': 'http://gw/media/1', 'mime_type': 'image/jpeg'}}
    return {'entry': [{'changes': [{'value': {'messages': [corpo]}}]}]}


@pytest.fixture
def ambiente(monkeypatch):
    estados, acoes_executadas, pagamentos = [], [], []
    monkeypatch.setattr(fluxo, 'receber_comprovante', lambda *a, **k: '/storage/comprovantes/x.jpg')
    monkeypatch.setattr(fluxo, 'atualizar_pedido_com_comprovante', lambda *a, **k: None)
    monkeypatch.setattr(fluxo, 'salvar_mensagem_pedido', lambda *a, **k: None)
    monkeypatch.setattr(fluxo, 'get_produto_by_id', lambda _id: {'preco': 10})
    # raising=False: no código antigo o fluxo nem importa esta função; o teste deve FALHAR na afirmação (bug), não quebrar aqui
    monkeypatch.setattr(fluxo, 'atualizar_estado_pedido', lambda pid, est: estados.append((pid, est)), raising=False)
    monkeypatch.setattr(fluxo, 'atualizar_pedido_com_pagamento', lambda *a, **k: pagamentos.append(a))
    monkeypatch.setattr(fluxo, 'executar_acao', lambda *a, **k: acoes_executadas.append(a))
    monkeypatch.setattr(fluxo, 'validar_comprovante_com_ia',
                        lambda _p: (_ for _ in ()).throw(AssertionError('não deve validar de novo')))
    return estados, acoes_executadas, pagamentos


def test_comprovante_repetido_de_pedido_pago_devolve_estado_0(ambiente):
    """O caso dos 4 pedidos (352205, 352759, 354244, 354438): pago (estado 0), chegou outra imagem."""
    estados, acoes, pagamentos = ambiente
    pedido = {'id': 352205, 'produto_id': 11, 'estado_id': 0, 'valor_pago': 10.0}
    fluxo.executar(pedido, _mensagem())
    assert estados == [(352205, 0)]      # sai do 13 e volta a pago
    assert acoes == [] and pagamentos == []  # continua sem reenviar bônus/mensagens nem gravar pagamento de novo


def test_comprovante_repetido_devolve_o_estado_que_o_pedido_tinha_nao_forca_zero(ambiente):
    """Se o pedido pago estava em outro estado (ex.: 4), volta para ele: forçar 0 desfaria esse estado."""
    estados, _, _ = ambiente
    fluxo.executar({'id': 9, 'produto_id': 11, 'estado_id': 4, 'valor_pago': 10.0}, _mensagem())
    assert estados == [(9, 4)]


@pytest.mark.parametrize('anterior', [None, 13])
def test_estado_anterior_ausente_ou_13_cai_em_0_porque_o_pedido_ja_esta_pago(ambiente, anterior):
    estados, _, _ = ambiente
    fluxo.executar({'id': 9, 'produto_id': 11, 'estado_id': anterior, 'valor_pago': 10.0}, _mensagem())
    assert estados == [(9, 0)]


def test_midia_nao_suportada_tambem_devolve_o_estado(ambiente):
    estados, acoes, _ = ambiente
    msg = {'entry': [{'changes': [{'value': {'messages': [{'type': 'video', 'id': 'w'}]}}]}]}
    fluxo.executar({'id': 5, 'produto_id': 11, 'estado_id': 3, 'valor_pago': 0.0}, msg)
    assert estados == [(5, 3)]
    assert acoes == []


def test_primeiro_comprovante_segue_o_caminho_normal_sem_devolver_estado_antigo(ambiente, monkeypatch):
    """Regressão: pedido NÃO pago valida e paga normalmente; não pode ser 'devolvido' ao estado anterior."""
    estados, acoes, pagamentos = ambiente
    monkeypatch.setattr(fluxo, 'validar_comprovante_com_ia', lambda _p: '{"valor": 10, "nome_banco": "X"}')
    monkeypatch.setattr(fluxo, 'listar_acoes_fluxo', lambda *a, **k: [
        {'ordem': 1, 'acao': 'enviar_mensagem', 'condicao': 'pagamento_valido'}])
    monkeypatch.setattr(fluxo, 'filtrar_e_ordenar', lambda a, c: a)
    monkeypatch.setattr(fluxo, 'selecionar_variantes', lambda a: a)
    monkeypatch.setattr(fluxo, 'criar_notificacao_admin', lambda *a, **k: None)
    fluxo.executar({'id': 7, 'produto_id': 11, 'estado_id': 3, 'valor_pago': 0.0,
                    'data_contato_site': None}, _mensagem())
    assert len(pagamentos) == 1     # gravou o pagamento (é ele que leva o pedido a estado 0)
    assert len(acoes) == 1          # e enviou as mensagens de confirmação
    assert estados == []            # e NÃO restaurou o estado antigo por cima
