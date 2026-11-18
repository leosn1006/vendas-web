"""As páginas da Música por idioma (Flask de verdade, banco e provedores falsos): /musica em português, /mx/cancion em
espanhol, a música respondendo no idioma DELA por qualquer endereço, e o Brasil sem mudança."""
import pytest
from flask import Flask

from musica import casos_de_uso as uc
from musica import rotas
from tests.musica.conftest import RESPOSTAS
from tests.musica.test_idiomas import RESPOSTAS_MX

PRODUTOS = {'pt-BR': {'id': 17, 'nome': 'Música de Presente', 'email_nome_remetente': 'Canção de Presente'},
            'es-MX': {'id': 30, 'nome': 'Canción MX', 'email_nome_remetente': 'Canción de Regalo'}}
PLANOS = [{'slug': 'musica', 'nome': 'Música', 'descricao': '', 'preco': 19.9, 'videoclipe': False,
           'plano': {'id': 18, 'produto_id': 17, 'slug': 'musica', 'padrao': 1, 'desconto_oferta': 0}}]


@pytest.fixture
def cliente(s, monkeypatch):
    monkeypatch.setattr(rotas, 'servicos', lambda: s)
    monkeypatch.setattr(rotas, '_produto', lambda idioma=None: PRODUTOS.get(idioma or rotas._idioma()))
    monkeypatch.setattr(rotas, '_planos_a_venda', lambda: PLANOS)
    monkeypatch.setattr(rotas, '_empresa', lambda: {'razao_social': 'LBE', 'cnpj': '1', 'email_suporte': 'a@b.c'})
    monkeypatch.setattr(rotas, '_rascunho_do_funil', lambda: None)
    monkeypatch.setattr(rotas, '_pedido_origem', lambda: None)
    monkeypatch.setattr(rotas, '_origem_confiavel', lambda: True)
    monkeypatch.setattr(rotas, '_turnstile_ok', lambda token: True)
    app = Flask('teste')
    from musica import registrar
    registrar(app)
    return app.test_client()


def _previa(s, idioma, respostas):
    musica = uc.criar_musica(s, 30 if idioma == 'es-MX' else 17, dict(respostas), 'a@b.com', '', '1.2.3.4',
                             idioma=idioma)
    s.repositorio.atualizar(musica['id'], status='previa_pronta', titulo='T', letra_exibicao='[Chorus]\nOi',
                            faixas=[{'numero': 1}, {'numero': 2}])
    return musica['token']


def test_landing_e_quiz_do_mexico_em_espanhol(cliente):
    r = cliente.get('/mx/cancion/')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'lang="es-MX"' in html and '¿Para quién es la canción?' in html
    assert 'href="/mx/cancion/crear"' in html and 'Canción de Regalo' in html
    assert 'id="exemplos"' in html and '/musica/static/exemplos/es-MX/mama-lupita.mp3' in html   # exemplos em espanhol
    assert 'Lupita, mi raíz' in html and 'mae-rosa.mp3' not in html   # nenhum exemplo do Brasil no México
    assert 'La historia de tu mamá' in cliente.get('/mx/cancion/?ocasion=mama').get_data(as_text=True)
    quiz = cliente.get('/mx/cancion/crear').get_data(as_text=True)
    assert '"chave_rascunho": "cancion_quiz_mx"' in quiz and 'Mariachi / Ranchera' in quiz and 'musica-mx' in quiz
    assert 'Aviso de privacidad' in cliente.get('/mx/cancion/privacidad').get_data(as_text=True)


def test_brasil_continua_em_portugues_e_sem_o_seletor_do_mexico_ate_o_lancamento(cliente):
    """Com o produto do México ativo (para mostrar o site), a landing que vende no Brasil não ganha link para lá."""
    html = cliente.get('/musica/').get_data(as_text=True)
    assert 'lang="pt-BR"' in html and 'Pra quem é a música?' in html and 'href="/musica/criar"' in html
    assert 'México' not in html
    assert 'lang="pt-BR">🇧🇷 Brasil' in cliente.get('/mx/cancion/').get_data(as_text=True)


