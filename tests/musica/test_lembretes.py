"""Lembretes da Música: quem parou na letra, na prévia ou no checkout recebe e-mails 15 min, 3 h e 24 h depois de
entrar na etapa, das 8h às 22h. A série é da PESSOA (o e-mail), uma por etapa: no máximo 3 por etapa, 9 no total,
faça quantas músicas fizer (docs/MUSICA.md "Lembretes")."""
from datetime import datetime, timedelta

import pytest

from musica import casos_de_uso as uc
from musica import config, links, mensagens
from musica.dominio import regras
from tests.musica.test_casos_de_uso import _com_previa

MINUTOS, JANELA, DIAS = config.LEMBRETES_MINUTOS, config.LEMBRETES_JANELA, config.LEMBRETES_DIAS
DIA = datetime(2026, 10, 27, 10, 0)   # dentro da janela


def _serie(desde, enviados=0, ultimo=None, musica_id=None, inicio=None):
    return {'inicio': inicio or desde, 'desde': desde, 'enviados': enviados, 'ultimo_em': ultimo, 'musica_id': musica_id}


@pytest.fixture(autouse=True)
def relogio(s):
    s.repositorio.agora = DIA   # criado_em das músicas e a janela da compra no mesmo relógio dos testes


# --------------------------------------------------------------- regras

@pytest.mark.parametrize('musica,etapa', [
    ({'status': 'letra_pronta', 'email': 'a@b.com'}, 'letra'),
    ({'status': 'previa_pronta', 'email': 'a@b.com'}, 'previa'),
    ({'status': 'previa_pronta', 'email': 'a@b.com', 'em_checkout': 1}, 'checkout'),
    ({'status': 'previa_pronta', 'email': 'a@b.com', 'liberada_em': DIA}, None),       # já paga
    ({'status': 'gerando', 'email': 'a@b.com'}, None),                                 # "outra versão" saindo
    ({'status': 'previa_pronta', 'email': None}, None),
])
def test_etapa(musica, etapa):
    assert regras.etapa_lembrete(musica) == etapa


@pytest.mark.parametrize('depois,enviados,acao', [
    (timedelta(minutes=10), 0, (None, 0)),
    (timedelta(minutes=15), 0, ('enviar', 1)),
    (timedelta(hours=2), 1, (None, 0)),
    (timedelta(hours=3), 1, ('enviar', 2)),
    (timedelta(hours=24), 2, ('enviar', 3)),
    (timedelta(hours=5), 0, ('enviar', 2)),        # venceram dois: sai só o mais recente
])
def test_tempos(depois, enviados, acao):
    assert regras.proximo_lembrete(_serie(DIA - depois, enviados), None, DIA, MINUTOS, JANELA, DIAS) == acao


def test_sem_serie_comeca_o_relogio():
    assert regras.proximo_lembrete(None, None, DIA, MINUTOS, JANELA, DIAS) == ('zerar', 0)


def test_fora_do_horario_espera_a_manha():
    serie = _serie(datetime(2026, 10, 27, 22, 30))   # entrou na etapa às 22h30
    assert regras.proximo_lembrete(serie, None, datetime(2026, 10, 27, 23, 0), MINUTOS, JANELA, DIAS) == (None, 0)
    assert regras.proximo_lembrete(serie, None, datetime(2026, 10, 28, 7, 55), MINUTOS, JANELA, DIAS) == (None, 0)
    assert regras.proximo_lembrete(serie, None, datetime(2026, 10, 28, 8, 0), MINUTOS, JANELA, DIAS) == ('enviar', 2)


def test_intervalo_minimo_por_pessoa():
    serie = _serie(DIA - timedelta(hours=3), 1)
    assert regras.proximo_lembrete(serie, DIA - timedelta(minutes=30), DIA, MINUTOS, JANELA, DIAS, 120) == (None, 0)
    assert regras.proximo_lembrete(serie, DIA - timedelta(hours=2), DIA, MINUTOS, JANELA, DIAS, 120) == ('enviar', 2)


def _m(id_, status='previa_pronta', email='a@b.com', criado=DIA, **extra):
    return {'id': id_, 'status': status, 'email': email, 'criado_em': criado, **extra}


def test_uma_musica_por_pessoa_a_mais_avancada_e_mais_recente():
    musicas = [_m(1, em_checkout=1), _m(2), _m(3, status='letra_pronta'), _m(4, email=' Outra@b.com')]
    escolhidas = regras.escolher_lembretes(musicas, {}, DIA, MINUTOS, DIAS)
    assert sorted((m['id'], e) for m, e, _, _ in escolhidas) == [(1, 'checkout'), (4, 'previa')]


