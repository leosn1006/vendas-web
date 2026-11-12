"""Cartão tokenizado pelo Silent Order Post (SOP) da Cielo: o backend só recebe o PaymentToken — número e CVV
nunca passam por aqui (PCI SAQ A-EP). Sem rede, sem banco e sem Redis."""
import importlib
import sys
import types

import pytest

import database
import web.cielo as cielo

checkout = importlib.import_module('web.checkout')  # `web.checkout` também é o nome de uma rota no pacote

TOKEN = '0b9f3c1e-2d4a-4f6b-8c7d-9e0f1a2b3c4d'
CREDENCIAL = {'tipo': 'sop', 'payment_token': TOKEN, 'bin': '453211', 'bandeira': 'visa'}
CORPO = {'produto_id': 1, 'nome': 'Maria', 'email': 'maria@gmail.com', 'cpf': '123.456.789-09',
         'titular': 'MARIA SILVA', 'parcelas': 1, 'credencial': CREDENCIAL}


# ─── Cielo: payload da autorização ────────────────────────────────────────────

class _Resp:
    def __init__(self, status, corpo):
        self.status_code, self._corpo, self.ok = status, corpo, 200 <= status < 300

    def json(self):
        return self._corpo

    def raise_for_status(self):
        if not self.ok:
            raise cielo.requests.HTTPError(str(self.status_code))


def test_criar_transacao_manda_so_o_token(monkeypatch):
    enviado = {}

    def post(url, json=None, headers=None, timeout=None):
        enviado.update(json)
        return _Resp(201, {'Payment': {'Status': 2}})
    monkeypatch.setattr(cielo.requests, 'post', post)
    cielo.criar_transacao(merchant_order_id='9', valor_centavos=4790, parcelas=1, soft_descriptor='LBE',
                          nome='Maria', cpf='12345678909', credencial={**CREDENCIAL, 'bandeira': 'mastercard'})
    cartao = enviado['Payment']['CreditCard']
    assert cartao == {'PaymentToken': TOKEN, 'Brand': 'Master'}
    assert enviado['Payment']['Capture'] is True and enviado['Payment']['Interest'] == 'ByMerchant'


def test_criar_transacao_sem_bandeira_omite_brand(monkeypatch):
    enviado = {}
    monkeypatch.setattr(cielo.requests, 'post',
                        lambda url, json=None, **k: enviado.update(json) or _Resp(201, {'Payment': {}}))
    cielo.criar_transacao(merchant_order_id='9', valor_centavos=100, parcelas=1, soft_descriptor='X', nome='M',
                          cpf='1', credencial={**CREDENCIAL, 'bandeira': ''})
    assert enviado['Payment']['CreditCard'] == {'PaymentToken': TOKEN}


def test_tipo_de_credencial_desconhecido_nao_chama_a_cielo(monkeypatch):
    monkeypatch.setattr(cielo.requests, 'post', lambda *a, **k: pytest.fail('não devia chamar a Cielo'))
    with pytest.raises(ValueError):
        cielo.criar_transacao(merchant_order_id='9', valor_centavos=100, parcelas=1, soft_descriptor='X',
                              nome='M', cpf='1', credencial={'tipo': 'google_pay'})


# ─── Cielo: OAuth e AccessToken do SOP ────────────────────────────────────────

class _RedisFalso:
    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v, ex=None, nx=False):
        if nx and k in self.d:
            return None
        self.d[k] = v
        self.ttl = getattr(self, 'ttl', {})
        self.ttl[k] = ex
        return True

    def incr(self, k):
        self.d[k] = self.d.get(k, 0) + 1
        return self.d[k]

    def expire(self, k, s):
        pass


@pytest.fixture
def redis_falso(monkeypatch):
    r = _RedisFalso()
    monkeypatch.setattr(cielo, '_redis', lambda: r)
    monkeypatch.setattr(cielo, '_SOP_CLIENT_ID', 'id')
    monkeypatch.setattr(cielo, '_SOP_CLIENT_SECRET', 'segredo')
    return r


