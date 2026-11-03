"""Cenários 1 a 19: clique no funil do site, no corpo do checkout e na landing do WhatsApp."""
import json
import re
from pathlib import Path

import pytest
from flask import Flask

from meta_clique import clique_meta, fbclid_do_fbc
from web.checkout import rastrear_visita_funil

ANUNCIO = 'gad_campaignid=123&adgroupid=9&creative=8&placement=ig&utm_source=meta'
_APP = Flask(__name__)
RAIZ = Path(__file__).resolve().parents[2]


def visita(query='', pedido_id=None, estado_novo=1004):
    """Uma visita ao funil do produto 1; `pedido_id` é o rascunho do cookie."""
    cabecalhos = {'Cookie': f'pedido_web_1={pedido_id}'} if pedido_id else {}
    with _APP.test_request_context(f'/?{query}', headers=cabecalhos, base_url='https://site.com'):
        from flask import request
        return rastrear_visita_funil(request, 1, estado_novo=estado_novo)


def foto_do_clique(banco, pedido_id):
    p = banco.ler_pedido(pedido_id)
    return {c: p[c] for c in ('gclid', 'fbc', 'campaignid', 'adgroupid', 'creative', 'placement')}


# ─── Clique ───────────────────────────────────────────────────────────────────

def test_01_url_completa_grava_fbc_e_cria_campanha_meta(banco):
    p = banco.ler_pedido(visita(f'fbclid=AbC&{ANUNCIO}'))
    assert re.fullmatch(r'fb\.1\.\d{13}\.AbC', p['fbc'])
    assert p['campaignid'] == '123' and p['adgroupid'] == '9'
    campanha = banco.ler_campanha('123')
    assert campanha['plataforma'] == 'meta' and campanha['nome'] == '123' and campanha['venda_web'] == 1


def test_01_campanha_que_ja_existe_nao_muda(banco):
    banco.campanha('123', nome='Dada no admin', plataforma='google')
    visita(f'fbclid=AbC&{ANUNCIO}')
    campanha = banco.ler_campanha('123')
    assert campanha['nome'] == 'Dada no admin' and campanha['plataforma'] == 'google'


def test_02_sem_fbclid_grava_campanha_sem_fbc(banco):
    p = banco.ler_pedido(visita(ANUNCIO))
    assert p['fbc'] is None and p['campaignid'] == '123'
    assert banco.ler_campanha('123')['plataforma'] == 'meta'


def test_03_link_da_bio_em_rascunho_com_gclid_nada_muda(banco):
    pid = banco.pedido(produto_id=1, estado_id=1004, gclid='G1', campaignid='777')
    antes = foto_do_clique(banco, pid)
    assert visita('fbclid=AbC', pedido_id=pid) == pid
    assert foto_do_clique(banco, pid) == antes
    assert banco.contar('campanhas') == 0


@pytest.mark.parametrize('query', ['fbclid=AbC&gad_campaignid=123', 'fbclid=AbC&utm_source=meta',
                                   'fbclid=AbC&gad_campaignid=123&utm_source=google'])
def test_04_sem_utm_ou_sem_campanha_nao_e_anuncio(banco, query):
    p = banco.ler_pedido(visita(query))
    assert p['fbc'] is None
    assert banco.contar('campanhas') == 0


@pytest.mark.parametrize('campanha', ['abc', '12a', '1' * 31, '١٢٣', '123\n'])
def test_05_campanha_invalida_nao_e_anuncio(banco, campanha):
    assert clique_meta({'utm_source': 'meta', 'gad_campaignid': campanha, 'fbclid': 'AbC'}) is None


def test_05_campanha_com_30_digitos_vale():
    assert clique_meta({'utm_source': 'meta', 'gad_campaignid': '1' * 30})['campaignid'] == '1' * 30


