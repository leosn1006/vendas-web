"""O navegador (static/js/email-validacao.js) e o servidor (web/email_validacao.py) usam a mesma lista de domínios:
o checkout, o quiz e a área da compra da Música e a Estante validam do mesmo jeito."""
import re
from pathlib import Path

from web import email_validacao

JS = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'email-validacao.js'


def test_lista_de_dominios_igual_no_navegador_e_no_servidor():
    bloco = re.search(r'const DOMINIOS_COMUNS = \[(.*?)\];', JS.read_text(), re.S).group(1)
    assert re.findall(r"'([^']+)'", bloco) == email_validacao.DOMINIOS_COMUNS


def test_todas_as_telas_com_email_usam_o_mesmo_arquivo():
    raiz = JS.parents[2] / 'app'
    for tela in ('templates/checkout.html', 'templates/checkout-2.html', 'templates/_estante_guardar.html',
                 'musica/templates/musica/quiz.html', 'musica/templates/musica/compra.html'):
        html = (raiz / tela).read_text()
        assert "filename='js/email-validacao.js'" in html, tela
        assert 'const DOMINIOS_COMUNS' not in html, tela   # sem cópia da lista dentro da tela


def test_mexico_nao_e_barrado_e_erro_de_digitacao_continua_barrado(monkeypatch):
    monkeypatch.setattr(email_validacao, '_dominio_existe', lambda d: None)
    assert email_validacao.validar_email('lupita@yahoo.com.mx')['valido']
    assert email_validacao.validar_email('ana@hotmail.com.br')['valido']
    for errado in ('ana@gmail.comb', 'ana@gmail.coml', 'ana@gmail.com.br'):
        r = email_validacao.validar_email(errado)
        assert not r['valido'] and r['sugestao'] == 'gmail.com', errado


def test_checkout_carrega_a_validacao_mesmo_sem_cartao():
    """O script da validação fica fora do {% if config_cartao %}: produto só com PIX também precisa dele."""
    raiz = JS.parents[2] / 'app' / 'templates'
    for tela in ('checkout.html', 'checkout-2.html'):
        html = (raiz / tela).read_text()
        script = html.index("filename='js/email-validacao.js'")
        bloco_cartao = html.rfind('{% if config_cartao %}', 0, script)
        assert bloco_cartao == -1 or '{% endif %}' in html[bloco_cartao:script], tela


def test_provedor_com_versao_do_pais_passa_e_gmail_com_br_nao(monkeypatch):
    monkeypatch.setattr(email_validacao, '_dominio_existe', lambda d: None)
    for ok in ('maria@hotmail.com.ar', 'lupita@outlook.com.mx', 'ana@yahoo.com.ar', 'jose@live.com.mx'):
        r = email_validacao.validar_email(ok)
        assert r['valido'] and r['sugestao'] is None, ok   # sem "você quis dizer outlook.com.br?"
    for errado in ('ana@gmail.com.br', 'ana@hotmail.comm', 'ana@hotmail.com.brr'):
        assert not email_validacao.validar_email(errado)['valido'], errado


def test_navegador_tem_a_mesma_lista_de_provedores_com_pais():
    js = JS.read_text()
    bloco = re.search(r'const PROVEDORES_COM_PAIS = \[(.*?)\];', js, re.S).group(1)
    assert re.findall(r"'([^']+)'", bloco) == email_validacao.PROVEDORES_COM_PAIS
