"""Regras puras da Música (sem banco, sem provedor)."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta

import pytest

from musica.adaptadores.gerador_apiframe import GeradorApiframe, interpretar_job
from musica.dominio import legenda, regras
from musica.dominio.modelos import GERACAO_ANDAMENTO, GERACAO_FALHOU, GERACAO_PRONTA
from musica.dominio.recursos import papel_permitido
from tests.musica.conftest import RESPOSTAS


def test_estilo_que_saiu_do_quiz_vira_o_de_hoje_na_criacao_e_na_leitura():
    from musica.adaptadores.repositorio_mysql import _musica
    from musica.dominio.quiz import CHAVES_VALIDAS, MAX_PESSOAS
    for antigo, atual in (('arrocha', 'sertanejo'), ('sertanejo_raiz', 'sertanejo'), ('piseiro', 'forro'), ('rock', 'rock')):
        assert regras.montar_respostas({'estilo': antigo}, CHAVES_VALIDAS, MAX_PESSOAS)['estilo'] == atual
        assert _musica({'respostas': f'{{"estilo": "{antigo}"}}'})['respostas']['estilo'] == atual


def test_montar_geracao_junta_estilo_clima_e_voz(s):
    pedido = regras.montar_geracao(RESPOSTAS, 'Pra Você, Dona Lena', '[Chorus]\nLena', s.estilos)
    assert pedido.titulo == 'Pra Você, Dona Lena'
    assert pedido.estilo.startswith(s.estilos['estilos']['sertanejo'])
    assert s.estilos['clima']['emocionante'] in pedido.estilo
    assert pedido.genero_vocal == s.estilos['voz']['feminina']['genero_vocal']
    assert pedido.negativo == s.estilos['negativo'] + ', ' + s.estilos['negativo_estilo']['sertanejo']


def test_estilo_desconhecido_usa_pop(s):
    pedido = regras.montar_geracao({'estilo': 'xx', 'clima': 'yy', 'voz': 'zz'}, '', 'letra', s.estilos)
    assert pedido.estilo.startswith(s.estilos['estilos']['pop'])
    assert pedido.titulo == 'Música de presente'


@pytest.mark.parametrize('duracao,inicio', [(180, 35), (75, 35), (60, 20), (30, 0), (None, 0)])
def test_previa_comeca_perto_do_refrao(duracao, inicio):
    assert regras.inicio_previa(duracao, 40) == inicio


def test_para_leitura_tira_marcacoes_e_marca_o_refrao():
    texto = '[Verse 1]\nEra domingo\n\n[Pre-Chorus]\nE eu lembro\n\n[Chorus]\nLena, Lena'
    assert regras.para_leitura(texto) == 'Era domingo\n\nE eu lembro\n\n(Refrão)\nLena, Lena'


def test_para_quem_prefere_o_apelido():
    assert regras.para_quem(RESPOSTAS) == 'Dona Lena'
    assert regras.para_quem({'nome': 'Helena'}) == 'Helena'
    assert regras.para_quem({}) == 'quem você ama'


def test_travou_depois_do_limite():
    agora = datetime(2026, 10, 17, 12, 0)
    assert regras.travou(agora - timedelta(minutes=7), agora, 6)
    assert not regras.travou(agora - timedelta(minutes=5), agora, 6)
    assert not regras.travou(None, agora, 6)


@pytest.mark.parametrize('nome,email,quando,erro', [
    ('', 'a@b.com', None, 'nome'),
    ('Lena', 'sem-arroba', None, 'e-mail'),
    ('Lena', 'a@b.com', datetime(2026, 10, 17, 11, 0), 'horário'),       # passado
    ('Lena', 'a@b.com', datetime(2027, 3, 1, 9, 0), 'horário'),          # mais de 90 dias
    ('Lena', 'a@b.com', None, None),                                      # agora
    ('Lena', 'a@b.com', datetime(2026, 10, 25, 0, 0), None),              # meia-noite do aniversário
])
def test_validar_presente(nome, email, quando, erro):
    resultado = regras.validar_presente(nome, email, quando, datetime(2026, 10, 17, 12, 0))
    assert (resultado is None) if erro is None else (erro in resultado.lower())


@pytest.mark.parametrize('recurso,papel,ok', [
    ('musica', 'principal', True), ('videoclipe', 'principal', True), ('qrcode', 'bump', True),
    ('entrega_email', 'bump', True), ('musica', 'bump', False), ('qrcode', 'principal', False),
    ('qrcode', 'bonus', False), ('inexistente', 'principal', False),
])
def test_papel_do_recurso_no_plano(recurso, papel, ok):
    assert papel_permitido(recurso, papel) is ok


def test_legenda_encaixa_as_linhas_nos_tempos():
    linhas = legenda.linhas_da_letra('[Verse]\nEra domingo de manhã\n\n[Chorus]\n(Lena) minha flor')
    assert linhas == ['Era domingo de manhã', 'Lena minha flor']
    palavras = [{'palavra': p, 'inicio': i, 'fim': i + 0.5} for i, p in
                enumerate(['era', 'domingo', 'de', 'manha', 'uh', 'lena', 'minha', 'flor'])]
    tempos = legenda.alinhar(linhas, palavras)
    assert [t[2] for t in tempos] == linhas
    assert tempos[0][0] == 0 and tempos[1][0] == 5


# ------------------------------------------------------------------ Apiframe (borda)

def test_apiframe_interpreta_os_status():
    pronto = interpretar_job({'status': 'COMPLETED', 'result': {'tracks': [{'audioUrl': 'u1', 'duration': 150}]}})
    assert pronto.status == GERACAO_PRONTA and pronto.faixas[0].url == 'u1'
    assert interpretar_job({'status': 'FAILED', 'error': 'x'}).status == GERACAO_FALHOU
    assert interpretar_job({'status': 'PROCESSING'}).status == GERACAO_ANDAMENTO


def test_apiframe_confere_a_assinatura_do_webhook():
    g = GeradorApiframe('chave-secreta', 'V5_5')
    corpo = json.dumps({'jobId': 'job-1', 'status': 'COMPLETED'}).encode()
    segredo = hashlib.sha256(b'chave-secreta').hexdigest().encode()
    assinatura = hmac.new(segredo, corpo, hashlib.sha256).hexdigest()
    assert g.webhook_valido(corpo, {'X-Webhook-Signature': assinatura}) == 'job-1'
    assert g.webhook_valido(corpo, {'X-Webhook-Signature': 'sha256=' + assinatura}) == 'job-1'
    assert g.webhook_valido(corpo, {'X-Webhook-Signature': 'errada'}) is None
    assert g.webhook_valido(corpo, {}) is None