def test_05_campanha_invalida_na_url_nao_cria_campanha(banco):
    p = banco.ler_pedido(visita('fbclid=AbC&gad_campaignid=abc&utm_source=meta'))
    assert p['fbc'] is None and banco.contar('campanhas') == 0


@pytest.mark.parametrize('fbclid', [123, None, ['AbC'], 'com espaço', 'a<b', 'x' * 501, 'AbC\n', ''])
def test_06_fbclid_invalido_nao_da_erro_e_o_anuncio_vale(fbclid):
    clique = clique_meta({'utm_source': 'meta', 'campaignid': '123', 'fbclid': fbclid}, chave_campanha='campaignid')
    assert clique == {'campaignid': '123', 'fbclid': None, 'fbc': None}


@pytest.mark.parametrize('google', ['gclid', 'wbraid', 'gbraid'])
def test_07_clique_do_google_junto_nao_e_meta(banco, google):
    p = banco.ler_pedido(visita(f'{google}=X&fbclid=AbC&{ANUNCIO}'))
    assert p['fbc'] is None and banco.contar('campanhas') == 0


def test_08_maiusculas_do_fbclid_chegam_iguais(banco):
    p = banco.ler_pedido(visita(f'fbclid=AbC-dEf_GhI&{ANUNCIO}'))
    assert fbclid_do_fbc(p['fbc']) == 'AbC-dEf_GhI'


# ─── Último clique no rascunho ────────────────────────────────────────────────

def rascunho_meta(banco, fbclid='Velho', campanha='123'):
    fbc = f'fb.1.1700000000000.{fbclid}' if fbclid else None
    banco.campanha(campanha, plataforma='meta')
    return banco.pedido(produto_id=1, estado_id=1004, gclid='', fbc=fbc, campaignid=campanha)


def test_09_rascunho_com_gclid_e_anuncio_da_meta_troca_tudo(banco):
    pid = banco.pedido(produto_id=1, estado_id=1004, gclid='G1', campaignid='777', adgroupid='1', creative='2')
    visita(f'fbclid=AbC&{ANUNCIO}', pedido_id=pid)
    p = banco.ler_pedido(pid)
    assert p['gclid'] == '' and p['campaignid'] == '123' and p['adgroupid'] == '9' and p['creative'] == '8'
    assert fbclid_do_fbc(p['fbc']) == 'AbC'
    assert banco.ler_campanha('123')['plataforma'] == 'meta'


def test_10_rascunho_da_meta_e_clique_do_google_zera_o_fbc(banco):
    pid = rascunho_meta(banco)
    visita('gclid=G2&gad_campaignid=555', pedido_id=pid)
    p = banco.ler_pedido(pid)
    assert p['gclid'] == 'G2' and p['campaignid'] == '555' and not p['fbc']


def test_11_mesmo_fbclid_de_novo_nada_muda(banco):
    pid = visita(f'fbclid=AbC&{ANUNCIO}')
    antes = foto_do_clique(banco, pid)
    visita(f'fbclid=AbC&{ANUNCIO}', pedido_id=pid)
    assert foto_do_clique(banco, pid) == antes


def test_11_f5_recria_a_campanha_que_faltou_no_primeiro_clique(banco):
    pid = visita(f'fbclid=AbC&{ANUNCIO}')
    banco.conexao.execute('DELETE FROM campanhas')
    visita(f'fbclid=AbC&{ANUNCIO}', pedido_id=pid)
    assert banco.ler_campanha('123')['plataforma'] == 'meta'


def test_12_fbclid_novo_troca_o_fbc(banco):
    pid = rascunho_meta(banco)
    visita(f'fbclid=Novo&{ANUNCIO}', pedido_id=pid)
    assert fbclid_do_fbc(banco.ler_pedido(pid)['fbc']) == 'Novo'


def test_13_anuncio_sem_fbclid_em_outra_campanha_zera_o_fbc(banco):
    pid = rascunho_meta(banco, campanha='777')
    visita(ANUNCIO, pedido_id=pid)
    p = banco.ler_pedido(pid)
    assert p['campaignid'] == '123' and not p['fbc']


