"""Fase 2 dos idiomas: o pós-compra (área da compra, presente, cartão, vídeo, e-mails) no idioma da música e no
horário do país dela; o Brasil igual a antes."""
import io
import json
from datetime import datetime

import pytest
from flask import Flask

from musica import casos_de_uso as uc
from musica import config, idiomas, integracao, links, mensagens, rotas
from musica.adaptadores import video_ffmpeg
from musica.dominio import regras
from tests.musica.conftest import RESPOSTAS
from tests.musica.test_idiomas import RESPOSTAS_MX

PRODUTO = 30


def _paga(s, idioma='es-MX', recursos=('musica', 'entrega_email', 'videoclipe', 'qrcode'), guid='g-mx'):
    """Uma música do idioma, com a prévia pronta e paga (o mesmo caminho que a Hotmart vai usar: vincular + liberar)."""
    respostas = RESPOSTAS_MX if idioma == 'es-MX' else RESPOSTAS
    musica = uc.criar_musica(s, PRODUTO, dict(respostas), 'patricia@ejemplo.com', '', '1.2.3.4', idioma=idioma)
    uc.escrever_letra(s, musica['id'])
    uc.gerar(s, musica['token'], '1.2.3.4')
    uc.consultar(s, musica['id'])
    s.repositorio.pedidos[700] = {'id': 700, 'guid': guid, 'email': 'patricia@ejemplo.com', 'estado_id': 1000,
                                  'dns_origem': 'site.com', 'contact_name': 'Patricia López'}
    s.repositorio.itens[700] = list(recursos)
    uc.vincular_ao_pedido(s, musica['token'], 700, PRODUTO)
    assert uc.liberar_do_pedido(s, 700)
    return s.repositorio.por_id(musica['id'])


@pytest.fixture
def wa_ligado(monkeypatch):
    monkeypatch.setattr(config, 'WHATSAPP_ATIVO', True)


# ------------------------------------------------------------ WhatsApp por idioma

def test_whatsapp_por_idioma(wa_ligado):
    assert idiomas.whatsapp_ativo('pt-BR') is True
    assert idiomas.whatsapp_ativo('es-MX') is False   # templates só em pt_BR: desligado até os de es_MX


def test_whatsapp_desligado_no_mexico_mesmo_com_a_chave_geral_ligada(s, wa_ligado):
    musica = _paga(s)
    s.repositorio.atualizar(musica['id'], whatsapp='525512345678')
    uc.whatsapp_comprador(s, musica['id'])                                   # sem template em pt para +52
    uc.agendar_presente(s, 'g-mx', 'Lupita', 'lupita@ejemplo.com', '', None, whatsapp='55 1234 5678', confirmo=True)
    assert s.repositorio.por_id(musica['id'])['presente_whatsapp'] is None   # o número digitado é ignorado
    uc.enviar_presentes(s)
    assert s.notificador.whatsapps == [] and len(s.notificador.emails) == 1


# ------------------------------------------------------------ e-mails em espanhol

def test_presente_por_email_em_espanhol_com_link_do_mexico(s):
    musica = _paga(s)
    uc.agendar_presente(s, 'g-mx', 'Lupita', 'lupita@ejemplo.com', '¡Te quiero, mamá!', None)
    assert uc.enviar_presentes(s) == 1
    email = s.notificador.emails[0]
    assert email['assunto'] == 'Patricia te hizo una canción 🎵'
    assert '¡Hola, Lupita!' in email['html'] and '¡Te quiero, mamá!' in email['html']
    assert f"/mx/cancion/m/{musica['token']}" in email['html'] and 'Ouvir' not in email['html']


def test_presente_sem_nome_de_quem_manda_em_espanhol(s):
    musica = _paga(s)
    s.repositorio.atualizar(musica['id'], respostas={**musica['respostas'], 'de': ''})
    uc.agendar_presente(s, 'g-mx', 'Lupita', 'lupita@ejemplo.com', '', None)
    uc.enviar_presentes(s)
    assert s.notificador.emails[0]['assunto'] == 'Alguien especial te hizo una canción 🎵'


