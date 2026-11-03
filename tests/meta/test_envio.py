"""Cenários 20 a 34: seleção das vendas (a consulta real, no SQLite), evento e envio."""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import requests

import database
from fluxos import fluxo_meta_conversoes as fluxo
from fluxos.fluxo_meta_conversoes import executar, montar_evento, normalizar_telefone

from .conftest import dias_atras

TOKEN = 'token-secreto'


def _sha(texto):
    return hashlib.sha256(texto.encode()).hexdigest()


def _ids_selecionados():
    return [v['id'] for v in database.busca_vendas_pendentes_meta()]


class Resposta:
    def __init__(self, corpo=None, status=200):
        self.corpo, self.status_code = corpo if corpo is not None else {'events_received': 1}, status

    def json(self):
        if isinstance(self.corpo, Exception):
            raise self.corpo
        return self.corpo


@pytest.fixture
def meta(monkeypatch):
    """A API simulada: guarda as chamadas e responde com `meta.resposta` (ou a função dada)."""
    estado = SimpleNamespace(chamadas=[], resposta=lambda: Resposta())

    def post(url, headers=None, json=None, timeout=None):
        estado.chamadas.append(SimpleNamespace(url=url, headers=headers, json=json))
        return estado.resposta()
    monkeypatch.setattr(fluxo.requests, 'post', post)
    monkeypatch.setenv('META_TOKEN_LSN', TOKEN)
    monkeypatch.delenv('META_TEST_EVENT_CODE', raising=False)
    monkeypatch.setattr(fluxo.config, 'WHATSAPP_API_URL', 'https://meta.teste/v24.0/')
    return estado


def _venda(**campos):
    padrao = dict(id=7, estado_id=1000, valor_pago=47.9, dns_origem='site.com', fbc='fb.1.1700000000000.AbC',
                  client_ip='200.1.2.3', client_user_agent='Mozilla/5.0', email=' Maria@Exemplo.com ',
                  contact_phone='556181163324', data_pagamento=datetime.now() - timedelta(days=1))
    return SimpleNamespace(**{**padrao, **campos})


# ─── Seleção ──────────────────────────────────────────────────────────────────

def test_20_pago_campanha_meta_dataset_ativo_vai(banco, venda_meta):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    pid = venda_meta()
    vendas = database.busca_vendas_pendentes_meta()
    assert [v['id'] for v in vendas] == [pid]
    assert vendas[0]['meta_dataset_id'] == '999' and vendas[0]['meta_token_env_var'] == 'META_TOKEN_LSN'


def test_20_whatsapp_estado_0_vai(banco, venda_meta):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    pid = venda_meta(estado_id=0)
    assert _ids_selecionados() == [pid]


@pytest.mark.parametrize('campos', [{'gclid': 'G1'}, {'wbraid': 'W'}, {'gbraid': 'B'}])
def test_21_com_clique_do_google_nao_vai(banco, venda_meta, campos):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    venda_meta(**campos)
    assert _ids_selecionados() == []


def test_21_campanha_google_nao_vai(banco, venda_meta):
    banco.campanha('123', plataforma='google')
    banco.dataset()
    venda_meta()
    assert _ids_selecionados() == []


def test_21_campanha_sem_linha_nao_vai(banco, venda_meta):
    banco.dataset()
    venda_meta()
    assert _ids_selecionados() == []


def test_21_campanha_de_outro_produto_nao_conta(banco, venda_meta):
    banco.campanha('123', produto_id=2, plataforma='meta')
    banco.dataset()
    venda_meta()
    assert _ids_selecionados() == []


@pytest.mark.parametrize('campos', [
    {'estado_id': 1002}, {'estado_id': 1}, {'data_envio_meta': dias_atras(0)},
    {'data_pagamento': dias_atras(6.01)}, {'data_pagamento': None},
], ids=['aguardando_pix', 'lead', 'ja_enviado', 'mais_de_6_dias', 'sem_data'])
def test_22_nao_vai(banco, venda_meta, campos):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    venda_meta(**campos)
    assert _ids_selecionados() == []


def test_22_com_5_dias_e_meio_ainda_vai(banco, venda_meta):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    assert venda_meta(data_pagamento=dias_atras(5.5)) in _ids_selecionados()


