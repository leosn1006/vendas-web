"""Lembretes da Música: quem parou na letra, na prévia ou no checkout recebe e-mails 15 min, 3 h e 24 h depois de
entrar na etapa, das 8h às 22h, até ela pagar ou pedir para parar (docs/MUSICA.md "Lembretes")."""
from datetime import datetime, timedelta

import pytest

from musica import casos_de_uso as uc
from musica import config, links, mensagens
from musica.dominio import regras
from tests.musica.test_casos_de_uso import _com_previa

MINUTOS, JANELA, DIAS = config.LEMBRETES_MINUTOS, config.LEMBRETES_JANELA, config.LEMBRETES_DIAS
DIA = datetime(2026, 10, 27, 10, 0)   # dentro da janela


def _proximo(etapa, musica, agora):
    return regras.proximo_lembrete(etapa, musica, agora, MINUTOS, JANELA, DIAS)


# --------------------------------------------------------------- regras

@pytest.mark.parametrize('musica,etapa', [
    ({'status': 'letra_pronta', 'email': 'a@b.com'}, 'letra'),
    ({'status': 'previa_pronta', 'email': 'a@b.com'}, 'previa'),
    ({'status': 'previa_pronta', 'email': 'a@b.com', 'em_checkout': 1}, 'checkout'),
    ({'status': 'previa_pronta', 'email': 'a@b.com', 'liberada_em': DIA}, None),       # já paga
    ({'status': 'previa_pronta', 'email': 'a@b.com', 'sem_lembretes': 1}, None),       # pediu para parar
    ({'status': 'gerando', 'email': 'a@b.com'}, None),                                 # "outra versão" saindo
    ({'status': 'previa_pronta', 'email': None}, None),
])
def test_etapa(musica, etapa):
    assert regras.etapa_lembrete(musica) == etapa


def test_voltar_para_uma_etapa_anterior_nao_reenvia():
    """Ex.: o PIX venceu e ela volta para a prévia — a série da prévia já saiu."""
    assert _proximo('previa', {'lembrete_etapa': 'checkout', 'lembrete_desde': DIA}, DIA + timedelta(hours=1)) == (None, 0)


def test_sem_nome_nao_fica_oi_oi():
    for etapa in ('letra', 'previa', 'checkout'):
        for n in (1, 2, 3):
            _, corpo = mensagens.lembrete(etapa, n, '', 'Helena', 'x', 'y')
            assert 'Oi, Oi' not in corpo and ', .' not in corpo and '>, ' not in corpo, (etapa, n)
    _, corpo = mensagens.lembrete('letra', 2, 'Leo', 'Helena', 'x', 'y')
    assert 'Leo, você já fez' in corpo
    _, corpo = mensagens.lembrete('letra', 2, '', 'Helena', 'x', 'y')
    assert 'Você já fez' in corpo


def test_etapa_nova_zera_o_relogio_e_a_mesma_nao():
    assert _proximo('previa', {'lembrete_etapa': 'letra', 'lembrete_desde': DIA}, DIA) == ('zerar', 0)
    assert _proximo('previa', {'lembrete_etapa': None}, DIA) == ('zerar', 0)
    # "outra versão": prévia → gerando → prévia de novo continua de onde estava
    assert _proximo('previa', {'lembrete_etapa': 'previa', 'lembrete_desde': DIA, 'lembretes_enviados': 1},
                    DIA + timedelta(minutes=20)) == (None, 0)


@pytest.mark.parametrize('depois,enviados,acao', [
    (timedelta(minutes=10), 0, (None, 0)),
    (timedelta(minutes=15), 0, ('enviar', 1)),
    (timedelta(hours=2), 1, (None, 0)),
    (timedelta(hours=3), 1, ('enviar', 2)),
    (timedelta(hours=24), 2, ('enviar', 3)),
    (timedelta(hours=30), 3, (None, 0)),           # acabou a sequência
    (timedelta(hours=5), 0, ('enviar', 2)),        # venceram dois: sai só o mais recente
    (timedelta(days=3, minutes=1), 2, (None, 0)),  # passou da validade
])
def test_tempos(depois, enviados, acao):
    desde = DIA - depois
    assert _proximo('letra', {'lembrete_etapa': 'letra', 'lembrete_desde': desde, 'lembretes_enviados': enviados},
                    DIA) == acao


def test_fora_do_horario_espera_a_manha():
    desde = datetime(2026, 10, 27, 22, 30)   # entrou na etapa às 22h30
    musica = {'lembrete_etapa': 'previa', 'lembrete_desde': desde, 'lembretes_enviados': 0}
    assert _proximo('previa', musica, datetime(2026, 10, 27, 23, 0)) == (None, 0)
    assert _proximo('previa', musica, datetime(2026, 10, 28, 7, 55)) == (None, 0)
    assert _proximo('previa', musica, datetime(2026, 10, 28, 8, 0)) == ('enviar', 2)   # 9h30 depois: só o de 3 h


# ------------------------------------------------------------ caso de uso

def _na_etapa(s, etapa):
    musica = _com_previa(s)
    if etapa == 'letra':
        s.repositorio.atualizar(musica['id'], status='letra_pronta')
    if etapa == 'checkout':
        uc.checkout_aberto(s, musica['token'])
        s.repositorio.atualizar(musica['id'], pedido_aberto_id=777, pedido_aberto_plano='videoclipe')
    return s.repositorio.por_id(musica['id'])


