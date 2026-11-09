"""Contribuição no site: sorteio do A/B, endpoints da entrada, camada da Estante e travas do follow-up do checkout."""
import inspect
import sys
import types

import pytest
from flask import Flask

import database
import lead_incluir  # noqa: F401 — importado antes dos monkeypatch: ele faz `from database import ...` no import
from web import contribuicao as ctb


class _Req:
    def __init__(self, args=None, cookies=None):
        self.args = args or {}
        self.cookies = cookies or {}


def _config(**extra):
    return {'produto_id': 11, 'ativo': 1, 'percentual_estante': 25, 'persona_nome': 'Luiza',
            'persona_foto': 'images/luiza.jpg', 'audio_intro': 'audios/contribuicao/i.mp3',
            'audio_cobranca': 'audios/contribuicao/c.mp3', 'audio_lembrete': 'audios/contribuicao/l.mp3',
            'texto_intro': 'oi', 'texto_cobranca': 'cobra', 'texto_lembrete': 'lembra', 'checklist': 'a\nb', **extra}


# ── Sorteio ──────────────────────────────────────────────────────────────────────────────

def test_teste_desligado_vai_todo_mundo_pro_whatsapp_sem_cookie():
    for config in (_config(percentual_estante=0), _config(ativo=0), None):
        r = ctb.sortear_braco(_Req(cookies={'ab_contrib_11': 'estante'}), 11, config)
        assert r == {'braco': 'wpp', 'teste': False, 'cookie': None}


def test_sorteio_grava_cookie_e_depois_respeita_o_cookie(monkeypatch):
    monkeypatch.setattr(ctb.random, 'random', lambda: 0.10)  # 10 < 25 → estante
    r = ctb.sortear_braco(_Req(), 11, _config())
    assert r == {'braco': 'estante', 'teste': False, 'cookie': 'estante'}
    monkeypatch.setattr(ctb.random, 'random', lambda: 0.90)
    assert ctb.sortear_braco(_Req(), 11, _config())['braco'] == 'wpp'
    # Com cookie, o sorteio não roda de novo (mesma pessoa, mesmo braço).
    assert ctb.sortear_braco(_Req(cookies={'ab_contrib_11': 'estante'}), 11, _config()) == \
        {'braco': 'estante', 'teste': False, 'cookie': None}


def test_qa_forca_o_braco_mesmo_com_o_teste_em_zero():
    r = ctb.sortear_braco(_Req(args={'contrib': 'estante'}), 11, _config(percentual_estante=0))
    assert r == {'braco': 'estante', 'teste': True, 'cookie': 'estante:teste'}
    r = ctb.sortear_braco(_Req(cookies={'ab_contrib_11': 'estante:teste'}), 11, _config(percentual_estante=0))
    assert r == {'braco': 'estante', 'teste': True, 'cookie': None}


def test_cookie_invalido_e_ignorado(monkeypatch):
    monkeypatch.setattr(ctb.random, 'random', lambda: 0.90)
    assert ctb.sortear_braco(_Req(cookies={'ab_contrib_11': 'xpto'}), 11, _config())['braco'] == 'wpp'


