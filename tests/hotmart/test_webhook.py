"""Webhook da Hotmart: hottok, pedido pago (uma entrega só), OXXO à espera, cancelado, oferta errada, órfão, câmbio."""
import datetime
from decimal import Decimal

from tests.hotmart.conftest import HOTTOK, aviso


def _post(cliente, corpo, hottok=HOTTOK):
    cabecalhos = {'X-HOTMART-HOTTOK': hottok} if hottok is not None else {}
    return cliente.post('/hotmart/webhook', json=corpo, headers=cabecalhos)


# ── segurança ──────────────────────────────────────────────────────────────────────────────────────────────────────

def test_sem_hottok_ou_errado_recusa_e_nao_grava(cliente, repo):
    assert _post(cliente, aviso(), hottok=None).status_code == 401
    assert _post(cliente, aviso(), hottok='outro').status_code == 401
    assert repo.eventos == {} and repo.pedidos[7]['estado_id'] == 1001


def test_sem_hottok_configurado_webhook_desligado(cliente, repo, monkeypatch):
    from hotmart import config
    monkeypatch.setattr(config, 'HOTTOK', '')
    assert _post(cliente, aviso(), hottok='').status_code == 404


def test_corpo_que_nao_e_json_400(cliente):
    resp = cliente.post('/hotmart/webhook', data='x', headers={'X-HOTMART-HOTTOK': HOTTOK})
    assert resp.status_code == 400


# ── pago ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_aprovado_confirma_em_reais_e_entrega_uma_vez(cliente, repo):
    resp = _post(cliente, aviso())
    assert resp.status_code == 200 and resp.get_json()['resultado'] == 'ok'
    pedido = repo.pedidos[7]
    assert pedido['estado_id'] == 1000 and pedido['metodo_pagamento'] == 'hotmart'
    assert pedido['valor_pago'] == Decimal('179.70')            # 599 MXN × PTAX 0,30
    assert pedido['valor_liquido_pagamento'] == Decimal('156.00')
    assert pedido['nome_pagador'] == 'María López'
    assert pedido['data_repasse'] == datetime.date(2025, 12, 5)  # aprovação (20/11/2025) + 15 dias
    assert repo.entregas == [7]
    pag = repo.pagamentos['HP111']
    assert (pag['valor'], pag['moeda'], pag['fonte_taxa'], pag['pais']) == (Decimal('599.0'), 'MXN', 'ptax', 'MX')
    assert pag['taxa_hotmart'] == Decimal('79.0') and pag['pedido_id'] == 7


def test_aviso_repetido_e_complete_nao_entregam_de_novo(cliente, repo):
    _post(cliente, aviso())
    assert _post(cliente, aviso()).get_json()['resultado'] == 'repetido'
    assert _post(cliente, aviso(evento='PURCHASE_COMPLETE', id_='evt-2', status='COMPLETE')).status_code == 200
    assert repo.entregas == [7]
    assert repo.pagamentos['HP111']['liberado_em'] == 'agora'


def test_oferta_de_outro_plano_nao_confirma(cliente, repo):
    assert _post(cliente, aviso(oferta='OFVIDEO')).get_json()['resultado'] == 'oferta_divergente'
    assert repo.pedidos[7]['estado_id'] == 1001 and repo.entregas == []
    assert repo.pagamentos['HP111']['pedido_id'] == 7            # a compra fica gravada para conferir


def test_oferta_nao_cadastrada_nao_confirma(cliente, repo):
    assert _post(cliente, aviso(oferta='NAOEXISTE')).get_json()['resultado'] == 'oferta_divergente'
    assert repo.entregas == []


# ── OXXO/SPEI, cancelado, devolução ────────────────────────────────────────────────────────────────────────────────

def test_oxxo_gerado_espera_e_depois_paga(cliente, repo):
    _post(cliente, aviso(evento='PURCHASE_BILLET_PRINTED', id_='e1', status='PRINTED_BILLET', tipo='CASH_PAYMENT',
                         aprovado_ms=None))
    assert repo.pedidos[7]['estado_id'] == 1010 and repo.entregas == []
    assert repo.pagamentos['HP111']['previsao_repasse'] is None
    _post(cliente, aviso(id_='e2', tipo='CASH_PAYMENT'))
    assert repo.pedidos[7]['estado_id'] == 1000 and repo.entregas == [7]


def test_espera_reconhecida_pelo_status_em_outro_evento(cliente, repo):
    _post(cliente, aviso(evento='PURCHASE_OUTRO', status='WAITING_PAYMENT', aprovado_ms=None))
    assert repo.pedidos[7]['estado_id'] == 1010


