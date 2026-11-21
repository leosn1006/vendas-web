"""Tela de lembranças com uma caixa só (20/11/2026): frases para começar, medidor e exemplos por relação, o texto
livre nas respostas e o microfone (fala → texto, sem guardar o áudio). docs/MUSICA.md, o quiz."""
import io
from pathlib import Path

import pytest
from flask import Flask

from musica import casos_de_uso as uc
from musica import rotas
from musica.casos_de_uso import Recusa
from musica.dominio import quiz, regras
from tests.musica.test_rotas_idiomas import PLANOS, PRODUTOS

AUDIO = b'\x1aE\xdf\xa3' + b'0' * 4000   # "webm" de mentira (o ditado do teste não lê o conteúdo)


def test_cada_guia_tem_frases_para_comecar_medidor_e_dica_nos_dois_idiomas():
    for idioma in ('pt-BR', 'es-MX'):
        q = quiz.do_idioma(idioma)
        for guia, g in q.LEMBRANCAS.items():
            assert len(g['inicios']) == 3 and len(g['medidor']) == 4 and g['dica'], (idioma, guia)


def test_exemplos_pela_relacao_com_a_guia_de_reserva():
    q = quiz.do_idioma('pt-BR')
    cfg = q.config_do_navegador()['exemplos_lembrancas']
    assert len(cfg['Esposa']) == 2 and 'ônibus' in cfg['Esposa'][0]
    assert cfg['Pai'] == q.EXEMPLOS_LEMBRANCAS['_padrao']                 # sem exemplo próprio: o da guia
    assert cfg['Mais de uma pessoa'] == q.EXEMPLOS_LEMBRANCAS['_grupo']
    assert cfg['Para mim'] == q.EXEMPLOS_LEMBRANCAS['_eu']
    assert all(cfg[r['valor']] for r in q.RELACOES)                       # toda relação tem exemplo
    mx = quiz.do_idioma('es-MX').config_do_navegador()['exemplos_lembrancas']
    assert mx['Esposa'] == quiz.do_idioma('es-MX').EXEMPLOS_LEMBRANCAS['_casal']


def test_texto_livre_ate_2500_e_o_formato_antigo_ainda_vale():
    longo = 'a' * 3000
    r = regras.montar_respostas({'para_quem': 'Esposa', 'nome': 'Rose', 'lembrancas': longo},
                                quiz.CHAVES_VALIDAS, quiz.MAX_PESSOAS)
    assert r['lembrancas'] == 'a' * 2500
    antigo = regras.montar_respostas({'nome': 'Rose', 'lembrancas_partes': [{'pergunta': 'P', 'resposta': 'R'}]},
                                     quiz.CHAVES_VALIDAS, quiz.MAX_PESSOAS)
    assert antigo['lembrancas'] == 'P: R'


class DitadoQueGuarda:
    def __init__(self, texto='Nos conhecemos no forró.'):
        self.texto_fixo, self.arquivos = texto, []

    def texto(self, arquivo, idioma='pt', dica=''):
        assert Path(arquivo).exists()
        self.arquivos.append((Path(arquivo), idioma, dica))
        return self.texto_fixo


def test_transcrever_devolve_o_texto_e_apaga_o_audio(s):
    s.ditado = DitadoQueGuarda('  Nos conhecemos\n no forró.  ')
    assert uc.transcrever(s, io.BytesIO(AUDIO), 'audio/webm;codecs=opus', 'pt-BR', 'Rose') == 'Nos conhecemos no forró.'
    arquivo, idioma, dica = s.ditado.arquivos[0]
    assert arquivo.suffix == '.webm' and idioma == 'pt' and dica == 'Rose'
    assert not arquivo.exists()                                           # o áudio não fica guardado
    uc.transcrever(s, io.BytesIO(AUDIO), 'audio/mp4', 'es-MX')            # iPhone; espanhol
    assert s.ditado.arquivos[1][0].suffix == '.mp4' and s.ditado.arquivos[1][1] == 'es'


def test_transcrever_recusa_formato_toque_curto_silencio_e_falha(s):
    with pytest.raises(Recusa, match='Formato'):
        uc.transcrever(s, io.BytesIO(AUDIO), 'video/quicktime')
    with pytest.raises(Recusa, match='entender'):
        uc.transcrever(s, io.BytesIO(b'curto'), 'audio/webm')
    s.ditado = DitadoQueGuarda('   ')
    with pytest.raises(Recusa, match='entender'):
        uc.transcrever(s, io.BytesIO(AUDIO), 'audio/webm')

    class Quebrado:
        def texto(self, *a, **k):
            raise TimeoutError('OpenAI fora')
    s.ditado = Quebrado()
    with pytest.raises(Recusa) as erro:
        uc.transcrever(s, io.BytesIO(AUDIO), 'audio/webm')
    assert erro.value.status == 503