# ── Endpoints ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def http(monkeypatch):
    estado = {'pedidos': {}, 'registros': [], 'marcos': [], 'entregues': [], 'emails': [], 'criados': 0}

    def criar(produto_id, nome, atrib, plano):
        estado['criados'] += 1
        p = {'id': 500 + estado['criados'], 'guid': f'gnovo{estado["criados"]:03d}', 'estado_id': 1008,
             'produto_id': produto_id, 'email': None}
        estado['pedidos'][p['guid']] = p
        estado['atrib'] = atrib
        return {'id': p['id'], 'guid': p['guid']}

    monkeypatch.setattr(database, 'get_contribuicao_config', lambda pid: _config() if pid == 11 else None)
    monkeypatch.setattr(database, 'get_plano_venda', lambda pid, slug=None: {'id': 7, 'preco_promocional': 10})
    monkeypatch.setattr(database, 'criar_pedido_contribuicao', criar)
    monkeypatch.setattr(database, 'registrar_contribuicao_pedido',
                        lambda *a, **k: estado['registros'].append((a, k)))
    monkeypatch.setattr(database, 'gravar_clique_pedido', lambda *a, **k: None)
    monkeypatch.setattr(database, 'get_pedido_by_guid', lambda g: estado['pedidos'].get(g))
    monkeypatch.setattr(database, 'marcar_marco_contribuicao', lambda pid, m: estado['marcos'].append((pid, m)))
    estado['cliques_repetidos'] = []
    monkeypatch.setattr(database, 'contar_clique_contribuicao', lambda pid: estado['cliques_repetidos'].append(pid))

    def entregar(pid, nome, email):  # como o banco: só entrega a partir de 1008, e o e-mail não muda depois
        p = next(p for p in estado['pedidos'].values() if p['id'] == pid)
        if p['estado_id'] != 1008:
            return False
        p.update(estado_id=1009, email=email)
        estado['entregues'].append((pid, nome, email))
        return True
    monkeypatch.setattr(database, 'entregar_pedido_contribuicao', entregar)
    tarefa = types.SimpleNamespace(delay=lambda pid: estado['emails'].append(pid))
    monkeypatch.setitem(sys.modules, 'tasks', types.SimpleNamespace(enviar_email_contribuicao_entrega=tarefa))
    estado['limite'] = 'ok'
    estado['reservas_envio'] = []

    def reservar(tipo, pid, ip, limite):
        estado['reservas_envio'].append((tipo, pid))
        return estado['limite']
    monkeypatch.setattr(database, 'reservar_envio_email', reservar)
    monkeypatch.setattr(database, 'desfazer_envio_email', lambda *a: None)
    estado['juntados'] = []
    monkeypatch.setattr(database, 'juntar_clique_na_entrega_anterior',
                        lambda novo, anterior: estado['juntados'].append((novo, anterior)))
    estado['cliques_novos'] = []
    monkeypatch.setattr(database, 'atualizar_clique_contribuicao',
                        lambda pid, atrib: estado['cliques_novos'].append((pid, atrib['gclid'])))

    app = Flask(__name__)
    app.register_blueprint(ctb.web_bp)
    c = app.test_client()
    c.set_cookie('ab_contrib_11', 'estante')  # sorteada pro braço estante (percentual 25 na _config)
    return c, estado


def test_iniciar_cria_a_entrega_com_a_atribuicao_e_conta_o_clique(http):
    c, estado = http
    c.set_cookie('ab_contrib_11', 'estante:teste')
    r = c.post('/api/v1/contribuicao/iniciar', json={
        'produto_id': 11, 'url': 'https://lsnlivros.com.br/tempero?gclid=abc&wbraid=w1', 'gclid': 'abc',
        'campaignid': '123'})
    assert r.status_code == 200 and r.get_json()['guid'] == 'gnovo001'
    assert estado['atrib']['gclid'] == 'abc' and estado['atrib']['wbraid'] == 'w1'
    assert estado['atrib']['dns_origem'] == 'lsnlivros.com.br'
    assert estado['registros'] == [((501, 11, 'estante', True), {})]


def test_iniciar_fora_do_braco_estante_ou_com_teste_desligado_cai_pro_whatsapp(http, monkeypatch):
    c, estado = http
    c.set_cookie('ab_contrib_11', 'wpp')
    assert c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11}).status_code == 409
    c.delete_cookie('ab_contrib_11')
    assert c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11}).status_code == 409
    c.set_cookie('ab_contrib_11', 'estante')
    monkeypatch.setattr(database, 'get_contribuicao_config', lambda pid: _config(percentual_estante=0))
    assert c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11}).status_code == 409
    c.set_cookie('ab_contrib_11', 'estante:teste')  # QA continua funcionando com o teste em 0
    assert c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11}).status_code == 200
    assert estado['criados'] == 1


def test_iniciar_de_novo_com_o_guid_reaproveita_o_pedido(http):
    c, estado = http
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11})
    r = c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11, 'guid': 'gnovo001'})
    assert r.get_json()['guid'] == 'gnovo001' and estado['criados'] == 1
    assert estado['cliques_repetidos'] == [501]  # o clique repetido conta, como no braço wpp (1 lead por clique)


def test_iniciar_sem_configuracao_devolve_erro_e_a_pagina_cai_pro_whatsapp(http):
    c, _ = http
    assert c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 12}).status_code == 409


def test_entregar_valida_o_email_e_manda_a_entrega(http):
    c, estado = http
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11})
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Maria', 'email': 'maria@gmail.comm'})
    assert r.status_code == 400 and r.get_json()['erro'] == 'email'
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Maria', 'email': ' Maria@Gmail.com '})
    assert r.status_code == 200 and r.get_json()['url'] == '/pedido2/gnovo001?chegou=1'
    assert estado['entregues'] == [(501, 'Maria', 'maria@gmail.com')]
    assert estado['emails'] == [501]


