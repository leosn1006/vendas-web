"""Link curto /m/<codigo> (docs/SMS.md): 7 caracteres sem os que se confundem, maiúscula ≠ minúscula, cada acesso
registrado e robô não conta como clique."""
import pytest
from flask import Flask

import links_curtos

NAVEGADOR = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1',
             'X-Real-IP': '177.1.2.3'}


@pytest.fixture
def cliente(banco):
    app = Flask(__name__)
    app.register_blueprint(links_curtos.bp)
    return app.test_client()


def test_codigo():
    codigos = {links_curtos.gerar_codigo() for _ in range(3000)}
    assert len(codigos) == 3000
    assert all(len(c) == 7 and set(c) <= set(links_curtos.ALFABETO) for c in codigos)
    assert not set('0O1lI') & set(links_curtos.ALFABETO) and len(links_curtos.ALFABETO) == 57
    assert not any(links_curtos._PROIBIDOS.search(c) for c in codigos)


def test_endereco_com_protocolo():
    """Com https:// o celular sempre faz o link clicável (sem ele, o teste de 14/11 não virou link)."""
    assert links_curtos.endereco('https://lsnlivros.com.br/', 'Ab3dEf9') == 'https://lsnlivros.com.br/m/Ab3dEf9'
    assert links_curtos.endereco('lsnlivros.com.br', 'Ab3dEf9') == 'https://lsnlivros.com.br/m/Ab3dEf9'
    assert links_curtos.endereco('http://localhost', 'Ab3dEf9') == 'http://localhost/m/Ab3dEf9'
    for vazio in ('', None, 'https://', 'https:///'):
        with pytest.raises(ValueError):
            links_curtos.endereco(vazio, 'Ab3dEf9')


def test_redireciona_e_conta_o_clique(banco, cliente):
    link = links_curtos.criar('https://lsnlivros.com.br/musica/p/tok', 'musica_lembrete', 'musica', 9)
    r = cliente.get(f"/m/{link['codigo']}", headers=NAVEGADOR)
    assert r.status_code == 302 and r.headers['Location'] == 'https://lsnlivros.com.br/musica/p/tok'
    assert banco.links[link['id']]['cliques_humanos'] == 1
    assert banco.acessos[-1] == {'codigo': link['codigo'], 'link_id': link['id'], 'ip': '177.1.2.3',
                                 'ua': NAVEGADOR['User-Agent'], 'robo': 0}


def test_maiuscula_e_minuscula_sao_codigos_diferentes(banco, cliente):
    link = links_curtos.criar('https://x.com.br/a', 'teste')
    trocado = link['codigo'].swapcase()
    r = cliente.get(f'/m/{trocado}', headers=NAVEGADOR)
    assert r.headers['Location'] == '/' and banco.acessos[-1]['link_id'] is None


@pytest.mark.parametrize('ua', ['WhatsApp/2.24.1 A', 'facebookexternalhit/1.1 Facebot Twitterbot/1.0',
                                'TelegramBot (like TwitterBot)', 'curl/8.4.0', ''])
def test_robo_nao_conta_clique(banco, cliente, ua):
    link = links_curtos.criar('https://x.com.br/a', 'teste')
    r = cliente.get(f"/m/{link['codigo']}", headers={'User-Agent': ua})
    assert r.status_code == 302 and banco.links[link['id']]['cliques_humanos'] == 0 and banco.acessos[-1]['robo'] == 1


def test_inexistente_vai_para_o_inicio_e_fica_registrado(banco, cliente):
    r = cliente.get('/m/ZZZZZZZ', headers=NAVEGADOR)
    assert r.status_code == 302 and r.headers['Location'] == '/'
    assert banco.acessos[-1]['link_id'] is None and banco.acessos[-1]['codigo'] == 'ZZZZZZZ'