@pytest.mark.parametrize('funcao,args,trecho', [
    (mensagens.presente_nao_entregue, ('Lupita', 'l@x.com', 'https://x/m/t', 4), 'Intentamos 4 veces'),
    (mensagens.presente_whatsapp_nao_chegou, ('Lupita', 'https://x/enviar'), 'No pudimos entregar la canción'),
    (mensagens.presente_chegou, ('Patricia', 'Lupita'), 'llegó al WhatsApp de <b>Lupita</b>'),
    (mensagens.musica_atualizada, ('Patricia', 'Lupita', 'https://x/compra/g', True), 'se está volviendo a hacer'),
])
def test_avisos_para_quem_comprou_em_espanhol(funcao, args, trecho):
    assunto, corpo = funcao(*args, idioma='es-MX')
    assert trecho in corpo
    assert not any(p in assunto + corpo for p in ('música', 'você', 'não', 'Oi'))


def test_valores_dos_emails_em_espanhol_sao_escapados():
    _, corpo = mensagens.presente('<b>X</b>', 'A & B', 'T', None, 'https://x', idioma='es-MX')
    assert '&lt;b&gt;X&lt;/b&gt;' in corpo and 'A &amp; B' in corpo


def test_link_do_presente_no_whatsapp_em_espanhol():
    assert mensagens.link_do_presente('Lupita', 'Patricia', 'https://x/m/t', 'es-MX') == \
        'Dale play, Lupita 🎵\nhttps://x/m/t\n\nCon cariño, Patricia.'


def test_links_da_compra_no_prefixo_do_idioma():
    assert links.compra('g', 'site.com', 'es-MX') == 'https://site.com/mx/cancion/compra/g'
    assert links.compra('g', 'site.com') == 'https://site.com/musica/compra/g'


def test_email_de_entrega_do_mexico(s, monkeypatch):
    musica = _paga(s)
    monkeypatch.setattr(integracao, 'servicos', lambda: s)
    dados = integracao.musica_do_pedido_pago({'id': 700, 'guid': 'g-mx'})
    assert dados['idioma'] == 'es-MX' and dados['caminho'] == '/mx/cancion/compra/g-mx'
    assunto, html = integracao.email_de_entrega({'contact_name': 'Patricia López'}, dados,
                                                'https://site.com/mx/cancion/compra/g-mx', '#0700', 'Canción de Regalo',
                                                '#E11D48', '#BE123C')
    assert assunto == f"Pedido #0700 ✅ La canción de {dados['para']} está lista 🎵"
    assert '¡Hola, Patricia!' in html and 'Escuchar mi canción' in html and '/mx/cancion/compra/g-mx' in html
    assert '¿Tienes dudas? Solo responde este correo.' in html


def test_musica_do_pedido_do_brasil_continua_igual(s, monkeypatch):
    _paga(s, idioma='pt-BR', guid='g-br')
    monkeypatch.setattr(integracao, 'servicos', lambda: s)
    dados = integracao.musica_do_pedido_pago({'id': 700, 'guid': 'g-br'})
    assert dados['caminho'] == '/musica/compra/g-br' and dados['idioma'] == 'pt-BR' and dados['para'] == 'Dona Lena'


# ------------------------------------------------------------ vídeo

class TranscritorEspiao:
    def __init__(self):
        self.idiomas = []

    def palavras(self, mp3, dica, idioma='pt'):
        self.idiomas.append(idioma)
        return []


@pytest.mark.parametrize('idioma,whisper,abertura', [('es-MX', 'es', 'Una canción hecha solo para ti'),
                                                     ('pt-BR', 'pt', 'Uma música feita só para você')])
def test_video_no_idioma_da_musica(s, idioma, whisper, abertura):
    musica = _paga(s, idioma=idioma)
    s.transcritor = TranscritorEspiao()
    uc.receber_foto(s, 'g-mx', io.BytesIO(b'f1'), True)
    uc.iniciar_video(s, 'g-mx', 1, True)
    uc.fazer_video(s, musica['id'])
    assert s.transcritor.idiomas == [whisper]
    assert {**video_ffmpeg.TEXTOS_PADRAO, **s.video.textos}['abertura_sub'] == abertura