def test_serie_acabada_numa_etapa_nao_silencia_outra_etapa():
    series = {('a@b.com', 'checkout'): _serie(DIA - timedelta(days=1), 3)}
    escolhidas = regras.escolher_lembretes([_m(1, em_checkout=1), _m(2)], series, DIA, MINUTOS, DIAS)
    assert [(m['id'], e) for m, e, _, _ in escolhidas] == [(2, 'previa')]


def test_serie_acabada_so_recomeca_se_ela_voltar_dias_depois():
    series = {('a@b.com', 'previa'): _serie(DIA - timedelta(days=4), 3)}
    assert regras.escolher_lembretes([_m(1, criado=DIA - timedelta(days=4))], series, DIA, MINUTOS, DIAS) == []
    volta = regras.escolher_lembretes([_m(2, criado=DIA)], series, DIA, MINUTOS, DIAS)   # criada depois da janela
    assert [(m['id'], serie) for m, _, serie, _ in volta] == [(2, None)]


def test_musica_nova_continua_a_contagem_com_relogio_proprio():
    """Série da letra de dois dias atrás com 1 enviado; ela faz outra letra agora: o próximo é o 2º, às 3 h da música
    nova — não o de 24 h na hora."""
    series = {('a@b.com', 'letra'): _serie(DIA - timedelta(days=2), 1, DIA - timedelta(days=2), musica_id=1)}
    (musica, etapa, serie, _), = regras.escolher_lembretes([_m(2, status='letra_pronta')], series, DIA, MINUTOS, DIAS)
    assert serie['desde'] == DIA and serie['enviados'] == 1 and serie['trocou']
    assert regras.proximo_lembrete(serie, None, DIA + timedelta(minutes=20), MINUTOS, JANELA, DIAS) == (None, 0)
    assert regras.proximo_lembrete(serie, None, DIA + timedelta(hours=3), MINUTOS, JANELA, DIAS) == ('enviar', 2)


def test_musica_que_avancou_nao_volta_para_a_etapa_anterior():
    """A marca é da música (musicas.lembrete_etapa): vale mesmo que outra música dela tenha assumido a série."""
    series = {('a@b.com', 'previa'): _serie(DIA - timedelta(days=1), 1, musica_id=1),
              ('a@b.com', 'checkout'): _serie(DIA - timedelta(hours=20), 2, musica_id=2)}
    assert regras.escolher_lembretes([_m(1, lembrete_etapa='checkout')], series, DIA, MINUTOS, DIAS) == []


def test_outra_versao_da_musica_da_vez_nao_mexe_no_relogio():
    """A música da vez (4) está gerando outra versão: a mais antiga (3) não assume nem recomeça o relógio."""
    series = {('a@b.com', 'previa'): {**_serie(DIA - timedelta(hours=1), 1, musica_id=4), 'musica_status': 'gerando'}}
    assert regras.escolher_lembretes([_m(3)], series, DIA, MINUTOS, DIAS) == []
    series[('a@b.com', 'previa')]['musica_status'] = 'previa_pronta'   # a versão nova ficou pronta: a 4 segue
    (_, _, serie, _), = regras.escolher_lembretes([_m(3), _m(4)], series, DIA, MINUTOS, DIAS)
    assert serie['desde'] == DIA - timedelta(hours=1) and not serie.get('trocou')


def test_musica_da_vez_parada_em_erro_nao_trava_a_pessoa():
    series = {('a@b.com', 'previa'): {**_serie(DIA - timedelta(hours=1), 1, musica_id=4), 'musica_status': 'erro'}}
    (musica, _, serie, _), = regras.escolher_lembretes([_m(3)], series, DIA, MINUTOS, DIAS)
    assert musica['id'] == 3 and serie['trocou'] and serie['enviados'] == 1


def test_etapa_esperando_nao_trava_as_outras():
    """O checkout espera a música da vez (em produção), mas a letra de outra música dela segue."""
    series = {('a@b.com', 'checkout'): {**_serie(DIA - timedelta(hours=1), 1, musica_id=9), 'musica_status': 'gerando'}}
    escolhidas = regras.escolher_lembretes([_m(3, em_checkout=1), _m(2, status='letra_pronta')], series, DIA,
                                           MINUTOS, DIAS)
    assert [(m['id'], e) for m, e, _, _ in escolhidas] == [(2, 'letra')]


