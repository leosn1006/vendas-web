"""Compra da Música de fora do Brasil pela Hotmart: os botões da prévia com as ofertas, o /comprar (cria o pedido, liga
a música, cookie e vai para a Hotmart com o xcod) e a página de obrigado. Brasil sem mudança."""
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from musica import rotas
from tests.musica.conftest import RESPOSTAS
from tests.musica.test_idiomas import RESPOSTAS_MX
from tests.musica.test_rotas_idiomas import PLANOS, _previa, cliente  # noqa: F401 — a fixture

PLANOS_MX = [
    {'slug': 'musica', 'nome': 'Canción', 'descricao': '', 'preco': 29.9, 'videoclipe': False,
     'plano': {'id': 25, 'produto_id': 30, 'slug': 'musica', 'padrao': 1}},
    {'slug': 'videoclipe', 'nome': 'Canción + Videoclip', 'descricao': '', 'preco': 49.9, 'videoclipe': True,
     'plano': {'id': 26, 'produto_id': 30, 'slug': 'videoclipe', 'padrao': 0}},
]
OFERTAS = {
    'sph9o75s': {'codigo': 'sph9o75s', 'produto_id': 30, 'plano_id': 25, 'produto_hotmart': 9006872,
                 'preco': Decimal('50.00'), 'moeda': 'MXN', 'uso': 'botao'},
    'cdr8fae7': {'codigo': 'cdr8fae7', 'produto_id': 30, 'plano_id': 26, 'produto_hotmart': 9006872,
                 'preco': Decimal('229.00'), 'moeda': 'MXN', 'uso': 'botao'},
    '6wunkb5c': {'codigo': '6wunkb5c', 'produto_id': 30, 'plano_id': 26, 'produto_hotmart': 9006872,
                 'preco': Decimal('199.00'), 'moeda': 'MXN', 'uso': 'popup'},
}


@pytest.fixture
def hotmart(monkeypatch, cliente):  # noqa: F811
    """O banco do lado da Hotmart (ofertas, pedidos) em memória."""
    import database
    from hotmart import checkout
    estado = {'pedidos': {}, 'vinculos': [], 'estado_pedido': {}}
    planos = {'pt-BR': PLANOS, 'es-MX': PLANOS_MX}
    monkeypatch.setattr(rotas, '_planos_a_venda', lambda: planos[rotas._idioma()])
    monkeypatch.setattr(checkout, 'ofertas_da_previa', lambda produto_id: {
        'botao': {o['plano_id']: o for o in OFERTAS.values() if o['uso'] == 'botao' and o['produto_id'] == produto_id},
        'popup': OFERTAS['6wunkb5c'] if produto_id == 30 else None})
    monkeypatch.setattr(checkout, 'oferta_para_link', lambda codigo, produto_id, moeda=None: OFERTAS.get(codigo) if (
        OFERTAS.get(codigo, {}).get('produto_id') == produto_id and OFERTAS[codigo]['moeda'] == moeda) else None)

    def criar_pedido(produto_id, plano, valor, nome, email, dns):
        n = len(estado['pedidos']) + 1
        estado['pedidos'][n] = {'id': n, 'guid': f'guid{n}', 'plano_id': plano['id'], 'email': email, 'dns': dns}
        return {'id': n, 'guid': f'guid{n}'}

    monkeypatch.setattr(checkout, 'criar_pedido', criar_pedido)
    monkeypatch.setattr(checkout, 'pedido_aberto', lambda musica_id, plano_id: next(
        ({'id': p['id'], 'guid': p['guid']} for p in estado['pedidos'].values()
         if p['plano_id'] == plano_id and p.get('estado_id', 1001) in checkout.ESTADOS_ABERTOS), None))

    monkeypatch.setattr(checkout, 'estado_do_pedido', lambda guid: (
        {'estado': estado['estado_pedido'][guid], 'token': 'tok' + guid} if guid in estado['estado_pedido'] else None))
    monkeypatch.setattr(database, 'get_plano_venda', lambda produto_id, slug: next(
        p['plano'] for p in PLANOS_MX if p['slug'] == slug))
    monkeypatch.setattr(database, 'preco_cobrado_plano', lambda produto_id, plano: 29.9)
    import musica.integracao
    monkeypatch.setattr(musica.integracao, 'vincular_ao_pedido',
                        lambda token, pedido_id, produto_id: estado['vinculos'].append((token, pedido_id)))
    import web.checkout
    monkeypatch.setattr(web.checkout, '_excedeu_limite_ip', lambda *a, **k: False)
    return estado