def test_13_anuncio_sem_fbclid_na_mesma_campanha_nada_muda(banco):
    pid = rascunho_meta(banco)
    antes = foto_do_clique(banco, pid)
    visita(ANUNCIO, pedido_id=pid)
    assert foto_do_clique(banco, pid) == antes


def test_14_navegacao_sem_parametros_nada_muda(banco):
    pid = rascunho_meta(banco)
    antes = foto_do_clique(banco, pid)
    visita('', pedido_id=pid)
    assert foto_do_clique(banco, pid) == antes


def test_15_gclid_fica_com_visita_so_de_wbraid(banco):
    pid = banco.pedido(produto_id=1, estado_id=1004, gclid='G1', campaignid='777')
    antes = foto_do_clique(banco, pid)
    visita('wbraid=W&gad_campaignid=555', pedido_id=pid)
    assert foto_do_clique(banco, pid) == antes


@pytest.mark.parametrize('braid', ['wbraid', 'gbraid'])
@pytest.mark.parametrize('fbclid', ['Velho', None], ids=['com_fbc', 'sem_fbc'])
def test_16_rascunho_da_meta_com_braid_troca_campanha_e_zera_fbc(banco, braid, fbclid):
    pid = rascunho_meta(banco, fbclid=fbclid)
    visita(f'{braid}=W&gad_campaignid=555', pedido_id=pid)
    p = banco.ler_pedido(pid)
    assert p['campaignid'] == '555' and not p['fbc']


def test_16_rascunho_sem_clique_nenhum_com_braid_nada_muda(banco):
    banco.campanha('777', plataforma='google')
    pid = banco.pedido(produto_id=1, estado_id=1004, gclid='', campaignid='777')
    visita('wbraid=W&gad_campaignid=555', pedido_id=pid)
    assert banco.ler_pedido(pid)['campaignid'] == '777'


def test_17_mesmo_gclid_de_novo_nada_muda(banco):
    pid = banco.pedido(produto_id=1, estado_id=1004, gclid='G1', campaignid='777')
    antes = foto_do_clique(banco, pid)
    visita('gclid=G1&gad_campaignid=555', pedido_id=pid)
    assert foto_do_clique(banco, pid) == antes


def test_pedido_pago_nunca_muda(banco):
    pid = banco.pedido(produto_id=1, estado_id=1000, gclid='G1', campaignid='777')
    antes = foto_do_clique(banco, pid)
    assert visita(f'fbclid=AbC&{ANUNCIO}', pedido_id=pid) != pid  # o cookie de pedido pago não é reaproveitado
    assert foto_do_clique(banco, pid) == antes

    from database import atualizar_campanha_rascunho, gravar_clique_pedido
    atualizar_campanha_rascunho(pid, gclid='', campaignid='1', fbc='fb.1.1.X')
    gravar_clique_pedido(pid, ip='1.1.1.1', navegador='N', fbc='fb.1.1.X')
    p = banco.ler_pedido(pid)
    assert foto_do_clique(banco, pid) == antes and p['client_ip'] is None and p['client_user_agent'] is None


# ─── Pedido criado sem rascunho ───────────────────────────────────────────────

