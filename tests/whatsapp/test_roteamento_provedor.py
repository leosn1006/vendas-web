"""
Roteamento por provedor (Meta x gateway WhatsApp Web).

Por que importa: número 'meta' TEM de continuar batendo na Graph API exatamente como antes da coluna
`provedor`; número 'wpp_web' vai para o api-wpp-web. Erro aqui manda mensagem de cliente para o lugar errado.
"""
import pytest

import database
import whatsapp

GATEWAY = 'http://api-wpp-web:3100/v24.0/'


@pytest.fixture
def gateway_url(monkeypatch):
    monkeypatch.setattr(database, 'WPP_WEB_API_URL', GATEWAY)


class _Resp:
    status_code = 200

    def json(self):
        return {'messages': [{'id': 'wamid.X'}]}


@pytest.fixture
def captura_post(monkeypatch):
    chamadas = []

    def fake_post(url, headers=None, json=None, timeout=None):
        chamadas.append({'url': url, 'json': json, 'timeout': timeout})
        return _Resp()

    monkeypatch.setattr(whatsapp.requests, 'post', fake_post)
    monkeypatch.setattr(whatsapp, 'get_whatsapp_token', lambda _pid: 'token-teste')
    return chamadas


# ─── get_whatsapp_api_url ────────────────────────────────────────────────────

def test_numero_meta_usa_graph_api(provedores):
    provedores['1012710858592627'] = 'meta'
    assert database.get_whatsapp_api_url('1012710858592627') == database.WHATSAPP_API_URL


def test_numero_nao_cadastrado_cai_na_meta(provedores):
    assert database.get_whatsapp_api_url('999') == database.WHATSAPP_API_URL


def test_sem_phone_number_id_cai_na_meta_sem_consultar_banco(provedores):
    assert database.get_whatsapp_api_url(None) == database.WHATSAPP_API_URL
    assert provedores['_consultas'] == []


def test_numero_wpp_web_usa_gateway(provedores, gateway_url):
    provedores['web-5561982402450'] = 'wpp_web'
    assert database.get_whatsapp_api_url('web-5561982402450') == GATEWAY


def test_gateway_sem_barra_final_ganha_barra(provedores, monkeypatch):
    monkeypatch.setattr(database, 'WPP_WEB_API_URL', 'http://gw:3100/v24.0')
    provedores['web-1'] = 'wpp_web'
    assert database.get_whatsapp_api_url('web-1') == 'http://gw:3100/v24.0/'


def test_wpp_web_sem_url_configurada_falha_explicito(provedores, monkeypatch):
    monkeypatch.setattr(database, 'WPP_WEB_API_URL', '')
    provedores['web-1'] = 'wpp_web'
    with pytest.raises(ValueError, match='WPP_WEB_API_URL'):
        database.get_whatsapp_api_url('web-1')


def test_provedor_e_cacheado_por_ttl_curto(provedores):
    provedores['web-1'] = 'wpp_web'
    database.get_provedor_numero('web-1')
    database.get_provedor_numero('web-1')
    assert len(provedores['_consultas']) == 1  # segunda leitura veio do cache


def test_cache_expira_e_enxerga_edicao_do_admin(provedores, monkeypatch):
    provedores['web-1'] = 'meta'
    assert database.get_provedor_numero('web-1') == 'meta'
    provedores['web-1'] = 'wpp_web'  # admin editou
    # avança o relógio além do TTL
    base = database.time.monotonic()
    monkeypatch.setattr(database.time, 'monotonic', lambda: base + database._PROVEDOR_CACHE_TTL_S + 1)
    assert database.get_provedor_numero('web-1') == 'wpp_web'


def test_provedor_invalido_no_banco_vira_meta():
    assert database._normalizar_provedor('qualquer-coisa') == 'meta'
    assert database._normalizar_provedor(None) == 'meta'


# ─── envio ───────────────────────────────────────────────────────────────────

def test_enviar_mensagem_meta_bate_na_graph(provedores, captura_post):
    provedores['1012710858592627'] = 'meta'
    pedido = {'phone_number_id': '1012710858592627', 'contact_to': '556181163324'}
    assert whatsapp.enviar_mensagem(pedido, 'oi') == 'wamid.X'
    assert captura_post[0]['url'] == 'https://graph.facebook.com/v24.0/1012710858592627/messages'