@pytest.fixture
def cliente(s, monkeypatch):
    monkeypatch.setattr(rotas, 'servicos', lambda: s)
    monkeypatch.setattr(rotas, '_produto', lambda idioma=None: PRODUTOS.get(idioma or rotas._idioma()))
    monkeypatch.setattr(rotas, '_planos_a_venda', lambda: PLANOS)
    monkeypatch.setattr(rotas, '_origem_confiavel', lambda: True)
    monkeypatch.setattr(rotas, '_ditado_excedido', lambda: False)
    app = Flask('teste')
    from musica import registrar
    registrar(app)
    return app.test_client()


def _enviar(cliente, conteudo=AUDIO, caminho='/musica/api/ditado'):
    return cliente.post(caminho, data={'audio': (io.BytesIO(conteudo), 'fala', 'audio/webm'), 'dica': 'Rose'},
                        content_type='multipart/form-data')


def test_rota_do_microfone(cliente, monkeypatch):
    r = _enviar(cliente)
    assert r.status_code == 200 and r.get_json()['texto'].startswith('A gente se conheceu')
    assert _enviar(cliente, caminho='/mx/cancion/api/ditado').status_code == 200          # México também
    assert cliente.post('/musica/api/ditado', data={}, content_type='multipart/form-data').status_code == 400
    assert _enviar(cliente, b'0' * (1024 * 1024 + 10)).status_code == 413
    monkeypatch.setattr(rotas, '_origem_confiavel', lambda: False)
    assert _enviar(cliente).status_code == 403


def test_rota_do_microfone_respeita_o_limite(cliente, monkeypatch):
    monkeypatch.setattr(rotas, '_ditado_excedido', lambda: True)
    r = _enviar(cliente)
    assert r.status_code == 429 and 'gravou bastante' in r.get_json()['erro']


class RedisFalso:
    def __init__(self):
        self.contas = {}

    def set(self, chave, valor, ex=None, nx=False):
        self.contas.setdefault(chave, valor)

    def incr(self, chave):
        self.contas[chave] += 1
        return self.contas[chave]


def test_limite_do_microfone_por_ip_e_recusa_sem_redis(monkeypatch):
    import web.cielo
    from musica import config
    falso = RedisFalso()
    monkeypatch.setattr(web.cielo, '_redis', lambda: falso)
    monkeypatch.setattr(config, 'DITADO_POR_HORA', 2)
    app = Flask('teste')
    with app.test_request_context(headers={'X-Real-IP': '9.9.9.9'}):
        assert [rotas._ditado_excedido() for _ in range(3)] == [False, False, True]
    def sem_redis():
        raise ConnectionError('redis fora')
    monkeypatch.setattr(web.cielo, '_redis', sem_redis)
    with app.test_request_context():
        assert rotas._ditado_excedido() is True   # limite de custo: sem Redis, recusa


def test_quiz_traz_a_tela_nova(cliente):
    html = cliente.get('/musica/criar').get_data(as_text=True)
    assert 'Conte a história de vocês' in html and '"exemplos_lembrancas"' in html and '/musica/api/ditado' in html


def test_toque_sem_querer_e_formato_errado_nao_gastam_a_cota(cliente, monkeypatch):
    contou = []
    monkeypatch.setattr(rotas, '_ditado_excedido', lambda: contou.append(1) or False)
    curto = cliente.post('/musica/api/ditado', data={'audio': (io.BytesIO(b'x' * 50), 'fala', 'audio/webm')},
                         content_type='multipart/form-data')
    errado = cliente.post('/musica/api/ditado', data={'audio': (io.BytesIO(AUDIO), 'fala', 'video/quicktime')},
                          content_type='multipart/form-data')
    assert curto.status_code == 400 and errado.status_code == 400 and not contou
    assert _enviar(cliente).status_code == 200 and contou == [1]


def test_limitador_do_checkout_continua_sem_bloquear_venda_sem_redis(monkeypatch):
    import web.cielo
    from web.checkout import _excedeu_limite_ip
    def sem_redis():
        raise ConnectionError('redis fora')
    monkeypatch.setattr(web.cielo, '_redis', sem_redis)
    assert _excedeu_limite_ip('sop_token', '1.2.3.4', 30, 600) is False
    assert _excedeu_limite_ip('musica_ditado', '1.2.3.4', 15, 3600, sem_redis_bloqueia=True) is True