@pytest.fixture
def checkout_simulado(monkeypatch, banco):
    """gerar_pix/gerar_cartao com o que é alheio ao clique simulado (produto, plano, bumps, oferta, itens, Cielo)."""
    import database
    import web.checkout as checkout
    import web.oferta as oferta
    for nome, valor in {
        'get_produto_disponivel_web': {'id': 1}, 'resolver_plano_checkout': ({'id': 1}, 47.9), 'listar_bumps_validos': [],
        'get_phone_number_id_produto': 'PH', 'criar_itens_pedido_web': None, 'buscar_chave_pix_venda_web': None,
        'get_config_cartao_produto': {'max_parcelas': 1, 'parcelas_sem_juros': 1, 'taxa_juros_mensal': 0,
                                      'soft_descriptor': 'X'},
        'avancar_pedido_cartao_aguardando': None, 'criar_tentativa_pagamento_cartao': 1,
    }.items():
        monkeypatch.setattr(database, nome, lambda *a, _v=valor, **k: _v)
    monkeypatch.setattr(oferta, 'desconto_da_oferta', lambda *a, **k: 0)
    monkeypatch.setattr(oferta, 'oferta_divergente', lambda *a, **k: None)
    monkeypatch.setattr(oferta, 'gravar_desconto_pedido', lambda *a, **k: None)
    monkeypatch.setattr(checkout, '_erro_musica', lambda *a, **k: None)
    monkeypatch.setattr(checkout, '_vincular_musica', lambda *a, **k: None)
    import web.bandeira_bin as bandeira_bin
    import web.cielo as cielo
    monkeypatch.setattr(bandeira_bin, 'resolver_bandeira', lambda *a: 'visa')

    def rede_fora(**k):
        raise ConnectionError('simulado')
    monkeypatch.setattr(cielo, 'criar_transacao', rede_fora)
    return checkout


CORPO = {'produto_id': 1, 'nome': 'Maria', 'email': 'maria@gmail.com', 'whatsapp': '61981163324', 'gclid': '',
         'campaignid': '123', 'utm_source': 'meta', 'fbclid': 'AbC', 'adgroupid': '9'}
CABECALHOS = {'X-Real-IP': '200.1.2.3', 'User-Agent': 'Mozilla/5.0'}


@pytest.mark.parametrize('funcao', ['gerar_pix', 'gerar_cartao'])
def test_corpo_captura_clique_ip_e_navegador(banco, checkout_simulado, funcao):
    with _APP.test_request_context('/', headers=CABECALHOS):
        resposta = getattr(checkout_simulado, funcao)(dict(CORPO), dns_origem='site.com')
    p = banco.ler_pedido(resposta['pedido_id'])
    assert fbclid_do_fbc(p['fbc']) == 'AbC' and p['client_ip'] == '200.1.2.3' and p['client_user_agent'] == 'Mozilla/5.0'
    assert banco.ler_campanha('123')['plataforma'] == 'meta' and banco.ler_campanha('123')['venda_web'] == 1


def test_06_fbclid_numero_no_corpo_nao_derruba_o_checkout(banco, checkout_simulado):
    with _APP.test_request_context('/', headers=CABECALHOS):
        resposta = checkout_simulado.gerar_pix({**CORPO, 'fbclid': 123}, dns_origem='site.com')
    p = banco.ler_pedido(resposta['pedido_id'])
    assert p['fbc'] is None and p['campaignid'] == '123'
    assert banco.ler_campanha('123')['plataforma'] == 'meta'


def test_rascunho_finalizado_mantem_o_clique_e_ganha_ip_e_navegador(banco, checkout_simulado):
    pid = banco.pedido(produto_id=1, estado_id=1003, gclid='', fbc='fb.1.1700000000000.Velho', campaignid='123')
    with _APP.test_request_context('/', headers=CABECALHOS):
        resposta = checkout_simulado.gerar_pix({**CORPO, 'pedido_id': pid}, dns_origem='site.com')
    assert resposta['pedido_id'] == pid
    p = banco.ler_pedido(pid)
    assert p['fbc'] == 'fb.1.1700000000000.Velho' and p['client_ip'] == '200.1.2.3'


def test_ip_cai_no_remote_addr_sem_x_real_ip(banco, checkout_simulado):
    with _APP.test_request_context('/', environ_base={'REMOTE_ADDR': '10.0.0.9'}):
        resposta = checkout_simulado.gerar_pix(dict(CORPO), dns_origem='site.com')
    assert banco.ler_pedido(resposta['pedido_id'])['client_ip'] == '10.0.0.9'