def test_expirado_cancela_mas_nunca_um_pedido_pago(cliente, repo):
    _post(cliente, aviso(evento='PURCHASE_EXPIRED', id_='e1', status='EXPIRED', aprovado_ms=None))
    assert repo.pedidos[7]['estado_id'] == 1011
    _post(cliente, aviso(id_='e2'))
    _post(cliente, aviso(evento='PURCHASE_CANCELED', id_='e3', status='CANCELLED', aprovado_ms=None))
    assert repo.pedidos[7]['estado_id'] == 1000
    assert repo.pagamentos['HP111']['aprovado_em'] is not None  # o aviso sem data não apaga a aprovação


def test_reembolso_so_registra(cliente, repo):
    _post(cliente, aviso(id_='e1'))
    _post(cliente, aviso(evento='PURCHASE_REFUNDED', id_='e2', status='REFUNDED'))
    assert repo.pedidos[7]['estado_id'] == 1000
    assert repo.pagamentos['HP111']['status'] == 'REFUNDED'


# ── sem pedido, order bump, erro ───────────────────────────────────────────────────────────────────────────────────

def test_sem_xcod_grava_orfao_e_responde_200(cliente, repo):
    resp = _post(cliente, aviso(xcod=None))
    assert resp.status_code == 200 and resp.get_json()['resultado'] == 'sem_pedido'
    assert repo.pagamentos['HP111']['pedido_id'] is None and repo.entregas == []


def test_order_bump_ignorado(cliente, repo):
    assert _post(cliente, aviso(order_bump=True)).get_json()['resultado'] == 'ignorado'
    assert repo.pedidos[7]['estado_id'] == 1001


def test_compra_principal_de_checkout_com_bump_e_processada(cliente, repo):
    """Doc oficial: a principal vem com is_order_bump = true e parent_purchase_transaction vazio."""
    corpo = aviso()
    corpo['data']['purchase']['order_bump'] = {'is_order_bump': True, 'parent_purchase_transaction': ''}
    corpo['data']['purchase'].update(invoice_by='HOTMART', business_model='R')
    assert _post(cliente, corpo).get_json()['resultado'] == 'ok'
    assert repo.pedidos[7]['estado_id'] == 1000
    pag = repo.pagamentos['HP111']
    assert (pag['order_bump'], pag['nota_fiscal_por'], pag['modelo_fiscal']) == (0, 'HOTMART', 'R')


def test_sem_comissao_da_hotmart_no_aviso(cliente, repo):
    """A doc lista só PRODUCER/COPRODUCER/AFFILIATE/ADDON: a taxa da Hotmart pode não vir."""
    corpo = aviso()
    corpo['data']['commissions'] = [c for c in corpo['data']['commissions'] if c['source'] == 'PRODUCER']
    assert _post(cliente, corpo).get_json()['resultado'] == 'ok'
    assert repo.pagamentos['HP111']['taxa_hotmart'] is None and repo.pedidos[7]['estado_id'] == 1000


def test_erro_responde_500_e_reenvio_processa(cliente, repo, monkeypatch):
    from hotmart import repositorio
    original = repositorio.confirmar_pedido
    monkeypatch.setattr(repositorio, 'confirmar_pedido', lambda *a: (_ for _ in ()).throw(RuntimeError('banco')))
    assert _post(cliente, aviso()).status_code == 500
    assert repo.eventos['evt-1']['resultado'] == 'erro'
    monkeypatch.setattr(repositorio, 'confirmar_pedido', original)
    assert _post(cliente, aviso()).get_json()['resultado'] == 'ok'
    assert repo.entregas == [7]


# ── câmbio ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_venda_em_reais_nao_converte(cliente, repo):
    _post(cliente, aviso(valor=49.9, moeda='BRL', liquido=43.0, moeda_liquido='BRL'))
    assert repo.pedidos[7]['valor_pago'] == Decimal('49.90')
    assert repo.pagamentos['HP111']['fonte_taxa'] == 'brl'


def test_conversao_da_hotmart_vale_mais_que_ptax(cliente, repo):
    conversao = {'converted_value': 145.6, 'converted_to_currency': 'BRL', 'conversion_rate': 0.28}
    _post(cliente, aviso(conversao=conversao))
    pag = repo.pagamentos['HP111']
    assert pag['fonte_taxa'] == 'hotmart' and pag['taxa_brl'] == Decimal('0.280000')
    assert pag['liquido_brl'] == Decimal('145.60') and repo.pedidos[7]['valor_pago'] == Decimal('167.72')


def test_liquido_em_dolar_convertido_pela_ptax_do_dolar(cliente, repo):
    repo.cotacoes['USD'] = {'valor': 5.0}
    _post(cliente, aviso(liquido=28.0, moeda_liquido='USD'))
    assert repo.pagamentos['HP111']['liquido_brl'] == Decimal('140.00')