# ── prévia ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_previa_do_mexico_mostra_as_ofertas_da_hotmart(cliente, hotmart, s):  # noqa: F811
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    dados = cliente.get(f'/mx/cancion/api/musicas/{token}').get_json()
    assert [(p['nome'], p['preco'], p['padrao']) for p in dados['planos']] == [
        ('Canción', 'MX$ 50', True), ('Canción + Videoclip', 'MX$ 229', False)]
    assert dados['planos'][0]['link'] == f'/mx/cancion/comprar/{token}/sph9o75s'
    o = dados['oferta']
    assert (o['preco_cheio'], o['preco'], o['economia']) == ('MX$ 229', 'MX$ 199', 'MX$ 30')
    assert o['link'].startswith(f'/mx/cancion/comprar/{token}/6wunkb5c?oferta=') and o['videoclipe'] is True
    assert o['expira'] == int(o['link'].split('oferta=')[1].split('.')[0])   # o link assinado vale 24 h


def test_previa_do_brasil_continua_com_o_nosso_checkout(cliente, hotmart, s):  # noqa: F811
    token = _previa(s, 'pt-BR', RESPOSTAS)
    dados = cliente.get(f'/musica/api/musicas/{token}').get_json()
    assert dados['planos'][0]['link'] == f'/pay/17?musica={token}'


def test_sem_oferta_de_botao_a_venda_fica_fechada(cliente, hotmart, s, monkeypatch):  # noqa: F811
    from hotmart import checkout
    monkeypatch.setattr(checkout, 'ofertas_da_previa', lambda produto_id: {'botao': {}, 'popup': None})
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    dados = cliente.get(f'/mx/cancion/api/musicas/{token}').get_json()
    assert dados['planos'] == [] and dados['oferta'] is None


# ── comprar ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_comprar_cria_o_pedido_e_vai_para_a_hotmart_com_o_xcod(cliente, hotmart, s):  # noqa: F811
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    r = cliente.get(f'/mx/cancion/comprar/{token}/sph9o75s')
    assert r.status_code == 302
    destino = urlparse(r.headers['Location'])
    assert (destino.netloc, destino.path) == ('pay.hotmart.com', '/9006872')
    assert parse_qs(destino.query) == {'off': ['sph9o75s'], 'xcod': ['guid1'], 'email': ['a@b.com']}
    assert hotmart['pedidos'][1]['plano_id'] == 25 and hotmart['vinculos'] == [(token, 1)]
    assert 'musica_hotmart=guid1' in r.headers['Set-Cookie'] and 'HttpOnly' in r.headers['Set-Cookie']

    r = cliente.get(f'/mx/cancion/comprar/{token}/sph9o75s')            # o 2º clique reaproveita o pedido
    assert 'xcod=guid1' in r.headers['Location'] and len(hotmart['pedidos']) == 1

    popup = cliente.get(f'/mx/cancion/api/musicas/{token}').get_json()['oferta']['link']
    r = cliente.get(popup)                                               # popup (link assinado): o plano do videoclipe
    assert 'off=6wunkb5c' in r.headers['Location'] and hotmart['pedidos'][2]['plano_id'] == 26


def test_popup_sem_o_link_assinado_nao_vende_com_desconto(cliente, hotmart, s):  # noqa: F811
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    for sufixo in ('', '?oferta=9999999999.falsa'):
        r = cliente.get(f'/mx/cancion/comprar/{token}/6wunkb5c{sufixo}')
        assert r.status_code == 302 and r.headers['Location'].endswith(f'/mx/cancion/p/{token}')
    assert hotmart['pedidos'] == {}


def test_pre_carregamento_do_navegador_nao_cria_pedido(cliente, hotmart, s):  # noqa: F811
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    r = cliente.get(f'/mx/cancion/comprar/{token}/sph9o75s', headers={'Sec-Purpose': 'prefetch'})
    assert r.status_code == 204 and hotmart['pedidos'] == {}