def test_falha_ao_gravar_ip_nao_derruba_o_checkout(banco, checkout_simulado, monkeypatch):
    import database

    def falha(*a, **k):
        raise RuntimeError('banco fora')
    monkeypatch.setattr(database, 'gravar_clique_pedido', falha)
    with _APP.test_request_context('/', headers=CABECALHOS):
        resposta = checkout_simulado.gerar_pix(dict(CORPO), dns_origem='site.com')
    assert resposta['pedido_id']


@pytest.mark.parametrize('template', ['checkout.html', 'checkout-2.html', 'dicas-quimio.html'])
def test_templates_mandam_o_clique_em_utmdata(template):
    html = (RAIZ / 'app' / 'templates' / template).read_text(encoding='utf-8')
    utm_data = re.search(r'const utmData = \{(.*?)\};', html, re.S).group(1)
    for campo in ('fbclid', 'utm_source', 'wbraid', 'gbraid'):
        assert re.search(rf"{campo}:\s+urlParams\.get\('{campo}'\)", utm_data)


# ─── Lead ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def lead(monkeypatch, banco):
    import lead_incluir
    monkeypatch.setattr(lead_incluir, 'gera_mensagem_inicial_randomicamente', lambda produto: 'Oi')
    monkeypatch.setattr(lead_incluir, 'selecionar_telefone_produto', lambda produto: {'telefone': '5561999990000'})

    def enviar(url, **corpo):
        with _APP.test_request_context('/', method='POST', headers=CABECALHOS):
            resposta, status = lead_incluir.persistir_lead({'url': url, **corpo})
            return status, json.loads(resposta.get_data())
    return enviar


def _ultimo_pedido(banco):
    return banco.ler_pedido(banco.conexao.execute('SELECT MAX(id) FROM pedidos').fetchone()[0])


def test_18_lead_com_anuncio_grava_fbc_ip_navegador_e_campanha_sem_venda_web(banco, lead):
    status, corpo = lead(f'https://site.com/fatia?fbclid=AbC&{ANUNCIO}')
    assert status == 200 and corpo['whatsapp_numero'] == '5561999990000'
    p = _ultimo_pedido(banco)
    assert fbclid_do_fbc(p['fbc']) == 'AbC' and p['campaignid'] == '123'
    assert p['client_ip'] == '200.1.2.3' and p['client_user_agent'] == 'Mozilla/5.0'
    campanha = banco.ler_campanha('123', produto_id=12)
    assert campanha['plataforma'] == 'meta' and campanha['venda_web'] == 0


def test_lead_com_gclid_no_corpo_nao_e_meta(banco, lead):
    lead(f'https://site.com/fatia?fbclid=AbC&{ANUNCIO}', gclid='G1')
    p = _ultimo_pedido(banco)
    assert p['fbc'] is None and p['gclid'] == 'G1' and banco.contar('campanhas') == 0


def test_lead_organico_guarda_navegador_e_nao_cria_campanha(banco, lead):
    lead('https://site.com/fatia?fbclid=AbC')
    p = _ultimo_pedido(banco)
    assert p['fbc'] is None and p['client_user_agent'] == 'Mozilla/5.0' and banco.contar('campanhas') == 0


@pytest.mark.parametrize('alvo', ['gravar_clique_pedido', 'criar_campanha_meta'])
def test_19_falha_no_clique_do_lead_responde_com_o_whatsapp(banco, lead, monkeypatch, alvo):
    import database
    import lead_incluir

    def falha(*a, **k):
        raise RuntimeError('banco fora')
    monkeypatch.setattr(database, alvo, falha)
    if alvo == 'gravar_clique_pedido':
        monkeypatch.setattr(lead_incluir, alvo, falha)
    status, corpo = lead(f'https://site.com/fatia?fbclid=AbC&{ANUNCIO}')
    assert status == 200 and corpo['whatsapp_numero'] == '5561999990000'
