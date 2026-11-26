"""Conciliação com a API de vendas: venda que o webhook perdeu (confirma uma vez), tudo batendo, divergências, oferta
errada, erro da API e o reprocessar. Base: a resposta real da venda HP0277856500 (api_venda_real.json)."""
import copy
import datetime
import json
import os
from decimal import Decimal

import pytest

from tests.hotmart.conftest import aviso

with open(os.path.join(os.path.dirname(__file__), 'api_venda_real.json'), encoding='utf-8') as f:
    REAL = json.load(f)


def _venda(**muda_compra):
    venda = {k: copy.deepcopy(REAL[k]) for k in ('history', 'price', 'commissions')}
    venda['history']['purchase'].update(muda_compra)
    return venda


@pytest.fixture
def api_falsa(monkeypatch, repo):
    """api.listar devolvendo as vendas do teste por status; o pedido de teste do conftest vira o 'hmtteste'."""
    from hotmart import api
    vendas = []
    chamadas = []

    def listar(caminho, **filtros):
        chamadas.append((caminho, filtros.get('transaction_status')))
        status = filtros.get('transaction_status')
        chave = {'sales/history': 'history', 'sales/price/details': 'price', 'sales/commissions': 'commissions'}[caminho]
        return [copy.deepcopy(v[chave]) for v in vendas if v['history']['purchase']['status'] == status]

    monkeypatch.setattr(api, 'listar', listar)
    monkeypatch.setattr(api, 'configurada', lambda: True)
    from hotmart import conciliacao
    monkeypatch.setattr(conciliacao, '_pegar_trava', lambda: True)
    monkeypatch.setattr(conciliacao, '_soltar_trava', lambda: None)
    repo.pedidos[7]['guid'] = 'hmtteste'
    repo.ofertas['sph9o75s'] = {'codigo': 'sph9o75s', 'produto_id': 50, 'plano_id': 501, 'ativo': 1}
    repo.cotacoes['USD'] = {'valor': 5.80}
    vendas_ref = vendas
    return type('Api', (), {'vendas': vendas_ref, 'chamadas': chamadas})


def _conciliar():
    from hotmart import conciliacao
    return conciliacao.conciliar(origem='botao', dias=45)


# ── leitura da API ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_resumo_da_api_da_venda_real():
    from hotmart.conciliacao import resumo_api
    r = resumo_api(_venda())
    assert (r['api_status'], r['api_total'], r['api_moeda'], r['api_iva']) == ('APPROVED', Decimal('58'), 'MXN', Decimal('8'))
    assert (r['api_taxa'], r['api_taxa_percentual'], r['api_liquido'], r['api_moeda_liquido']) == (
        Decimal('0.5'), Decimal('20'), Decimal('2.01'), 'USD')
    assert (r['api_xcod'], r['api_oferta']) == ('hmtteste', 'sph9o75s')
    assert r['api_garantia_ate'] == datetime.datetime(2026, 12, 1, 21, 0)   # 02/12 00:00 UTC, no horário de Brasília


def test_aviso_montado_pela_api_e_lido_como_o_webhook():
    from hotmart import leitura
    from hotmart.conciliacao import aviso_da_api
    d = leitura.ler(aviso_da_api(_venda(), 'APPROVED'))
    assert (d['evento'], d['transacao'], d['xcod'], d['oferta']) == ('PURCHASE_APPROVED', 'HP0277856500', 'hmtteste', 'sph9o75s')
    assert (d['valor'], d['moeda'], d['valor_cheio']) == (Decimal('50'), 'MXN', Decimal('58'))   # sem IVA × com IVA
    assert (d['liquido'], d['moeda_liquido'], d['order_bump']) == (Decimal('2.01'), 'USD', False)
    assert d['evento_id'] == 'conciliacao:HP0277856500:APPROVED'


# ── webhook perdido: confirma pela API ─────────────────────────────────────────────────────────────────────────────