def test_sem_ptax_usa_ultima_taxa_e_sem_nada_fica_pendente_mas_entrega(cliente, repo):
    repo.cotacoes.clear()
    repo.taxas['MXN'] = Decimal('0.29')
    _post(cliente, aviso())
    assert repo.pagamentos['HP111']['fonte_taxa'] == 'ultima' and repo.pedidos[7]['valor_pago'] == Decimal('173.71')

    repo.pedidos[8] = {'id': 8, 'guid': 'def456', 'produto_id': 50, 'plano_id': 501, 'estado_id': 1001,
                       'valor_pago': 29.9, 'fluxo_inicial': 'web'}
    repo.taxas.clear()
    _post(cliente, aviso(id_='evt-9', transacao='HP222', xcod='def456'))
    assert repo.pagamentos['HP222']['fonte_taxa'] == 'pendente'
    assert repo.pedidos[8]['estado_id'] == 1000 and repo.entregas == [7, 8]   # a entrega nunca espera o câmbio
    assert repo.pedidos[8]['valor_pago'] == 29.9                              # mantém o esperado, não zera

    repo.cotacoes['MXN'] = {'valor': 0.31}                                     # o COMPLETE chega com cotação
    _post(cliente, aviso(evento='PURCHASE_COMPLETE', id_='evt-10', transacao='HP222', xcod='def456', status='COMPLETE'))
    assert repo.pedidos[8]['valor_pago'] == Decimal('185.69') and repo.entregas == [7, 8]
    assert repo.pagamentos['HP222']['fonte_taxa'] == 'ptax'


# ── proteções da revisão ───────────────────────────────────────────────────────────────────────────────────────────

def test_pedido_sem_plano_nao_aceita_oferta_nenhuma(cliente, repo):
    repo.pedidos[7]['plano_id'] = None
    assert _post(cliente, aviso()).get_json()['resultado'] == 'oferta_divergente'
    assert repo.pedidos[7]['estado_id'] == 1001


def test_cancelamento_de_outro_produto_nao_mexe_no_pedido(cliente, repo):
    repo.ofertas['OUTRO'] = {'codigo': 'OUTRO', 'produto_id': 99, 'plano_id': 990, 'ativo': 1}
    resp = _post(cliente, aviso(evento='PURCHASE_EXPIRED', oferta='OUTRO', status='EXPIRED', aprovado_ms=None))
    assert resp.get_json()['resultado'] == 'oferta_divergente' and repo.pedidos[7]['estado_id'] == 1001


def test_espera_e_cancelamento_nunca_mexem_em_pedido_de_outro_fluxo(cliente, repo):
    repo.pedidos[7].update(estado_id=1009)                                   # contribuição: livro entregue
    _post(cliente, aviso(evento='PURCHASE_EXPIRED', id_='e1', status='EXPIRED', aprovado_ms=None))
    assert repo.pedidos[7]['estado_id'] == 1009
    repo.pedidos[7].update(estado_id=3, fluxo_inicial='whatsapp')            # WhatsApp aguardando pagamento
    _post(cliente, aviso(evento='PURCHASE_BILLET_PRINTED', id_='e2', status='PRINTED_BILLET', aprovado_ms=None))
    assert repo.pedidos[7]['estado_id'] == 3


def test_aviso_sem_preco_nao_apaga_a_cotacao(cliente, repo):
    _post(cliente, aviso(id_='e1'))
    sem_preco = aviso(evento='PURCHASE_REFUNDED', id_='e2', status='REFUNDED')
    del sem_preco['data']['purchase']['price']
    _post(cliente, sem_preco)
    pag = repo.pagamentos['HP111']
    assert (pag['fonte_taxa'], pag['taxa_brl']) == ('ptax', Decimal('0.300000'))


def test_aviso_sem_id_usa_o_conteudo_como_chave(cliente, repo):
    a, b = aviso(), aviso(transacao='HP999', xcod=None)
    del a['id'], b['id']
    assert _post(cliente, a).get_json()['resultado'] == 'ok'
    assert _post(cliente, b).get_json()['resultado'] == 'sem_pedido'       # outro aviso: não é "repetido"
    assert _post(cliente, a).get_json()['resultado'] == 'repetido'


def test_previsao_usa_a_garantia_quando_mais_tarde():
    from hotmart.servico import previsao_repasse
    aprovado = datetime.datetime(2026, 11, 1, 10)
    assert previsao_repasse(aprovado, None) == datetime.date(2026, 11, 16)
    assert previsao_repasse(aprovado, datetime.datetime(2026, 12, 1)) == datetime.date(2026, 12, 1)
    assert previsao_repasse(None, None) is None