def test_oauth_guardado_no_redis_evita_nova_chamada(monkeypatch, redis_falso):
    chamadas = []

    def post(url, **k):
        chamadas.append(url)
        if 'oauth' in url:
            return _Resp(200, {'access_token': 'OAUTH1', 'expires_in': 1199})
        return _Resp(201, {'AccessToken': 'SOP1'})
    monkeypatch.setattr(cielo.requests, 'post', post)
    assert cielo.gerar_access_token_sop() == 'SOP1'
    assert cielo.gerar_access_token_sop() == 'SOP1'
    assert sum('oauth' in u for u in chamadas) == 1  # o segundo reaproveitou o token guardado


def test_oauth_revogado_renova_e_tenta_de_novo(monkeypatch, redis_falso):
    redis_falso.d[cielo._CHAVE_REDIS_OAUTH] = 'VENCIDO'

    def post(url, headers=None, **k):
        if 'oauth' in url:
            return _Resp(200, {'access_token': 'NOVO', 'expires_in': 1199})
        if headers['Authorization'] == 'Bearer VENCIDO':
            return _Resp(401, {})
        return _Resp(201, {'AccessToken': 'SOP2'})
    monkeypatch.setattr(cielo.requests, 'post', post)
    assert cielo.gerar_access_token_sop() == 'SOP2'
    assert redis_falso.d[cielo._CHAVE_REDIS_OAUTH] == 'NOVO'


def test_rota_de_token_so_para_produto_com_cartao(monkeypatch, redis_falso):
    monkeypatch.setattr(database, 'get_config_cartao_produto', lambda pid: None)
    assert checkout.gerar_access_token_sop(1, '1.2.3.4')['_status'] == 404


def test_rota_de_token_so_para_produto_a_venda_no_site(monkeypatch, redis_falso):
    monkeypatch.setattr(database, 'get_config_cartao_produto', lambda pid: {'max_parcelas': 1})
    monkeypatch.setattr(database, 'get_produto_disponivel_web', lambda pid: None)
    assert checkout.gerar_access_token_sop(1, '1.2.3.4')['_status'] == 404


def test_rota_de_token_tem_limite_por_ip(monkeypatch, redis_falso):
    monkeypatch.setattr(database, 'get_config_cartao_produto', lambda pid: {'max_parcelas': 1})
    monkeypatch.setattr(database, 'get_produto_disponivel_web', lambda pid: {'id': pid})
    monkeypatch.setattr(cielo, 'gerar_access_token_sop', lambda: 'SOP')
    respostas = [checkout.gerar_access_token_sop(1, '1.2.3.4') for _ in range(31)]
    assert all(r.get('access_token') == 'SOP' for r in respostas[:30])
    assert respostas[30]['_status'] == 429
    assert redis_falso.ttl['limite:sop_token:1.2.3.4'] == 600  # a chave do limite sempre nasce com prazo
    assert checkout.gerar_access_token_sop(1, '5.6.7.8')['access_token'] == 'SOP'  # outro IP segue livre


# ─── gerar_cartao ─────────────────────────────────────────────────────────────