def test_venda_paga_que_o_webhook_perdeu_e_confirmada_uma_vez(api_falsa, repo):
    api_falsa.vendas.append(_venda())
    r = _conciliar()
    assert (r['vendas_api'], r['novas'], r['confirmadas'], r['divergentes'], r['erro']) == (1, 1, 1, 0, None)
    pedido = repo.pedidos[7]
    assert pedido['estado_id'] == 1000 and pedido['metodo_pagamento'] == 'hotmart'
    assert pedido['valor_pago'] == Decimal('15.00')                    # 50 MXN × 0,30 (sem IVA)
    assert repo.entregas == [7]
    pag = repo.pagamentos['HP0277856500']
    assert pag['divergencia'] is None and pag['api_iva'] == Decimal('8') and pag['conciliado_em'] == 'agora'
    assert repo.conciliacoes[-1]['confirmadas'] == 1 and repo.conciliacoes[-1]['origem'] == 'botao'

    r = _conciliar()                                                    # a próxima hora: nada muda
    assert (r['novas'], r['confirmadas'], r['divergentes']) == (0, 0, 0) and repo.entregas == [7]


def test_webhook_e_api_batendo_nao_mexe_em_nada(api_falsa, repo, cliente):
    from tests.hotmart.test_webhook import _post
    corpo = aviso(transacao='HP0277856500', xcod='hmtteste', oferta='sph9o75s', valor=50, moeda='MXN',
                  liquido=2.01, moeda_liquido='USD')
    corpo['data']['purchase']['full_price'] = {'value': 58, 'currency_value': 'MXN'}
    _post(cliente, corpo)
    assert repo.entregas == [7]
    api_falsa.vendas.append(_venda())
    r = _conciliar()
    assert (r['novas'], r['confirmadas'], r['divergentes']) == (0, 0, 0)
    assert repo.pagamentos['HP0277856500']['divergencia'] is None and repo.entregas == [7]


def test_oferta_de_outro_plano_nao_e_confirmada_pela_conciliacao(api_falsa, repo):
    api_falsa.vendas.append(_venda(offer={'code': 'OFVIDEO'}))
    r = _conciliar()
    assert r['confirmadas'] == 0 and repo.pedidos[7]['estado_id'] == 1001 and repo.entregas == []
    assert 'não pago' in repo.pagamentos['HP0277856500']['divergencia']
    assert repo.eventos['conciliacao:HP0277856500:APPROVED']['resultado'] == 'oferta_divergente'


def test_venda_sem_pedido_nosso_vira_divergencia(api_falsa, repo):
    api_falsa.vendas.append(_venda(tracking={}))
    r = _conciliar()
    assert r['divergentes'] == 1 and 'sem pedido' in repo.pagamentos['HP0277856500']['divergencia']


# ── divergências ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_reembolso_na_api_sem_o_aviso_vira_divergencia(api_falsa, repo, cliente):
    from tests.hotmart.test_webhook import _post
    _post(cliente, aviso(transacao='HP0277856500', xcod='hmtteste', oferta='sph9o75s'))
    api_falsa.vendas.append(_venda(status='REFUNDED'))
    r = _conciliar()
    assert r['divergentes'] == 1
    assert 'status: API REFUNDED × webhook APPROVED' in repo.pagamentos['HP0277856500']['divergencia']
    assert repo.pedidos[7]['estado_id'] == 1000                         # divergência não muda o pedido


def test_valor_diferente_vira_divergencia(api_falsa, repo, cliente):
    from tests.hotmart.test_webhook import _post
    corpo = aviso(transacao='HP0277856500', xcod='hmtteste', oferta='sph9o75s', valor=50, moeda='MXN',
                  liquido=2.01, moeda_liquido='USD')
    corpo['data']['purchase']['full_price'] = {'value': 60, 'currency_value': 'MXN'}
    _post(cliente, corpo)
    api_falsa.vendas.append(_venda())
    _conciliar()
    assert repo.pagamentos['HP0277856500']['divergencia'] == 'valor: API 58 × webhook 60 MXN'


# ── erros e reprocessar ────────────────────────────────────────────────────────────────────────────────────────────

def test_erro_da_api_fica_na_execucao_sem_excecao(api_falsa, repo, monkeypatch):
    from hotmart import api
    monkeypatch.setattr(api, 'listar', lambda *a, **k: (_ for _ in ()).throw(api.ErroApi('history: HTTP 403')))
    r = _conciliar()
    assert 'HTTP 403' in r['erro'] and repo.conciliacoes[-1]['erro'] == r['erro']