@pytest.mark.parametrize('caminho', ['/musica/crear', '/musica/terminos', '/musica/privacidad',
                                     '/mx/cancion/criar', '/mx/cancion/termos', '/mx/cancion/privacidade'])
def test_endereco_de_outro_idioma_nao_existe(cliente, caminho):
    assert cliente.get(caminho).status_code == 404


def test_valores_trocados_nos_textos_sao_escapados(cliente):
    from flask import Flask
    app = Flask('t2')
    with app.test_request_context('/'):
        from flask import g
        g.idioma = 'pt-BR'
        assert str(rotas._t('geral.og_titulo', marca='<script>x</script>')).startswith('&lt;script&gt;')


def test_quiz_do_mexico_cria_a_musica_em_espanhol_com_celular_mexicano(cliente, s):
    corpo = {'respostas': {**RESPOSTAS_MX, 'pessoas': [{'nome': 'Guadalupe', 'apelido': 'Lupita'}],
                           'lembrancas_partes': [{'pergunta': 'Un recuerdo', 'resposta': 'El pozole de los domingos'}]},
             'email': 'p@ejemplo.com', 'whatsapp': '55 1234 5678'}
    r = cliente.post('/mx/cancion/api/musicas', json=corpo)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['link'].startswith('/mx/cancion/p/')
    musica = s.repositorio.por_token(r.get_json()['token'])
    assert musica['idioma'] == 'es-MX' and musica['produto_id'] == 30 and musica['whatsapp'] == '525512345678'
    r = cliente.post('/mx/cancion/api/musicas', json={**corpo, 'whatsapp': '11 91234-5678'})
    assert r.status_code == 400 and 'Revisa tu celular' in r.get_json()['erro']


def test_quiz_do_mexico_recusa_resposta_do_quiz_do_brasil(cliente):
    corpo = {'respostas': {**RESPOSTAS, 'pessoas': [{'nome': 'Helena'}],
                           'lembrancas_partes': [{'pergunta': 'x', 'resposta': 'bolo de fubá aos domingos'}]},
             'email': 'p@ejemplo.com'}
    r = cliente.post('/mx/cancion/api/musicas', json=corpo)
    assert r.status_code == 400 and 'Falta alguna respuesta' in r.get_json()['erro']


def test_previa_do_mexico_em_espanhol_por_qualquer_endereco_e_sem_checkout_em_reais(cliente, s):
    token = _previa(s, 'es-MX', RESPOSTAS_MX)
    for caminho in (f'/mx/cancion/api/musicas/{token}', f'/musica/api/musicas/{token}'):
        dados = cliente.get(caminho).get_json()
        assert dados['letra'].startswith('(Coro)') and dados['planos'] == [] and dados['oferta'] is None
        assert dados['previas'][0].startswith('/mx/cancion/previa/')
    pagina = cliente.get(f'/musica/p/{token}').get_data(as_text=True)
    assert 'lang="es-MX"' in pagina and '"venda_fechada": "Por ahora no estamos vendiendo.' in pagina


def test_previa_do_brasil_continua_com_o_nosso_checkout(cliente, s):
    token = _previa(s, 'pt-BR', RESPOSTAS)
    dados = cliente.get(f'/musica/api/musicas/{token}').get_json()
    assert dados['letra'].startswith('(Refrão)')
    assert dados['planos'][0]['link'] == f'/pay/17?musica={token}' and dados['planos'][0]['preco'].startswith('R$')


def test_erro_dos_casos_de_uso_sai_no_idioma_da_musica(cliente, s):
    token = _previa(s, 'es-MX', RESPOSTAS_MX)   # prévia pronta: "criar a música" de novo é recusado
    r = cliente.post(f'/mx/cancion/api/musicas/{token}/gerar')
    assert r.status_code == 400 and r.get_json()['erro'] == 'Esta canción ya se está creando.'
    token_br = _previa(s, 'pt-BR', RESPOSTAS)
    r = cliente.post(f'/musica/api/musicas/{token_br}/gerar')
    assert r.get_json()['erro'] == 'Esta música já está sendo criada.'