def test_23_campanha_sem_destino_nao_chama_a_meta_e_avisa(banco, venda_meta, meta, caplog):
    banco.campanha('123', plataforma='meta')
    pid = venda_meta()
    with caplog.at_level(logging.ERROR):
        resumo = executar()
    assert meta.chamadas == [] and resumo['pendentes'] == 1
    assert banco.ler_pedido(pid)['data_envio_meta'] is None
    assert f'Venda {pid}' in caplog.text and 'ainda sem destino' in caplog.text


def test_23_usa_o_dataset_e_o_token_da_campanha(banco, venda_meta, meta, monkeypatch):
    monkeypatch.setenv('META_TOKEN_OUTRA', 'token-da-outra-bm')
    banco.campanha('123', plataforma='meta')
    banco.dataset(dataset_id='111', token_env_var='META_TOKEN_OUTRA')
    venda_meta()
    executar()
    assert meta.chamadas[0].url.endswith('/111/events')
    assert meta.chamadas[0].headers['Authorization'] == 'Bearer token-da-outra-bm'


def test_23_mesmo_dominio_em_duas_campanhas_vai_para_o_dataset_de_cada_uma(banco, venda_meta, meta):
    banco.campanha('123', plataforma='meta')
    banco.campanha('456', plataforma='meta')
    banco.dataset('123', dataset_id='111')
    banco.dataset('456', dataset_id='222')
    venda_meta(campaignid='123', data_pagamento=dias_atras(2))
    venda_meta(campaignid='456', data_pagamento=dias_atras(1))
    executar()
    assert [c.url.rsplit('/', 2)[1] for c in meta.chamadas] == ['111', '222']


# ─── Evento ───────────────────────────────────────────────────────────────────

def test_24_evento_do_site_com_valor_pago(banco, venda_meta, meta):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    pid = venda_meta()
    executar()
    evento = meta.chamadas[0].json['data'][0]
    assert evento['event_name'] == 'Purchase' and evento['event_id'] == f'pedido-{pid}'
    assert evento['action_source'] == 'website' and evento['event_source_url'] == 'https://site.com/'
    assert evento['custom_data'] == {'currency': 'BRL', 'value': 47.9}
    assert len(meta.chamadas[0].json['data']) == 1


def test_25_whatsapp_vale_10_reais():
    assert montar_evento(_venda(estado_id=0, valor_pago=47.9))['custom_data'] == {'currency': 'BRL', 'value': 10.0}


def test_26_hash_so_em_email_e_telefone():
    user_data = montar_evento(_venda())['user_data']
    assert user_data['em'] == [_sha('maria@exemplo.com')]
    assert user_data['ph'] == [_sha('5561981163324')]
    assert user_data['fbc'] == 'fb.1.1700000000000.AbC'
    assert user_data['client_ip_address'] == '200.1.2.3' and user_data['client_user_agent'] == 'Mozilla/5.0'


def test_cartao_sem_telefone_e_sem_fbc_vai_so_com_email():
    user_data = montar_evento(_venda(contact_phone='', fbc=None, client_ip=None))['user_data']
    assert 'ph' not in user_data and 'fbc' not in user_data and 'client_ip_address' not in user_data
    assert 'em' in user_data


@pytest.mark.parametrize('entrada, saida', [
    ('556181163324', '5561981163324'), ('5561981163324', '5561981163324'), ('556133334444', '556133334444'),
    ('14155550123', '14155550123'), ('', ''), (None, ''), ('+55 (61) 8116-3324', '5561981163324'),
    ('00556181163324', '5561981163324'),
])
def test_27_telefone(entrada, saida):
    assert normalizar_telefone(entrada) == saida


def test_28_data_futura_vira_agora():
    agora = datetime.now().timestamp()
    tempo = montar_evento(_venda(data_pagamento=datetime.now() + timedelta(days=30)))['event_time']
    assert abs(tempo - agora) < 5


def test_28_event_time_em_horario_de_brasilia():
    pago = datetime.now(timezone(timedelta(hours=-3))).replace(microsecond=0, tzinfo=None) - timedelta(days=1)
    esperado = int(pago.replace(tzinfo=timezone.utc).timestamp()) + 3 * 3600
    assert montar_evento(_venda(data_pagamento=pago))['event_time'] == esperado


def test_28_data_em_texto_como_no_google():
    pago = (datetime.now(timezone(timedelta(hours=-3))) - timedelta(days=1)).replace(microsecond=0, tzinfo=None)
    esperado = int(pago.replace(tzinfo=timezone.utc).timestamp()) + 3 * 3600
    assert montar_evento(_venda(data_pagamento=pago.strftime('%Y-%m-%d %H:%M:%S')))['event_time'] == esperado