def test_enviar_mensagem_wpp_web_bate_no_gateway(provedores, gateway_url, captura_post):
    provedores['web-5561982402450'] = 'wpp_web'
    pedido = {'phone_number_id': 'web-5561982402450', 'contact_to': '556181163324'}
    whatsapp.enviar_mensagem(pedido, 'oi')
    assert captura_post[0]['url'] == f'{GATEWAY}web-5561982402450/messages'
    assert captura_post[0]['json']['to'] == '556181163324'


def test_marcar_como_lida_tem_timeout(provedores, gateway_url, captura_post, monkeypatch):
    provedores['web-1'] = 'wpp_web'
    monkeypatch.setattr(_Resp, 'raise_for_status', lambda self: None, raising=False)
    whatsapp.marcar_como_lida('wamid.A', 'web-1')
    assert captura_post[0]['timeout']  # antes era None: worker travava com gateway mudo


def test_template_em_numero_wpp_web_falha_com_mensagem_clara(provedores, gateway_url):
    provedores['web-1'] = 'wpp_web'
    with pytest.raises(ValueError, match='Template não existe no gateway'):
        whatsapp.enviar_produto_whatsapp({'phone_number_id': 'web-1'}, 't', 'pt_BR', 'u', 'f', [])


# ─── link da Estante ─────────────────────────────────────────────────────────

def test_link_estante_wpp_web_usa_dns_origem(provedores, monkeypatch):
    provedores['web-1'] = 'wpp_web'
    pedido = {'id': 1, 'guid': 'abc', 'phone_number_id': 'web-1', 'dns_origem': 'lsnlivros.com.br'}
    assert whatsapp.montar_link_estante(pedido) == 'https://lsnlivros.com.br/pedido/abc'
    assert whatsapp.montar_link_estante(pedido, '/pedido2') == 'https://lsnlivros.com.br/pedido2/abc'


def test_link_estante_wpp_web_ignora_porta_e_caixa_do_dns_origem(provedores):
    provedores['web-1'] = 'wpp_web'
    pedido = {'id': 1, 'guid': 'abc', 'phone_number_id': 'web-1', 'dns_origem': 'LSNLivros.com.br:443'}
    assert whatsapp.montar_link_estante(pedido) == 'https://lsnlivros.com.br/pedido/abc'


@pytest.fixture(autouse=True)
def _sem_app_base_url(monkeypatch):
    # cada teste decide se há APP_BASE_URL; o valor do .env de quem roda os testes não pode vazar para cá
    monkeypatch.delenv('APP_BASE_URL', raising=False)


@pytest.mark.parametrize('dns', [None, '', 'localhost', 'evil.com/x', 'a b.com', 'http://x.com'])
def test_link_estante_wpp_web_sem_dns_valido_e_sem_app_base_url_falha(provedores, dns):
    provedores['web-1'] = 'wpp_web'
    pedido = {'id': 1, 'guid': 'abc', 'phone_number_id': 'web-1', 'dns_origem': dns}
    with pytest.raises(ValueError, match='dns_origem'):
        whatsapp.montar_link_estante(pedido)


@pytest.mark.parametrize('dns', [None, ''])
def test_link_estante_cliente_que_veio_direto_pelo_whatsapp_usa_app_base_url(provedores, monkeypatch, dns):
    """Caso que quebrou em produção: mensagem direta ao número (sem site) => pedido sem dns_origem.
    Antes o fluxo 'pedido' parava com erro e o cliente ficava sem resposta."""
    provedores['web-1'] = 'wpp_web'
    monkeypatch.setenv('APP_BASE_URL', 'https://lsnlivros.com.br')
    pedido = {'id': 345550, 'guid': 'abc', 'phone_number_id': 'web-1', 'dns_origem': dns}
    assert whatsapp.montar_link_estante(pedido) == 'https://lsnlivros.com.br/pedido/abc'
    assert whatsapp.montar_link_estante(pedido, '/pedido2') == 'https://lsnlivros.com.br/pedido2/abc'