def test_sem_credencial_nao_roda(monkeypatch, repo):
    from hotmart import api
    monkeypatch.setattr(api, 'configurada', lambda: False)
    r = _conciliar()
    assert 'não configurada' in r['erro'] and repo.conciliacoes == []


def test_reprocessar_depois_de_cadastrar_a_oferta(cliente, repo):
    from hotmart import servico
    from tests.hotmart.test_webhook import _post
    assert _post(cliente, aviso(oferta='NOVA')).get_json()['resultado'] == 'oferta_divergente'
    repo.ofertas['NOVA'] = {'codigo': 'NOVA', 'produto_id': 50, 'plano_id': 501, 'ativo': 1}
    assert servico.reprocessar(repo.eventos['evt-1']['id']) == 'ok'
    assert repo.pedidos[7]['estado_id'] == 1000 and repo.entregas == [7]
    assert repo.eventos['evt-1']['resultado'] == 'ok'


def test_busca_todos_os_status_nos_tres_endpoints(api_falsa):
    from hotmart.conciliacao import STATUS_API
    _conciliar()
    assert len(api_falsa.chamadas) == 3 * len(STATUS_API)
    assert {s for _, s in api_falsa.chamadas} == set(STATUS_API)


def test_pago_sem_entrega_ha_mais_de_30_min_recebe_a_entrega_de_novo(api_falsa, repo, monkeypatch):
    from hotmart import repositorio
    repo.pedidos[7]['email'] = 'compradora@exemplo.com'
    api_falsa.vendas.append(_venda())
    _conciliar()
    assert repo.entregas == [7]
    original = repositorio.pagamento_com_pedido
    antigo = datetime.datetime.now() - datetime.timedelta(hours=2)
    monkeypatch.setattr(repositorio, 'pagamento_com_pedido',
                        lambda t: {**original(t), 'pedido_entregue_em': None, 'pedido_pago_em': antigo})
    r = _conciliar()
    assert repo.entregas == [7, 7] and r['reentregas'] == 1
    monkeypatch.setattr(repositorio, 'pagamento_com_pedido',
                        lambda t: {**original(t), 'pedido_entregue_em': antigo, 'pedido_pago_em': antigo})
    _conciliar()
    assert repo.entregas == [7, 7]                                     # já entregue: não agenda de novo


def test_reentrega_so_com_email_e_dentro_de_6_horas(api_falsa, repo, monkeypatch):
    from hotmart import repositorio
    api_falsa.vendas.append(_venda())
    _conciliar()
    original = repositorio.pagamento_com_pedido
    for muda in ({'pedido_email': None, 'pedido_pago_em': datetime.datetime.now() - datetime.timedelta(hours=1)},
                 {'pedido_email': 'a@b.com', 'pedido_pago_em': datetime.datetime.now() - datetime.timedelta(hours=7)},
                 {'pedido_email': 'a@b.com', 'pedido_metodo': 'pix',
                  'pedido_pago_em': datetime.datetime.now() - datetime.timedelta(hours=1)}):
        monkeypatch.setattr(repositorio, 'pagamento_com_pedido',
                            lambda t, m=muda: {**original(t), 'pedido_entregue_em': None, **m})
        assert _conciliar()['reentregas'] == 0
    assert repo.entregas == [7]


def test_cartao_recusado_antigo_nao_cancela_o_pedido_que_espera_o_oxxo(api_falsa, repo):
    recusado = _venda(status='CANCELLED', transaction='HPANTIGO', order_date=1795660000000)
    for parte in ('price', 'commissions'):
        recusado[parte]['transaction'] = 'HPANTIGO'
    oxxo = _venda(status='WAITING_PAYMENT', transaction='HPOXXO', order_date=1795669999000,
                  payment={'type': 'CASH_PAYMENT'})
    for parte in ('price', 'commissions'):
        oxxo[parte]['transaction'] = 'HPOXXO'
    api_falsa.vendas.extend([recusado, oxxo])
    _conciliar()
    assert repo.pedidos[7]['estado_id'] == 1010                         # o OXXO (mais recente) vale
    assert set(repo.pagamentos) == {'HPANTIGO', 'HPOXXO'}               # o antigo só foi registrado
    assert repo.eventos['conciliacao:HPANTIGO:CANCELLED:registro']['resultado'] == 'ok'