@pytest.mark.parametrize('campos', [{'dns_origem': ''}, {'dns_origem': None}, {'client_user_agent': ''},
                                    {'client_user_agent': None}])
def test_29_sem_dominio_ou_navegador_nao_monta(campos):
    assert montar_evento(_venda(**campos)) is None


def test_29_venda_fica_pendente_sem_chamar_a_meta(banco, venda_meta, meta, caplog):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    pid = venda_meta(client_user_agent=None)
    with caplog.at_level(logging.WARNING):
        resumo = executar()
    assert meta.chamadas == [] and resumo['pendentes'] == 1
    assert banco.ler_pedido(pid)['data_envio_meta'] is None
    assert 'fica pendente' in caplog.text


# ─── Envio ────────────────────────────────────────────────────────────────────

def _uma_venda(banco, venda_meta):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    return venda_meta()


def test_30_aceite_marca_como_enviada_e_sai_da_selecao(banco, venda_meta, meta):
    pid = _uma_venda(banco, venda_meta)
    resumo = executar()
    assert resumo['enviadas'] == 1 and resumo['erros'] == 0
    assert banco.ler_pedido(pid)['data_envio_meta'] is not None
    assert _ids_selecionados() == []
    chamada = meta.chamadas[0]
    assert chamada.url == 'https://meta.teste/v24.0/999/events'


@pytest.mark.parametrize('resposta', [
    Resposta({'error': {'message': 'recusado'}}, status=400), Resposta({'events_received': 1}, status=500),
    Resposta({'events_received': 0}), Resposta(['nao', 'objeto']), Resposta(ValueError('sem json')), Resposta({}),
    Resposta({'events_received': 'muitos'}),
], ids=['http_400', 'http_500_com_aceite', 'zero', 'json_lista', 'nao_json', 'sem_campo', 'texto'])
def test_30_recusa_nao_marca_e_conta_erro(banco, venda_meta, meta, resposta):
    pid = _uma_venda(banco, venda_meta)
    meta.resposta = lambda: resposta
    resumo = executar()
    assert resumo['erros'] == 1 and resumo['enviadas'] == 0
    assert banco.ler_pedido(pid)['data_envio_meta'] is None


def test_30_falha_de_conexao_nao_marca_e_conta_erro(banco, venda_meta, meta):
    pid = _uma_venda(banco, venda_meta)

    def cai():
        raise requests.ConnectionError('fora do ar')
    meta.resposta = cai
    assert executar()['erros'] == 1
    assert banco.ler_pedido(pid)['data_envio_meta'] is None


def test_31_excecao_numa_venda_nao_para_as_seguintes(banco, venda_meta, meta):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    ruim = venda_meta(data_pagamento=dias_atras(3))
    boa = venda_meta(data_pagamento=dias_atras(2))
    respostas = iter([RuntimeError('inesperado'), Resposta()])

    def proxima():
        r = next(respostas)
        if isinstance(r, Exception):
            raise r
        return r
    meta.resposta = proxima
    resumo = executar()
    assert resumo == {'vendas': 2, 'enviadas': 1, 'testes': 0, 'pendentes': 0, 'erros': 1}
    assert banco.ler_pedido(ruim)['data_envio_meta'] is None
    assert banco.ler_pedido(boa)['data_envio_meta'] is not None


def test_32_modo_teste_manda_o_codigo_e_nao_marca(banco, venda_meta, meta, monkeypatch):
    monkeypatch.setenv('META_TEST_EVENT_CODE', 'TEST123')
    pid = _uma_venda(banco, venda_meta)
    resumo = executar()
    assert meta.chamadas[0].json['test_event_code'] == 'TEST123'
    assert resumo['testes'] == 1 and banco.ler_pedido(pid)['data_envio_meta'] is None


def test_fora_do_modo_teste_nao_manda_codigo(banco, venda_meta, meta):
    _uma_venda(banco, venda_meta)
    executar()
    assert 'test_event_code' not in meta.chamadas[0].json


def test_33_token_so_no_cabecalho(banco, venda_meta, meta, caplog):
    _uma_venda(banco, venda_meta)
    meta.resposta = lambda: Resposta({'events_received': 0})
    with caplog.at_level(logging.DEBUG):
        executar()
    chamada = meta.chamadas[0]
    assert chamada.headers['Authorization'] == f'Bearer {TOKEN}'
    assert TOKEN not in chamada.url and TOKEN not in str(chamada.json)
    assert TOKEN not in caplog.text