@pytest.mark.parametrize('codigo', ['naoexiste', ''])
def test_oferta_desconhecida_nao_cria_pedido(cliente, hotmart, s, codigo):  # noqa: F811
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    r = cliente.get(f'/mx/cancion/comprar/{token}/{codigo}')
    assert r.status_code == 404 and hotmart['pedidos'] == {}


def test_musica_ja_comprada_volta_para_a_previa_sem_pedido(cliente, hotmart, s):  # noqa: F811
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    musica = s.repositorio.por_token(token)
    s.repositorio.atualizar(musica['id'], liberada_em='2026-11-26 10:00:00')
    r = cliente.get(f'/mx/cancion/comprar/{token}/sph9o75s')
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/mx/cancion/p/{token}')
    assert hotmart['pedidos'] == {}


def test_no_brasil_nao_existe(cliente, hotmart, s):  # noqa: F811
    token = _previa(s, 'pt-BR', RESPOSTAS)
    assert cliente.get(f'/musica/comprar/{token}/sph9o75s').status_code == 404
    assert cliente.get('/musica/gracias').status_code == 404


# ── obrigado ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_obrigado_espera_e_leva_para_a_area_da_compra(cliente, hotmart):  # noqa: F811
    cliente.set_cookie('musica_hotmart', 'guid7')
    html = cliente.get('/mx/cancion/gracias').get_data(as_text=True)
    assert 'Estamos confirmando tu pago' in html and '/mx/cancion/api/compra-hotmart' in html
    assert cliente.get('/mx/cancion/api/compra-hotmart').get_json() == {'situacao': 'sem_pedido'}
    hotmart['estado_pedido']['guid7'] = 1001
    assert cliente.get('/mx/cancion/api/compra-hotmart').get_json() == {'situacao': 'processando'}
    hotmart['estado_pedido']['guid7'] = 1010
    assert cliente.get('/mx/cancion/api/compra-hotmart').get_json() == {'situacao': 'aguardando'}
    hotmart['estado_pedido']['guid7'] = 1011
    assert cliente.get('/mx/cancion/api/compra-hotmart').get_json() == {
        'situacao': 'cancelado', 'link': '/mx/cancion/p/tokguid7'}
    hotmart['estado_pedido']['guid7'] = 1000
    assert cliente.get('/mx/cancion/api/compra-hotmart').get_json() == {
        'situacao': 'pago', 'link': '/mx/cancion/compra/guid7'}


def test_obrigado_sem_cookie_avisa_do_email_sem_prometer_que_ja_foi(cliente, hotmart):  # noqa: F811
    html = cliente.get('/mx/cancion/gracias').get_data(as_text=True)
    assert 'Tu canción llega por correo' in html and 'En cuanto se confirme el pago' in html
    assert 'api/compra-hotmart' not in html
    assert cliente.get('/mx/cancion/api/compra-hotmart').get_json() == {'situacao': 'sem_pedido'}


def test_depois_do_cartao_recusado_o_novo_clique_cria_outro_pedido(cliente, hotmart, s):  # noqa: F811
    """O cancelado não é reaberto: um aviso atrasado da transação recusada não pode mexer no pagamento novo."""
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    cliente.get(f'/mx/cancion/comprar/{token}/sph9o75s')
    hotmart['pedidos'][1]['estado_id'] = 1011                           # o cartão foi recusado
    r = cliente.get(f'/mx/cancion/comprar/{token}/sph9o75s')
    assert 'xcod=guid2' in r.headers['Location'] and 'musica_hotmart=guid2' in r.headers['Set-Cookie']


def test_oferta_em_outra_moeda_nao_aparece_na_previa(cliente, hotmart, s, monkeypatch):  # noqa: F811
    import copy
    monkeypatch.setitem(OFERTAS, '6wunkb5c', {**copy.deepcopy(OFERTAS['6wunkb5c']), 'moeda': 'USD'})
    monkeypatch.setitem(OFERTAS, 'cdr8fae7', {**copy.deepcopy(OFERTAS['cdr8fae7']), 'moeda': 'USD'})
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    dados = cliente.get(f'/mx/cancion/api/musicas/{token}').get_json()
    assert [p['nome'] for p in dados['planos']] == ['Canción'] and dados['oferta'] is None