def test_textos_do_video_do_brasil_sao_os_de_antes():
    video = idiomas.textos('pt-BR')['video']
    assert {k: video[k] for k in video_ffmpeg.TEXTOS_PADRAO} == video_ffmpeg.TEXTOS_PADRAO
    assert video['titulo_padrao'] == 'Música de presente'   # o de antes dos idiomas


# ------------------------------------------------------------ horário do presente

def test_para_fuso():
    assert regras.para_fuso(datetime(2026, 12, 24, 12, 0), 'America/Sao_Paulo', 'America/Mexico_City') == \
        datetime(2026, 12, 24, 9, 0)
    assert regras.para_fuso(None, 'a', 'b') is None
    assert regras.para_fuso(datetime(2026, 1, 1), 'America/Sao_Paulo', 'America/Sao_Paulo') == datetime(2026, 1, 1)


@pytest.fixture
def cliente(s, monkeypatch):
    monkeypatch.setattr(rotas, 'servicos', lambda: s)
    monkeypatch.setattr(rotas, '_produto', lambda idioma=None: {'id': PRODUTO, 'nome': 'X', 'email_nome_remetente': 'Marca'})
    monkeypatch.setattr(rotas, '_empresa', lambda: {'razao_social': 'LBE', 'cnpj': '1', 'email_suporte': 'a@b.c'})
    monkeypatch.setattr(rotas, '_origem_confiavel', lambda: True)
    app = Flask('teste')
    from musica import registrar
    registrar(app)
    return app.test_client()


def test_presente_agendado_no_horario_do_mexico(cliente, s, wa_ligado):
    """9h na Cidade do México (o navegador manda o fuso) = 12h em Brasília no banco; a tela mostra 9h de novo."""
    musica = _paga(s)
    r = cliente.post('/mx/cancion/api/compra/g-mx/presente',
                     json={'nome': 'Lupita', 'email': 'l@x.com', 'quando': '2026-12-24T09:00:00-06:00'})
    assert r.status_code == 200, r.get_json()
    assert s.repositorio.por_id(musica['id'])['presente_em'] == datetime(2026, 12, 24, 12, 0)
    html = cliente.get('/mx/cancion/compra/g-mx').get_data(as_text=True)
    assert '<b>24/12 a las 09:00</b>' in html and 'value="09:00"' in html and 'value="2026-12-24"' in html
    assert 'en tu horario' in html and 'horário de Brasília)' not in html   # o texto visível; o JS tem um comentário
    assert 'id="pr-whats"' not in html                                          # sem campo de WhatsApp no México
    assert '"hora_com_fuso": true' in html


def test_paginas_do_pos_compra_em_espanhol(cliente, s):
    musica = _paga(s)
    compra = cliente.get('/mx/cancion/compra/g-mx').get_data(as_text=True)
    assert 'lang="es-MX"' in compra and 'Videoclip con tus fotos' in compra and 'Tarjeta con código QR' in compra
    assert 'Descargar versión 1' in compra and '(Coro)' in compra
    presente = cliente.get(f"/mx/cancion/m/{musica['token']}").get_data(as_text=True)
    assert 'Crear la mía' in presente and 'href="/mx/cancion/"' in presente and 'Descargar versión' in presente
    cartao = cliente.get('/mx/cancion/compra/g-mx/cartao').get_data(as_text=True)
    assert 'lang="es-MX"' in cartao and 'Apunta la cámara del celular' in cartao and 'Con cariño, Patricia' in cartao
    r = cliente.get('/mx/cancion/compra/g-mx/enviar')
    assert r.status_code == 302 and 'Te%20hice%20una%20canci' in r.headers['Location']


def test_erros_do_pos_compra_em_espanhol(cliente, s):
    _paga(s, recursos=('musica',))
    r = cliente.post('/mx/cancion/api/compra/g-mx/presente', json={'nome': 'L', 'email': 'l@x.com', 'agora': True})
    assert r.status_code == 403 and r.get_json()['erro'] == 'La entrega para quien la va a recibir no es parte de esta compra.'
    r = cliente.post('/mx/cancion/api/compra/g-mx/presente', json={'nome': 'L', 'quando': 'x'})
    assert r.get_json()['erro'].startswith('Elige el día y la hora')