def _rodar(s, monkeypatch, agora):
    monkeypatch.setattr(uc, '_agora', lambda: agora)
    return uc.enviar_lembretes(s)


@pytest.mark.parametrize('etapa', ['letra', 'previa', 'checkout'])
def test_tres_emails_por_etapa(s, monkeypatch, etapa):
    musica = _na_etapa(s, etapa)
    assert _rodar(s, monkeypatch, DIA) == 0                                   # entrou na etapa: só zera o relógio
    assert s.repositorio.por_id(musica['id'])['lembrete_etapa'] == etapa
    for depois in (timedelta(minutes=15), timedelta(hours=3), timedelta(hours=24)):
        assert _rodar(s, monkeypatch, DIA + depois) == 1
        assert _rodar(s, monkeypatch, DIA + depois + timedelta(minutes=5)) == 0   # nada repetido
    assert len(s.notificador.emails) == 3
    destino = {e['destino'] for e in s.notificador.emails}
    assert destino == {musica['email']}
    assunto_1 = mensagens.lembrete(etapa, 1, '', regras.para_quem(musica['respostas']), 'x', 'y')[0]
    assert s.notificador.emails[0]['assunto'] == assunto_1
    html = s.notificador.emails[0]['html']
    assert f"/musica/p/{musica['token']}/sem-lembretes" in html
    if etapa == 'checkout':
        assert f"/pay/{musica['produto_id']}?pedido=777&amp;plano=videoclipe&amp;musica={musica['token']}" in html
    else:
        assert f"/musica/p/{musica['token']}" in html


def test_avancar_de_etapa_troca_a_sequencia(s, monkeypatch):
    musica = _na_etapa(s, 'letra')
    _rodar(s, monkeypatch, DIA)
    _rodar(s, monkeypatch, DIA + timedelta(minutes=15))                       # 1º da letra
    s.repositorio.atualizar(musica['id'], status='previa_pronta')             # criou a música e ouviu
    _rodar(s, monkeypatch, DIA + timedelta(minutes=20))                       # zera na prévia
    _rodar(s, monkeypatch, DIA + timedelta(minutes=35))                       # 1º da prévia
    assuntos = [e['assunto'] for e in s.notificador.emails]
    assert assuntos[0].startswith('A letra de') and assuntos[1].startswith('Gostou da música de')


def test_pagou_ou_pediu_para_parar_nao_recebe_mais(s, monkeypatch):
    paga, parou = _na_etapa(s, 'previa'), _na_etapa(s, 'previa')
    _rodar(s, monkeypatch, DIA)
    s.repositorio.atualizar(paga['id'], liberada_em=DIA)
    assert uc.parar_lembretes(s, parou['token'])
    assert _rodar(s, monkeypatch, DIA + timedelta(hours=1)) == 0
    assert s.repositorio.por_id(parou['id'])['sem_lembretes'] == 1


def test_varias_musicas_do_mesmo_email_recebem_um_lembrete_so(s, monkeypatch):
    """A cliente que fez 4 músicas em 20 min (3 prévias e 1 letra) recebe um e-mail, da prévia mais recente."""
    previas = [_na_etapa(s, 'previa') for _ in range(3)]
    letra = _na_etapa(s, 'letra')
    for m in previas + [letra]:
        s.repositorio.atualizar(m['id'], email='Maria@Gmail.com' if m is letra else 'maria@gmail.com')
    _rodar(s, monkeypatch, DIA)
    assert _rodar(s, monkeypatch, DIA + timedelta(minutes=15)) == 1
    assert _rodar(s, monkeypatch, DIA + timedelta(minutes=30)) == 0
    assert f"/musica/p/{previas[-1]['token']}" in s.notificador.emails[0]['html']


def test_checkout_ganha_de_previa_mais_nova_do_mesmo_email():
    musicas = [{'id': 1, 'email': 'a@b.com', 'status': 'previa_pronta', 'em_checkout': 1},
               {'id': 2, 'email': 'a@b.com', 'status': 'previa_pronta'},
               {'id': 3, 'email': 'outra@b.com', 'status': 'letra_pronta'}]
    assert [(m['id'], e) for m, e in regras.uma_por_email(musicas)] == [(1, 'checkout'), (3, 'letra')]


def test_link_do_checkout_sem_pedido_aberto():
    m = {'token': 'f' * 32, 'produto_id': 17, 'dominio': 'lsnlivros.com.br'}
    assert links.checkout(m).endswith(f"/pay/17?musica={'f' * 32}")


def test_checkout_aberto_grava_so_a_primeira_vez(s, monkeypatch):
    musica = _com_previa(s)
    monkeypatch.setattr(uc, '_agora', lambda: DIA)
    uc.checkout_aberto(s, musica['token'])
    monkeypatch.setattr(uc, '_agora', lambda: DIA + timedelta(hours=2))
    uc.checkout_aberto(s, musica['token'])
    assert s.repositorio.por_id(musica['id'])['checkout_aberto_em'] == DIA


def test_pix_da_musica_sai_do_lembrete_generico():
    """Pedido de música não recebe o e-mail genérico de PIX: a etapa checkout dos lembretes cuida dele."""
    import inspect
    import database
    assert 'musica_pedidos' in inspect.getsource(database.buscar_pedidos_followup_pagamento_web)