def test_link_estante_dns_origem_do_pedido_tem_prioridade_sobre_app_base_url(provedores, monkeypatch):
    provedores['web-1'] = 'wpp_web'
    monkeypatch.setenv('APP_BASE_URL', 'https://lsnlivros.com.br')
    pedido = {'id': 1, 'guid': 'abc', 'phone_number_id': 'web-1', 'dns_origem': 'lneditor.com.br'}
    assert whatsapp.montar_link_estante(pedido) == 'https://lneditor.com.br/pedido/abc'


@pytest.mark.parametrize('base,esperado', [
    ('https://lsnlivros.com.br/', 'lsnlivros.com.br'),      # barra final
    ('https://lsnlivros.com.br:443/x', 'lsnlivros.com.br'),  # porta e caminho
    ('LSNLivros.com.br', 'lsnlivros.com.br'),                # sem esquema, caixa
])
def test_link_estante_app_base_url_tolera_formatos_do_env(provedores, monkeypatch, base, esperado):
    provedores['web-1'] = 'wpp_web'
    monkeypatch.setenv('APP_BASE_URL', base)
    pedido = {'id': 1, 'guid': 'abc', 'phone_number_id': 'web-1', 'dns_origem': None}
    assert whatsapp.montar_link_estante(pedido) == f'https://{esperado}/pedido/abc'


@pytest.mark.parametrize('base', ['http://localhost', 'http://localhost:8000', '', 'https://a b.com'])
def test_link_estante_app_base_url_do_compose_padrao_nao_serve(provedores, monkeypatch, base):
    """O compose usa http://localhost quando APP_BASE_URL não está definida: não pode virar link para o cliente."""
    provedores['web-1'] = 'wpp_web'
    monkeypatch.setenv('APP_BASE_URL', base)
    pedido = {'id': 1, 'guid': 'abc', 'phone_number_id': 'web-1', 'dns_origem': None}
    with pytest.raises(ValueError, match='APP_BASE_URL'):
        whatsapp.montar_link_estante(pedido)


def test_link_estante_meta_continua_pelo_token_env_key(provedores, monkeypatch):
    provedores['1012710858592627'] = 'meta'
    monkeypatch.setattr(whatsapp, 'get_token_env_key', lambda _pid: 'WHATSAPP_ACCESS_TOKEN_LSN')
    monkeypatch.setattr(whatsapp, 'dominio_por_token_env_key', lambda _k: 'lsnlivros.com.br')
    pedido = {'id': 1, 'guid': 'abc', 'phone_number_id': '1012710858592627', 'dns_origem': 'outro.com.br'}
    assert whatsapp.montar_link_estante(pedido) == 'https://lsnlivros.com.br/pedido/abc'


# ─── timeouts ────────────────────────────────────────────────────────────────

def _pedido(pid):
    return {'phone_number_id': pid, 'contact_to': '556181163324'}


def test_timeouts_numero_meta_continuam_30s(provedores, captura_post, monkeypatch):
    provedores['1012710858592627'] = 'meta'
    pedido = _pedido('1012710858592627')
    whatsapp.enviar_mensagem(pedido, 'oi')
    whatsapp.enviar_imagem(pedido, 'https://x.com/a.jpg')
    whatsapp.enviar_audio(pedido, 'https://x.com/a.ogg')
    whatsapp.enviar_documento(pedido, 'https://x.com/a.pdf', 'c', 'a.pdf')
    assert [c['timeout'] for c in captura_post] == [30, 30, 30, 30]


def test_timeouts_gateway_cobrem_pior_caso_do_gateway(provedores, gateway_url, captura_post):
    """Gateway: texto 25 s (+fila); mídia = baixar link 30 s + enviar até 120 s. O app tem de esperar mais que isso."""
    provedores['web-1'] = 'wpp_web'
    pedido = _pedido('web-1')
    whatsapp.enviar_mensagem(pedido, 'oi')
    whatsapp.enviar_imagem(pedido, 'https://x.com/a.jpg')
    whatsapp.enviar_audio(pedido, 'https://x.com/a.ogg')
    whatsapp.enviar_documento(pedido, 'https://x.com/a.pdf', 'c', 'a.pdf')
    texto, imagem, audio, documento = [c['timeout'] for c in captura_post]
    assert texto > 25
    assert imagem == audio == documento > 30 + 120