def test_order_bump_pago_nao_e_aplicado_como_compra_principal(api_falsa, repo):
    bump = _venda(transaction='HPBUMP', offer={'code': 'BUMP-DESCONHECIDO'})
    for parte in ('price', 'commissions'):
        bump[parte]['transaction'] = 'HPBUMP'
    api_falsa.vendas.extend([bump, _venda()])                            # o bump vem primeiro na lista
    r = _conciliar()
    assert r['confirmadas'] == 1 and repo.pedidos[7]['estado_id'] == 1000 and repo.entregas == [7]
    assert repo.eventos['conciliacao:HPBUMP:APPROVED']['resultado'] == 'ignorado'   # registrado como bump
    bump = repo.pagamentos['HPBUMP']
    assert (bump['order_bump'], bump['transacao_principal']) == (1, 'HP0277856500')
    assert not any(e['resultado'] == 'oferta_divergente' for e in repo.eventos.values())

    repo.ofertas['BUMP-DESCONHECIDO'] = {'codigo': 'BUMP-DESCONHECIDO', 'produto_id': 50, 'plano_id': 501, 'ativo': 1}
    repo.pedidos[7]['estado_id'] = 1010                                  # mesmo que o pedido voltasse a ficar aberto
    _conciliar()
    assert repo.pedidos[7]['estado_id'] == 1010                         # o bump gravado nunca confirma


def test_aviso_do_webhook_ja_para_conferir_nao_ganha_um_segundo(api_falsa, repo, cliente):
    from tests.hotmart.test_webhook import _post
    _post(cliente, aviso(transacao='HP0277856500', xcod='hmtteste', oferta='NAO-CADASTRADA'))
    api_falsa.vendas.append(_venda(offer={'code': 'NAO-CADASTRADA'}))
    _conciliar()
    assert [e['evento_id'] for e in repo.eventos.values()] == ['evt-1']


def test_reprocessar_recusa_aviso_que_nao_esta_para_conferir(cliente, repo):
    from hotmart import servico
    from tests.hotmart.test_webhook import _post
    _post(cliente, aviso())
    with pytest.raises(ValueError, match='não está para conferir'):
        servico.reprocessar(repo.eventos['evt-1']['id'])
    assert repo.entregas == [7]


def test_uma_venda_com_erro_nao_impede_as_outras(api_falsa, repo, monkeypatch):
    from hotmart import repositorio
    ruim = _venda(transaction='HPRUIM', tracking={'external_code': 'outro'})
    for parte in ('price', 'commissions'):
        ruim[parte]['transaction'] = 'HPRUIM'
    api_falsa.vendas.extend([ruim, _venda()])
    original = repositorio.salvar_conciliacao

    def falha_no_ruim(transacao, campos, divergencia):
        if transacao == 'HPRUIM':
            raise RuntimeError('Data too long')
        return original(transacao, campos, divergencia)

    monkeypatch.setattr(repositorio, 'salvar_conciliacao', falha_no_ruim)
    r = _conciliar()
    assert r['erro'] is None and r['confirmadas'] == 1 and repo.pedidos[7]['estado_id'] == 1000


def test_campos_da_api_cortados_no_tamanho_das_colunas():
    from hotmart.conciliacao import resumo_api
    r = resumo_api(_venda(tracking={'external_code': 'x' * 100}, offer={'code': 'o' * 60}, status='S' * 40))
    assert (len(r['api_xcod']), len(r['api_oferta']), len(r['api_status'])) == (64, 40, 30)


def test_segunda_conciliacao_ao_mesmo_tempo_nao_roda(api_falsa, repo, monkeypatch):
    from hotmart import conciliacao
    monkeypatch.setattr(conciliacao, '_pegar_trava', lambda: False)
    api_falsa.vendas.append(_venda())
    r = _conciliar()
    assert r['erro'] == 'outra conciliação já está rodando' and repo.conciliacoes == [] and repo.entregas == []
