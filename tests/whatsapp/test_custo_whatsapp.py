"""
Custo das mensagens da Meta (pricing_analytics → whatsapp_custo_diario): agregação por número/categoria,
coleta só de números Meta, produto_id preservado no upsert e conversão para Real só na tela.
"""
import datetime

import pytest

import config
import cotacao
import database
import whatsapp_custo

# Formato real devolvido pela Meta em 07/10/2026 (mistura REGULAR e FREE no mesmo dia).
_RESPOSTA = {
    'currency': 'USD',
    'pricing_analytics': {'data': [{'data_points': [
        {'start': 1, 'end': 2, 'phone_number': '556182487487', 'pricing_type': 'REGULAR',
         'pricing_category': 'SERVICE', 'volume': 553, 'cost': 3.9149},
        {'start': 1, 'end': 2, 'phone_number': '556182487487', 'pricing_type': 'FREE_CUSTOMER_SERVICE',
         'pricing_category': 'SERVICE', 'volume': 321, 'cost': 0},
        {'start': 1, 'end': 2, 'phone_number': '556182487487', 'pricing_type': 'REGULAR',
         'pricing_category': 'MARKETING', 'volume': 10, 'cost': 0.625},
        {'start': 1, 'end': 2, 'phone_number': '556999999999', 'pricing_type': 'FREE_ENTRY_POINT',
         'pricing_category': 'SERVICE', 'volume': 4, 'cost': 0},
    ]}]},
}


def test_agrega_por_telefone_e_categoria():
    r = whatsapp_custo.agregar_pricing_analytics(_RESPOSTA)
    assert r[('556182487487', 'SERVICE')] == {'custo': pytest.approx(3.9149), 'msgs_cobradas': 553, 'msgs_gratis': 321}
    assert r[('556182487487', 'MARKETING')] == {'custo': pytest.approx(0.625), 'msgs_cobradas': 10, 'msgs_gratis': 0}
    assert r[('556999999999', 'SERVICE')]['msgs_gratis'] == 4


def test_resposta_sem_dados():
    assert whatsapp_custo.agregar_pricing_analytics({'id': '1'}) == {}


def test_janela_e_o_dia_em_brasilia():
    ini, fim = whatsapp_custo.janela_do_dia(datetime.date(2026, 10, 7))
    assert fim - ini == 86400
    assert ini == int(datetime.datetime(2026, 10, 7, 3, tzinfo=datetime.timezone.utc).timestamp())


def test_fora_de_producao_nao_chama_a_meta(monkeypatch):
    monkeypatch.setattr(config, 'EH_PRODUCAO', False)
    monkeypatch.setattr(whatsapp_custo, 'consultar_waba', lambda *a: pytest.fail('chamou a Meta no dev'))
    assert whatsapp_custo.coletar_dia(datetime.date(2026, 10, 7), 'intradia')['wabas'] == 0


def test_coleta_so_numeros_meta_e_uma_chamada_por_waba(monkeypatch):
    monkeypatch.setattr(config, 'EH_PRODUCAO', True)
    monkeypatch.setattr(database, 'listar_telefones_com_token', lambda: [
        {'telefone': '556182487487', 'produto_id': 8, 'api_phone_number_id': 'p1', 'provedor': 'meta', 'waba_id': 'W1'},
        {'telefone': '556100000000', 'produto_id': 8, 'api_phone_number_id': 'p2', 'provedor': 'wpp_web', 'waba_id': None},
        {'telefone': '556111111111', 'produto_id': 8, 'api_phone_number_id': 'p3', 'provedor': 'meta', 'waba_id': None},
    ])
    monkeypatch.setattr(database, 'get_whatsapp_token', lambda pid: 'tok')
    chamadas, gravados = [], []
    monkeypatch.setattr(whatsapp_custo, 'consultar_waba', lambda w, t, d: chamadas.append(w) or _RESPOSTA)
    monkeypatch.setattr(database, 'upsert_custo_whatsapp_dia', lambda *a: gravados.append(a))

    r = whatsapp_custo.coletar_dia(datetime.date(2026, 10, 7), 'intradia')

    assert chamadas == ['W1']  # gateway e número sem waba_id ficam de fora
    # 556999999999 não está cadastrado → ignorado; as 2 categorias do número cadastrado são gravadas
    assert sorted(g[2] for g in gravados) == ['MARKETING', 'SERVICE']
    assert all(g[3] == 8 and g[5] == 'USD' for g in gravados)
    assert r == {'wabas': 1, 'falhas': 0, 'falhas_conectados': [], 'linhas': 2}


def test_falha_so_alerta_waba_de_numero_conectado(monkeypatch):
    """Número banido com token morto falha todo dia — não pode virar alerta diário."""
    monkeypatch.setattr(config, 'EH_PRODUCAO', True)
    monkeypatch.setattr(database, 'listar_telefones_com_token', lambda: [
        {'telefone': '1', 'produto_id': 8, 'api_phone_number_id': 'p1', 'provedor': 'meta', 'waba_id': 'W1', 'status_api': 'CONNECTED'},
        {'telefone': '2', 'produto_id': 8, 'api_phone_number_id': 'p2', 'provedor': 'meta', 'waba_id': 'W2', 'status_api': 'BANNED'},
    ])
    monkeypatch.setattr(database, 'get_whatsapp_token', lambda pid: 'tok')

    def falha(w, t, d):
        raise whatsapp_custo.requests.ConnectionError('fora do ar')
    monkeypatch.setattr(whatsapp_custo, 'consultar_waba', falha)

    r = whatsapp_custo.coletar_dia(datetime.date(2026, 10, 7), 'fechamento')
    assert r['falhas'] == 2
    assert r['falhas_conectados'] == ['W1']


def test_upsert_nao_sobrescreve_produto(monkeypatch):
    sqls = []
    monkeypatch.setattr(database.db, 'execute_query', lambda q, p=None, **k: sqls.append(q))
    database.upsert_custo_whatsapp_dia('2026-10-07', '556182487487', 'SERVICE', 8, 'W1', 'USD', 1.0, 1, 0, 'intradia')
    update = sqls[0].split('ON DUPLICATE KEY UPDATE')[1]
    assert 'produto_id' not in update
    assert 'custo' in update


def test_conversao_soma_usd_com_ptax_e_iof_mais_brl(monkeypatch):
    monkeypatch.setattr(cotacao, 'obter_ptax_usd', lambda: {'valor': 5.0, 'data': None, 'fallback': False})
    monkeypatch.setenv('IOF_CARTAO_INTERNACIONAL', '3.5')
    c = cotacao.custo_wpp_para_tela(10.0, 2.0)
    assert c['convertido'] == pytest.approx(2.0 + 10.0 * 5.0 * 1.035)
    assert (c['usd'], c['brl']) == (10.0, 2.0)