@pytest.fixture
def compra(monkeypatch):
    """gerar_cartao com banco e Cielo simulados; devolve o registro do que foi gravado/enviado."""
    reg = {'estado': None, 'tentativa': None, 'atualizacao': None, 'cielo': None, 'resposta': None}
    simples = {
        'get_produto_disponivel_web': {'id': 1}, 'resolver_plano_checkout': ({'id': 1, 'slug': 'basico'}, 47.9),
        'get_config_cartao_produto': {'max_parcelas': 1, 'parcelas_sem_juros': 1, 'taxa_juros_mensal': 0,
                                      'soft_descriptor': 'LBE'},
        'listar_bumps_validos': [], 'criar_pedido_web_unificado': 77, 'criar_itens_pedido_web': None,
        'garantir_guid_pedido': 'g77', 'listar_itens_pedido': [], 'get_pedido_cartao_para_retry': None,
    }
    for nome, valor in simples.items():
        monkeypatch.setattr(database, nome, lambda *a, _v=valor, **k: _v)
    monkeypatch.setattr(database, 'avancar_pedido_cartao_aguardando', lambda pid: reg.update(estado=1005))
    monkeypatch.setattr(database, 'marcar_pedido_cartao_negado', lambda pid: reg.update(estado=1006))
    monkeypatch.setattr(database, 'confirmar_pagamento_web', lambda **k: reg.update(estado=1000) or True)
    monkeypatch.setattr(database, 'criar_tentativa_pagamento_cartao', lambda **k: reg.update(tentativa=k) or 5)
    monkeypatch.setattr(database, 'atualizar_tentativa_pagamento_cartao',
                        lambda _id, **k: reg.update(atualizacao=k))
    for nome in ('_gravar_navegador', '_vincular_musica'):
        monkeypatch.setattr(checkout, nome, lambda *a, **k: None)
    for nome in ('_erro_validacao_email', '_erro_musica', '_clique_meta_do_corpo', '_whatsapp_do_checkout'):
        monkeypatch.setattr(checkout, nome, lambda *a, **k: None)
    monkeypatch.setattr(checkout, '_phone_number_id_do_produto', lambda pid: 'PH')
    import web.oferta as oferta
    monkeypatch.setattr(oferta, 'desconto_da_oferta', lambda *a, **k: 0)
    monkeypatch.setattr(oferta, 'oferta_divergente', lambda *a, **k: None)
    monkeypatch.setattr(oferta, 'gravar_desconto_pedido', lambda *a, **k: None)
    import web.bandeira_bin as bandeira_bin
    monkeypatch.setattr(bandeira_bin, 'resolver_bandeira', lambda b: 'visa' if b == '453211' else None)
    monkeypatch.setitem(sys.modules, 'tasks', types.SimpleNamespace(
        enviar_email_entrega=types.SimpleNamespace(delay=lambda pid: None)))

    def criar_transacao(**k):
        reg['cielo'] = k
        if isinstance(reg['resposta'], Exception):
            raise reg['resposta']
        return reg['resposta']
    monkeypatch.setattr(cielo, 'criar_transacao', criar_transacao)
    return reg


APROVADO = {'Payment': {'Status': 2, 'PaymentId': 'P1', 'ReturnCode': '00',
                        'CreditCard': {'CardNumber': '453211******3703', 'Brand': 'Visa', 'PaymentToken': TOKEN}}}


@pytest.mark.parametrize('campo', ['numero_cartao', 'cvv'])
def test_corpo_com_cartao_aberto_e_recusado_sem_criar_pedido(compra, campo):
    r = checkout.gerar_cartao({**CORPO, campo: '4532117080573703'})
    assert r['aprovado'] is False and 'pedido_id' not in r and 'Atualize a página' in r['mensagem']
    assert compra['cielo'] is None and compra['tentativa'] is None


@pytest.mark.parametrize('credencial', [None, {}, {'tipo': 'sop'}, {'tipo': 'sop', 'payment_token': 'abc'},
                                        {'tipo': 'apple_pay', 'payment_token': TOKEN}])
def test_credencial_invalida_e_recusada(compra, credencial):
    r = checkout.gerar_cartao({**CORPO, 'credencial': credencial})
    assert r['aprovado'] is False and compra['cielo'] is None


def test_aprovado_paga_e_audita_sem_token(compra):
    compra['resposta'] = APROVADO
    r = checkout.gerar_cartao(dict(CORPO))
    assert r['aprovado'] is True and compra['estado'] == 1000
    assert compra['cielo']['credencial'] == {'tipo': 'sop', 'payment_token': TOKEN, 'bin': '453211', 'bandeira': 'visa'}
    t = compra['tentativa']
    assert t['origem'] == 'sop' and t['cartao_mascarado'] == '453211******' and TOKEN not in str(t['request_json'])
    a = compra['atualizacao']
    assert a['cartao_mascarado'] == '453211******3703'
    assert TOKEN not in str(a['response_json'])


def test_negado_vai_para_1006_com_mensagem_amena(compra):
    compra['resposta'] = {'Payment': {'Status': 3, 'ReturnCode': '05', 'CreditCard': {'CardNumber': '453211******3703'}}}
    r = checkout.gerar_cartao(dict(CORPO))
    assert r['aprovado'] is False and r['permite_retry'] and compra['estado'] == 1006
    assert '05' not in r['mensagem']