def test_marca_da_musica_so_quando_o_lembrete_sai(s, monkeypatch):
    musica = _na_etapa(s, 'checkout')
    _rodar(s, monkeypatch, DIA)                                        # só começa a série
    assert s.repositorio.por_id(musica['id'])['lembrete_etapa'] is None
    _rodar(s, monkeypatch, DIA + timedelta(minutes=15))                # 1º lembrete saiu
    assert s.repositorio.por_id(musica['id'])['lembrete_etapa'] == 'checkout'


def test_trocar_de_musica_nao_estica_a_validade():
    """O relógio recomeça na troca, mas a série vale 3 dias do início: fazer uma música nova a cada 2 dias não a
    mantém viva para sempre."""
    series = {('a@b.com', 'letra'): _serie(DIA - timedelta(hours=1), 1, musica_id=1, inicio=DIA - timedelta(days=4))}
    dentro_da_janela = DIA - timedelta(days=1, hours=12)   # criada antes de a janela (início + 3 dias) fechar
    assert regras.escolher_lembretes([_m(2, status='letra_pronta', criado=dentro_da_janela)], series, DIA,
                                     MINUTOS, DIAS) == []


def test_pedido_de_saida_vale_90_dias(s, monkeypatch):
    musica = _na_etapa(s, 'previa', 'maria@gmail.com')
    s.repositorio.lembretes_saida['maria@gmail.com'] = DIA - timedelta(days=30)
    assert s.repositorio.candidatas_lembrete() == []
    s.repositorio.lembretes_saida['maria@gmail.com'] = DIA - timedelta(days=91)
    assert [m['id'] for m in s.repositorio.candidatas_lembrete()] == [musica['id']]


def test_serie_vencida_nao_envia_mesmo_chamada_direto():
    assert regras.proximo_lembrete(_serie(DIA - timedelta(days=4), 1), None, DIA, MINUTOS, JANELA, DIAS) == (None, 0)


def test_sem_nome_nao_fica_oi_oi():
    for etapa in ('letra', 'previa', 'checkout'):
        for n in (1, 2, 3):
            _, corpo = mensagens.lembrete(etapa, n, '', 'Helena', 'x', 'y')
            assert 'Oi, Oi' not in corpo and ', .' not in corpo and '>, ' not in corpo, (etapa, n)
    assert 'Leo, você já fez' in mensagens.lembrete('letra', 2, 'Leo', 'Helena', 'x', 'y')[1]
    assert 'Você já fez' in mensagens.lembrete('letra', 2, '', 'Helena', 'x', 'y')[1]


# ------------------------------------------------------------ caso de uso

def _na_etapa(s, etapa, email=None):
    musica = _com_previa(s)
    if email:
        s.repositorio.atualizar(musica['id'], email=email)
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
    assert _rodar(s, monkeypatch, DIA) == 0                                   # entrou na etapa: só começa o relógio
    for depois in (timedelta(minutes=15), timedelta(hours=3), timedelta(hours=24)):
        assert _rodar(s, monkeypatch, DIA + depois) == 1
        assert _rodar(s, monkeypatch, DIA + depois + timedelta(minutes=5)) == 0   # nada repetido
    assert _rodar(s, monkeypatch, DIA + timedelta(hours=48)) == 0
    assert len(s.notificador.emails) == 3 and {e['destino'] for e in s.notificador.emails} == {musica['email']}
    assunto_1 = mensagens.lembrete(etapa, 1, '', regras.para_quem(musica['respostas']), 'x', 'y')[0]
    assert s.notificador.emails[0]['assunto'] == assunto_1
    html = s.notificador.emails[0]['html']
    assert f"/musica/p/{musica['token']}/sem-lembretes" in html
    if etapa == 'checkout':
        assert f"/pay/{musica['produto_id']}?pedido=777&amp;plano=videoclipe&amp;musica={musica['token']}" in html
    else:
        assert f"/musica/p/{musica['token']}" in html


def test_avancar_de_etapa_comeca_a_serie_da_nova(s, monkeypatch):
    musica = _na_etapa(s, 'letra')
    _rodar(s, monkeypatch, DIA)
    _rodar(s, monkeypatch, DIA + timedelta(minutes=15))                       # 1º da letra
    s.repositorio.atualizar(musica['id'], status='previa_pronta')             # criou a música e ouviu
    _rodar(s, monkeypatch, DIA + timedelta(minutes=20))                       # começa a série da prévia
    assert _rodar(s, monkeypatch, DIA + timedelta(minutes=35)) == 0           # 2 h desde o último e-mail dela
    assert _rodar(s, monkeypatch, DIA + timedelta(minutes=15 + 120)) == 1     # 1º da prévia
    assuntos = [e['assunto'] for e in s.notificador.emails]
    assert assuntos[0].startswith('A letra de') and assuntos[1].startswith('Gostou da música de')