def test_textos_do_pos_compra_completos():
    pt, es = idiomas.textos('pt-BR'), idiomas.textos('es-MX')
    assert set(pt['compra']) <= set(es['compra']) and set(pt['compra']['js']) <= set(es['compra']['js'])
    json.dumps(es['compra']['js'])


def test_agendado_vai_para_o_navegador_com_o_fuso(cliente, s):
    """No México a tela troca o horário para o fuso do navegador (o mesmo do envio): Tijuana e Cancún não veem a hora
    da Cidade do México. O servidor manda o horário com o fuso de Brasília."""
    musica = _paga(s)
    s.repositorio.atualizar(musica['id'], presente_nome='Lupita', presente_email='l@x.com',
                            presente_em=datetime(2026, 12, 24, 12, 0))
    html = cliente.get('/mx/cancion/compra/g-mx').get_data(as_text=True)
    assert 'const AGENDADO = "2026-12-24T12:00:00-03:00";' in html and 'id="pr-agendado"' in html


def test_presente_so_por_whatsapp_num_idioma_sem_whatsapp_avisa_quem_comprou(s, wa_ligado):
    """Dado antigo (ou a chave desligada depois de agendar): o WhatsApp não sai e quem comprou recebe o botão para
    mandar pelo WhatsApp dela, em espanhol — nunca "enviado" em silêncio."""
    musica = _paga(s)
    s.repositorio.atualizar(musica['id'], presente_nome='Lupita', presente_whatsapp='525512345678', presente_em=None)
    uc.enviar_presentes(s)
    assert s.notificador.whatsapps == []
    assert s.repositorio.por_id(musica['id'])['presente_wa_status'] == 'falhou'
    assert s.notificador.emails[0]['assunto'] == 'Mándale la canción a Lupita desde tu WhatsApp 🎁'
    assert '/mx/cancion/compra/g-mx/enviar' in s.notificador.emails[0]['html']


def test_titulo_padrao_do_video_no_idioma(s):
    musica = _paga(s)
    s.repositorio.atualizar(musica['id'], titulo=None)
    uc.receber_foto(s, 'g-mx', io.BytesIO(b'f1'), True)
    uc.iniciar_video(s, 'g-mx', 1, False)
    uc.fazer_video(s, musica['id'])
    assert s.video.montados[-1][1] == 'Una canción de regalo'


@pytest.mark.parametrize('idioma', [i for i in idiomas.IDIOMAS if i != idiomas.IDIOMA_PADRAO])
def test_toda_frase_de_email_usada_existe_no_idioma(idioma):
    """mensagens._txt cai no texto da chave ("emails.entrega_texto") se a frase faltar: o e-mail sairia assim para a
    cliente, sem erro. Toda chave usada no mensagens.py tem que existir em cada idioma de fora do Brasil."""
    import re
    from pathlib import Path
    codigo = (Path(mensagens.__file__)).read_text(encoding='utf-8')
    usadas = set(re.findall(r"_txt\(idioma, '(\w+)'", codigo))
    assert len(usadas) > 20
    emails = idiomas.textos(idioma)['emails']
    assert usadas <= set(emails), sorted(usadas - set(emails))
    lembretes = idiomas.textos(idioma)['lembretes']
    assert {'oi', 'oi_nome', 'rodape', 'letra', 'previa', 'checkout'} <= set(lembretes)


def test_email_de_entrega_e_avisos_declaram_o_idioma(s, monkeypatch):
    _paga(s)
    monkeypatch.setattr(integracao, 'servicos', lambda: s)
    dados = integracao.musica_do_pedido_pago({'id': 700, 'guid': 'g-mx'})
    _, html = integracao.email_de_entrega({}, dados, 'https://x', '#1', 'Marca', '#E11D48', '#BE123C')
    assert '<html lang="es-MX">' in html and '¡Hola!' in html