def test_email_da_entrega_sai_so_na_primeira_vez(http):
    c, estado = http
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11})
    c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Maria', 'email': 'maria@gmail.com'})
    # De novo com o mesmo e-mail (voltou na página / dois toques): a Estante, sem outro e-mail.
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Maria', 'email': 'maria@gmail.com'})
    assert r.status_code == 200 and r.get_json()['guid'] == 'gnovo001'
    # Outro e-mail numa entrega feita: não muda o pedido (seria um jeito de mandar o reenvio a qualquer endereço);
    # a página recomeça com um pedido novo.
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Ana', 'email': 'outra@gmail.com'})
    assert r.status_code == 409 and r.get_json() == {'erro': 'ja_entregue'}
    assert estado['pedidos']['gnovo001']['email'] == 'maria@gmail.com'
    assert estado['emails'] == [501] and estado['reservas_envio'] == [('entrega_contribuicao', 501)]


def test_limite_barra_o_email_mas_nao_a_entrega(http):
    c, estado = http
    estado['limite'] = 'ip'
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11})
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Maria', 'email': 'maria@gmail.com'})
    assert r.status_code == 200 and r.get_json()['url'] == '/pedido2/gnovo001?chegou=1'
    assert estado['entregues'] and not estado['emails']


def test_clique_novo_de_anuncio_no_mesmo_aparelho_vale_o_ultimo(http):
    c, estado = http
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11, 'gclid': 'A'})
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11, 'guid': 'gnovo001'})  # sem anúncio: mantém
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11, 'guid': 'gnovo001', 'gclid': 'B'})
    assert estado['cliques_novos'] == [(501, 'B')] and estado['criados'] == 1


def _entregue(estado, guid, email, produto_id=11):
    estado['pedidos'][guid] = {'id': 400, 'guid': guid, 'estado_id': 1009, 'produto_id': produto_id, 'email': email}


def test_entrega_feita_nao_e_reaproveitada_por_outra_pessoa_no_mesmo_navegador(http):
    """Mãe e filho no mesmo celular: o guid guardado é de uma entrega já feita → pedido novo (senão o nome e o
    e-mail dela sobrescreveriam os do pedido dele)."""
    c, estado = http
    _entregue(estado, 'gdudu001', 'dudu@gmail.com')
    r = c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11, 'guid': 'gdudu001'})
    assert r.get_json()['guid'] == 'gnovo001' and estado['criados'] == 1 and not estado['cliques_repetidos']
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Ana', 'email': 'ana@gmail.com',
                                                      'anteriores': ['gdudu001']})
    assert r.get_json() == {'url': '/pedido2/gnovo001?chegou=1', 'guid': 'gnovo001'}
    assert estado['entregues'] == [(501, 'Ana', 'ana@gmail.com')] and not estado['juntados']


def test_mesma_pessoa_voltando_cai_na_propria_estante(http):
    c, estado = http
    _entregue(estado, 'gdudu001', 'dudu@gmail.com')
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11, 'guid': 'gdudu001'})
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Dudu', 'email': ' Dudu@Gmail.com',
                                                      'anteriores': ['gdudu001']})
    assert r.get_json() == {'url': '/pedido2/gdudu001', 'guid': 'gdudu001'}
    assert estado['juntados'] == [(501, 400)] and not estado['entregues'] and not estado['emails']


def test_reconhece_qualquer_uma_das_entregas_do_navegador(http):
    """Dudu, depois a mãe, depois o Dudu de novo: ele cai na Estante dele, não na dela nem num pedido novo."""
    c, estado = http
    _entregue(estado, 'gdudu001', 'dudu@gmail.com')
    estado['pedidos']['gmae0001'] = {'id': 401, 'guid': 'gmae0001', 'estado_id': 1009, 'produto_id': 11,
                                     'email': 'mae@gmail.com'}
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11, 'guid': 'gmae0001'})
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Dudu', 'email': 'dudu@gmail.com',
                                                      'anteriores': ['gmae0001', 'gdudu001', 123, None]})
    assert r.get_json()['guid'] == 'gdudu001' and estado['juntados'] == [(501, 400)]


def test_anterior_de_outro_produto_nao_conta(http):
    c, estado = http
    _entregue(estado, 'goutro01', 'dudu@gmail.com', produto_id=12)
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11})
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gnovo001', 'nome': 'Dudu', 'email': 'dudu@gmail.com',
                                                      'anteriores': ['goutro01']})
    assert r.get_json()['guid'] == 'gnovo001' and not estado['juntados']


def test_entregar_guid_que_nao_e_de_contribuicao_e_recusado(http):
    c, estado = http
    estado['pedidos']['gpago0001'] = {'id': 9, 'guid': 'gpago0001', 'estado_id': 1000}
    r = c.post('/api/v1/contribuicao/entregar', json={'guid': 'gpago0001', 'email': 'maria@gmail.com'})
    assert r.status_code == 404 and not estado['entregues']