def test_varias_musicas_da_mesma_pessoa_tres_lembretes_na_etapa(s, monkeypatch):
    """4 músicas na prévia (refez, ou para várias pessoas), "outra versão" no meio: 3 e-mails da prévia, não 3 por
    música — e os seguintes falam da música mais nova."""
    _na_etapa(s, 'previa', 'maria@gmail.com')
    _rodar(s, monkeypatch, DIA)
    assert _rodar(s, monkeypatch, DIA + timedelta(minutes=15)) == 1
    novas = [_na_etapa(s, 'previa', 'Maria@Gmail.com ') for _ in range(3)]
    s.repositorio.atualizar(novas[-1]['id'], status='gerando')                # "outra versão" da mais nova
    for depois in (timedelta(minutes=30), timedelta(hours=3), timedelta(hours=5)):
        _rodar(s, monkeypatch, DIA + depois)
    s.repositorio.atualizar(novas[-1]['id'], status='previa_pronta')
    for depois in (timedelta(hours=24), timedelta(hours=30), timedelta(days=2), timedelta(days=4)):
        _rodar(s, monkeypatch, DIA + depois)
    assert len(s.notificador.emails) == 3
    assert f"/musica/p/{novas[-1]['token']}" in s.notificador.emails[-1]['html']


def test_parar_vale_para_a_pessoa(s, monkeypatch):
    _na_etapa(s, 'previa', 'maria@gmail.com')
    b = _na_etapa(s, 'letra', 'maria@gmail.com')
    assert uc.parar_lembretes(s, b['token'])
    _rodar(s, monkeypatch, DIA)
    assert _rodar(s, monkeypatch, DIA + timedelta(minutes=15)) == 0
    assert s.repositorio.candidatas_lembrete() == []


def test_comprou_uma_nao_recebe_lembrete_da_outra(s):
    paga = _na_etapa(s, 'previa', 'maria@gmail.com')
    _na_etapa(s, 'letra', 'maria@gmail.com')
    s.repositorio.atualizar(paga['id'], liberada_em=DIA)
    assert s.repositorio.candidatas_lembrete() == []


def test_compra_antiga_nao_bloqueia_musica_nova(s):
    """Comprou há 10 dias e fez outra música agora: a nova recebe lembretes."""
    antiga = _na_etapa(s, 'previa', 'maria@gmail.com')
    nova = _na_etapa(s, 'previa', 'maria@gmail.com')
    s.repositorio.atualizar(antiga['id'], liberada_em=DIA - timedelta(days=10), criado_em=DIA - timedelta(days=10))
    assert [m['id'] for m in s.repositorio.candidatas_lembrete()] == [nova['id']]


def test_checkout_aberto_grava_so_a_primeira_vez(s, monkeypatch):
    musica = _com_previa(s)
    monkeypatch.setattr(uc, '_agora', lambda: DIA)
    uc.checkout_aberto(s, musica['token'])
    monkeypatch.setattr(uc, '_agora', lambda: DIA + timedelta(hours=2))
    uc.checkout_aberto(s, musica['token'])
    assert s.repositorio.por_id(musica['id'])['checkout_aberto_em'] == DIA


def test_link_do_checkout_sem_pedido_aberto():
    m = {'token': 'f' * 32, 'produto_id': 17, 'dominio': 'lsnlivros.com.br'}
    assert links.checkout(m).endswith(f"/pay/17?musica={'f' * 32}")


def test_pix_da_musica_sai_do_lembrete_generico():
    """Pedido de música não recebe o e-mail genérico de PIX: a etapa checkout dos lembretes cuida dele."""
    import inspect
    import database
    assert 'musica_pedidos' in inspect.getsource(database.buscar_pedidos_followup_pagamento_web)


def test_email_da_musica_ja_gravado_na_chave_dos_lembretes(s):
    """Os lembretes comparam o e-mail como gravado (com índice): a criação já o normaliza."""
    from tests.musica.conftest import RESPOSTAS
    musica = uc.criar_musica(s, 17, dict(RESPOSTAS), '  Maria@Gmail.COM ', '', '1.2.3.4')
    assert musica['email'] == 'maria@gmail.com' == regras.chave_email(' Maria@Gmail.COM')