@pytest.mark.parametrize('variavel, valor', [('SECRET_KEY', 'segredo'), ('META_TOKEN_VAZIO', ''),
                                             ('META_TOKEN_AUSENTE', None), ('', None)])
def test_33_variavel_recusada_nao_chama_a_meta(banco, venda_meta, meta, monkeypatch, variavel, valor):
    if valor is not None:
        monkeypatch.setenv(variavel, valor)
    banco.campanha('123', plataforma='meta')
    banco.dataset(token_env_var=variavel)
    pid = venda_meta()
    assert executar()['erros'] == 1
    assert meta.chamadas == [] and banco.ler_pedido(pid)['data_envio_meta'] is None


@pytest.mark.parametrize('dias, avisa', [(5, True), (5.5, True), (4, False), (4.9, False)])
def test_34_aviso_de_janela(meta, monkeypatch, caplog, dias, avisa):
    agora_br = datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    venda = {**vars(_venda(data_pagamento=agora_br - timedelta(days=dias))), 'meta_dataset_id': '999',
             'meta_token_env_var': 'META_TOKEN_LSN'}
    monkeypatch.setattr(fluxo, 'busca_vendas_pendentes_meta', lambda: [venda])
    monkeypatch.setattr(fluxo, 'marcar_venda_como_enviada_a_meta', lambda pedido_id: None)
    meta.resposta = lambda: Resposta({'events_received': 0})
    with caplog.at_level(logging.ERROR):
        executar()
    assert ('sem aceite há' in caplog.text) is avisa


def test_34_venda_aceita_nao_gera_aviso_de_janela(meta, monkeypatch, caplog):
    agora_br = datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    venda = {**vars(_venda(data_pagamento=agora_br - timedelta(days=5))), 'meta_dataset_id': '999',
             'meta_token_env_var': 'META_TOKEN_LSN'}
    monkeypatch.setattr(fluxo, 'busca_vendas_pendentes_meta', lambda: [venda])
    monkeypatch.setattr(fluxo, 'marcar_venda_como_enviada_a_meta', lambda pedido_id: None)
    with caplog.at_level(logging.ERROR):
        executar()
    assert 'sem aceite há' not in caplog.text


@pytest.mark.parametrize('entrada, esperado', [
    ('55999998888', '5555999998888'),    # celular do DDD 55 gravado sem o DDI
    ('5533334444', '555533334444'),      # fixo do DDD 55 gravado sem o DDI
    ('5555999998888', '5555999998888'),
    ('14155550123', '14155550123'),
])
def test_27_ddd_55_sem_ddi(entrada, esperado):
    assert fluxo.normalizar_telefone(entrada) == esperado


def test_31_data_invalida_no_aviso_nao_derruba_as_outras_vendas(meta, monkeypatch):
    ruim = {**vars(_venda(id=1, data_pagamento='data ruim')), 'meta_dataset_id': '999', 'meta_token_env_var': 'META_TOKEN_LSN'}
    boa = {**vars(_venda(id=2)), 'meta_dataset_id': '999', 'meta_token_env_var': 'META_TOKEN_LSN'}
    marcadas = []
    monkeypatch.setattr(fluxo, 'busca_vendas_pendentes_meta', lambda: [ruim, boa])
    monkeypatch.setattr(fluxo, 'marcar_venda_como_enviada_a_meta', marcadas.append)
    resumo = executar()
    assert marcadas == [2] and resumo['erros'] == 1 and resumo['enviadas'] == 1


def test_34_queda_de_rede_tambem_avisa(meta, monkeypatch, caplog):
    agora_br = datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    venda = {**vars(_venda(data_pagamento=agora_br - timedelta(days=5))), 'meta_dataset_id': '999',
             'meta_token_env_var': 'META_TOKEN_LSN', 'campaignid': '123'}
    monkeypatch.setattr(fluxo, 'busca_vendas_pendentes_meta', lambda: [venda])

    def fora(*a, **k):
        raise fluxo.requests.ConnectionError('fora')
    monkeypatch.setattr(fluxo.requests, 'post', fora)
    with caplog.at_level(logging.ERROR):
        resumo = executar()
    assert resumo['erros'] == 1 and 'sem aceite há' in caplog.text