def test_evento_so_aceita_os_marcos_da_pagina(http):
    c, estado = http
    c.post('/api/v1/contribuicao/iniciar', json={'produto_id': 11})
    assert c.post('/api/v1/contribuicao/evento', json={'guid': 'gnovo001', 'marco': 'email_em'}).status_code == 204
    assert c.post('/api/v1/contribuicao/evento', json={'guid': 'gnovo001', 'marco': 'x; DROP'}).status_code == 204
    assert c.post('/api/v1/contribuicao/evento', json={'guid': 'gnovo001', 'marco': 'audio1_play_em'}).status_code == 204
    assert estado['marcos'] == [(501, 'audio1_play_em')]


def test_marco_invalido_nunca_vira_sql():
    with pytest.raises(ValueError):
        database.marcar_marco_contribuicao(1, 'nome_em = NOW(), estado_id')


# ── Camada da Estante ────────────────────────────────────────────────────────────────────

@pytest.fixture
def estante(monkeypatch):
    estado = {'paga': False, 'marcos': []}
    monkeypatch.setattr(database, 'get_contribuicao_config', lambda pid: _config())
    def paga(pedido, por_email=True):
        estado['por_email'] = por_email
        return estado['paga']
    monkeypatch.setattr(database, 'contribuicao_paga', paga)
    monkeypatch.setattr(database, 'marcar_marco_contribuicao', lambda pid, m: estado['marcos'].append(m))
    monkeypatch.setattr(database, 'get_plano_venda', lambda pid, slug=None: {
        'id': 7, 'slug': 'basico', 'padrao': 1, 'preco_promocional': 10, 'nome': 'Temperos',
        'principais': [{'nome_venda': 'Temperos', 'imagem_pequena': 'capa.webp'}]})
    return estado


def test_estante_da_entrega_nao_paga_pede_a_contribuicao(estante):
    ctx = ctb.contexto_estante({'id': 50, 'guid': 'gteste01', 'estado_id': 1009, 'produto_id': 11})
    assert ctx['link'] == '/pay2/11?ref=gteste01'
    assert ctx['preco'] == '10' and ctx['audio'] == '/static/audios/contribuicao/c.mp3'
    assert estante['marcos'] == ['estante_em']
    lembrete = ctb.contexto_estante({'id': 50, 'guid': 'gteste01', 'estado_id': 1009, 'produto_id': 11}, lembrete=True)
    assert lembrete['audio'] == '/static/audios/contribuicao/l.mp3'


def test_estante_volta_ao_normal_depois_de_pagar_ou_fora_da_contribuicao(estante):
    estante['paga'] = True
    assert ctb.contexto_estante({'id': 50, 'guid': 'g', 'estado_id': 1009, 'produto_id': 11}) is None
    estante['paga'] = False
    assert ctb.contexto_estante({'id': 50, 'guid': 'g', 'estado_id': 1000, 'produto_id': 11}) is None
    assert ctb.contexto_estante({'id': 50, 'guid': 'g', 'estado_id': 3, 'produto_id': 11}) is None


def test_estante_so_considera_paga_pelo_vinculo_nunca_pelo_email(estante):
    ctb.contexto_estante({'id': 50, 'guid': 'g', 'estado_id': 1009, 'produto_id': 11})
    assert estante['por_email'] is False


def test_checkout_so_e_contribuicao_para_o_mesmo_produto_e_nao_paga(monkeypatch):
    pago = {'v': False}
    monkeypatch.setattr(database, 'contribuicao_paga', lambda p, por_email=True: pago['v'])
    entrega = {'id': 50, 'estado_id': 1009, 'produto_id': 11}
    assert ctb.eh_origem_contribuicao(entrega, 11) is True
    assert ctb.eh_origem_contribuicao(entrega, 12) is False      # cross-sell de outro produto
    assert ctb.eh_origem_contribuicao({**entrega, 'estado_id': 1000}, 11) is False
    assert ctb.eh_origem_contribuicao(None, 11) is False
    pago['v'] = True
    assert ctb.eh_origem_contribuicao(entrega, 11) is False      # já contribuiu: compra normal


# ── Follow-up do checkout ────────────────────────────────────────────────────────────────

def test_checkout_da_contribuicao_fica_fora_do_followup_web():
    sql = inspect.getsource(database.buscar_pedidos_followup_pagamento_web)
    assert 'contribuicao_pedidos' in sql and 'pedidos_vinculados' in sql
    assert "cp.braco = 'estante'" in sql and 'cp.produto_id = p.produto_id' in sql