def test_rede_fora_deixa_em_1005_para_a_reconciliacao(compra):
    compra['resposta'] = ConnectionError('simulado')
    r = checkout.gerar_cartao(dict(CORPO))
    assert r['aprovado'] is False and compra['estado'] == 1005


def test_bandeira_do_front_so_quando_o_bin_nao_resolve(compra):
    compra['resposta'] = APROVADO
    checkout.gerar_cartao({**CORPO, 'credencial': {**CREDENCIAL, 'bin': '999999', 'bandeira': 'elo'}})
    assert compra['cielo']['credencial']['bandeira'] == 'elo'


def test_reconciliacao_consulta_pelo_numero_gravado_na_tentativa(monkeypatch):
    """O prefixo (CIELO_PREFIXO_PEDIDO) pode mudar entre a venda e o sweep: vale o número que foi para a Cielo."""
    consultado = []
    monkeypatch.setattr(database, 'get_ultima_tentativa_pagamento_cartao',
                        lambda pid: {'id': 1, 'payment_id': None, 'merchant_order_id': 'dev-77', 'valor': 47.9})
    monkeypatch.setattr(database, 'buscar_idade_pedido', lambda pid: None)
    monkeypatch.setattr(cielo, 'consultar_por_merchant_order_id', lambda m: consultado.append(m) or {'Payments': []})
    monkeypatch.setattr(cielo, 'PREFIXO_PEDIDO', '')
    checkout.reconciliar_cartao(77)
    assert consultado == ['dev-77']


def test_merchant_order_id_com_prefixo(monkeypatch):
    monkeypatch.setattr(cielo, 'PREFIXO_PEDIDO', 'dev-')
    assert cielo.merchant_order_id(305690) == 'dev-305690'


def test_com_prefixo_nao_reconcilia_tentativa_antiga_sem_prefixo(monkeypatch):
    """Dev apontando para a Cielo de produção: tentativa antiga (sandbox, sem prefixo) não é consultada."""
    monkeypatch.setattr(database, 'get_ultima_tentativa_pagamento_cartao',
                        lambda pid: {'id': 1, 'payment_id': 'P-SANDBOX', 'merchant_order_id': '283459', 'valor': 10})
    monkeypatch.setattr(cielo, 'consultar_por_payment_id', lambda p: pytest.fail('não devia consultar a Cielo'))
    monkeypatch.setattr(cielo, 'consultar_por_merchant_order_id', lambda m: pytest.fail('não devia consultar a Cielo'))
    monkeypatch.setattr(cielo, 'PREFIXO_PEDIDO', 'dev-')
    assert checkout.reconciliar_cartao(283459) == {'pago': False}


def test_validade_errada_pede_para_conferir_os_dados():
    """Código 54 (visto em produção com a validade digitada errada) não é 'banco não autorizou'."""
    categoria, mensagem = checkout.categorizar_erro_cielo(3, '54', 'Autorizacao negada')
    assert categoria == 'cartao_problema' and 'validade' in mensagem


def test_titular_e_nome_nulos_nao_derrubam(compra):
    compra['resposta'] = APROVADO
    r = checkout.gerar_cartao({**CORPO, 'titular': '', 'nome': None})
    assert r['aprovado'] is True and compra['tentativa']['nome_titular'] == ''


def test_reconciliacao_aprovada_grava_os_4_ultimos_digitos(monkeypatch):
    gravado = {}
    monkeypatch.setattr(database, 'get_ultima_tentativa_pagamento_cartao',
                        lambda pid: {'id': 1, 'payment_id': 'P1', 'merchant_order_id': '77', 'valor': 10})
    monkeypatch.setattr(database, 'atualizar_tentativa_pagamento_cartao', lambda _id, **k: gravado.update(k))
    monkeypatch.setattr(database, 'confirmar_pagamento_web', lambda **k: False)
    monkeypatch.setattr(cielo, 'PREFIXO_PEDIDO', '')
    monkeypatch.setattr(cielo, 'consultar_por_payment_id', lambda p: APROVADO)
    assert checkout.reconciliar_cartao(77)['pago'] is True
    assert gravado['cartao_mascarado'] == '453211******3703'
