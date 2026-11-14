"""SMS junto com os lembretes da Música (docs/SMS.md): só nas etapas prévia e checkout, com celular brasileiro, texto
sem acento em 1 parte (≤ 160) e uma falha do SMS nunca afeta o e-mail."""
from datetime import timedelta

import pytest

from musica import mensagens
from tests.musica.test_lembretes import DIA, _na_etapa, _rodar, relogio  # noqa: F401 (relógio dos testes, autouse)

LINK = 'lsnlivros.com.br/m/Ab3dEf9'


@pytest.mark.parametrize('etapa', ['previa', 'checkout'])
def test_sms_acompanha_cada_email_da_etapa(s, monkeypatch, etapa):
    musica = _na_etapa(s, etapa)
    s.repositorio.atualizar(musica['id'], whatsapp='(61) 98269-6770')
    _rodar(s, monkeypatch, DIA)
    for depois in (timedelta(minutes=15), timedelta(hours=3), timedelta(hours=24)):
        _rodar(s, monkeypatch, DIA + depois)
    assert len(s.notificador.emails) == 3 and len(s.notificador.smss) == 3
    assert [x['etapa'] for x in s.notificador.smss] == [f'{etapa} 1', f'{etapa} 2', f'{etapa} 3']
    primeiro = s.notificador.smss[0]
    assert primeiro['telefone'] == '5561982696770' and primeiro['musica_id'] == musica['id']
    assert primeiro['texto'] == ('Cancao de Presente: Patricia, a musica da Dona Lena ficou pronta e esta guardada '
                                 f'pra voce. Ouca de novo e finalize: {LINK}')
    # um texto para cada lembrete (o mesmo três vezes parece robô)
    assert len({x['texto'] for x in s.notificador.smss}) == 3
    assert 'continua guardada' in s.notificador.smss[1]['texto'] and 'ainda da tempo' in s.notificador.smss[2]['texto']
    if etapa == 'checkout':
        assert '/pay/' in primeiro['destino'] and musica['token'] in primeiro['destino']
    else:
        assert primeiro['destino'].endswith(f"/musica/p/{musica['token']}")


def test_etapa_letra_nao_recebe_sms(s, monkeypatch):
    musica = _na_etapa(s, 'letra')
    s.repositorio.atualizar(musica['id'], whatsapp='61982696770')
    _rodar(s, monkeypatch, DIA)
    _rodar(s, monkeypatch, DIA + timedelta(minutes=15))
    assert len(s.notificador.emails) == 1 and s.notificador.smss == []


@pytest.mark.parametrize('telefone', [None, '', '6132345678', '+1 415 555 0100'])
def test_sem_celular_brasileiro_so_email(s, monkeypatch, telefone):
    musica = _na_etapa(s, 'previa')
    s.repositorio.atualizar(musica['id'], whatsapp=telefone)
    _rodar(s, monkeypatch, DIA)
    _rodar(s, monkeypatch, DIA + timedelta(minutes=15))
    assert len(s.notificador.emails) == 1 and s.notificador.smss == []


def test_falha_do_sms_nao_derruba_o_email(s, monkeypatch):
    musica = _na_etapa(s, 'previa')
    s.repositorio.atualizar(musica['id'], whatsapp='61982696770')
    s.notificador.falhar_sms = True
    _rodar(s, monkeypatch, DIA)
    assert _rodar(s, monkeypatch, DIA + timedelta(minutes=15)) == 1
    assert len(s.notificador.emails) == 1


# ------------------------------------------------------------------- texto

@pytest.mark.parametrize('respostas,trecho', [
    ({'para_quem': 'Mãe', 'nome': 'Helena'}, 'Leo, a musica da Helena ficou pronta'),
    ({'para_quem': 'Pai', 'nome': 'João'}, 'Leo, a musica do Joao ficou pronta'),
    ({'para_quem': 'Mais de uma pessoa', 'nome': 'Ana, Bia e Carla'}, 'a musica de Ana, Bia e Carla ficou pronta'),
    ({'para_quem': 'Outra pessoa', 'nome': 'Kim'}, 'a musica de Kim ficou pronta'),
    ({'para_quem': 'Para mim', 'nome': 'Patrícia'}, 'a sua musica ficou pronta'),
])
def test_da_do_de(respostas, trecho):
    assert trecho in mensagens.lembrete_sms('Leo', respostas, LINK)


@pytest.mark.parametrize('numero,de,esperado', [
    (1, 'Leo', f'Cancao de Presente: Leo, a musica do Cesar ficou pronta e esta guardada pra voce. Ouca de novo e finalize: {LINK}'),
    (2, 'Leo', f'Cancao de Presente: Leo, a musica do Cesar continua guardada. Falta so finalizar pra emocionar quem voce ama: {LINK}'),
    (3, 'Leo', f'Cancao de Presente: Leo, ainda da tempo! A musica do Cesar esta esperando por voce. Finalize aqui: {LINK}'),
    (3, '', f'Cancao de Presente: Ainda da tempo! A musica do Cesar esta esperando por voce. Finalize aqui: {LINK}'),
])
def test_tres_textos(numero, de, esperado):
    assert mensagens.lembrete_sms(de, {'para_quem': 'Pai', 'nome': 'Cesar'}, LINK, numero=numero) == esperado


def test_para_mim_nao_fala_em_emocionar_quem_voce_ama():
    texto = mensagens.lembrete_sms('Ana', {'para_quem': 'Para mim', 'nome': 'Ana'}, LINK, numero=2)
    assert 'a sua musica continua guardada' in texto and 'pra ouvir inteira' in texto


def test_sem_nome_comeca_com_maiuscula():
    assert mensagens.lembrete_sms('', {'para_quem': 'Mãe', 'nome': 'Helena'}, LINK).startswith(
        'Cancao de Presente: A musica da Helena')


def test_sem_acento_e_sem_emoji():
    texto = mensagens.lembrete_sms('Conceição 💛', {'para_quem': 'Avó', 'nome': 'Glória'}, LINK, 'Canção de Presente')
    assert texto.startswith('Cancao de Presente: Conceicao, a musica da Gloria') and texto.endswith(LINK)
    assert texto.isascii()


@pytest.mark.parametrize('de,respostas', [
    ('Maximiliana', {'para_quem': 'Mais de uma pessoa', 'nome': 'Maria Aparecida, Josefina Antonieta e Carla'}),
    ('Anastacia Bernardete', {'para_quem': 'Amiga', 'nome': 'X' * 120}),
])
def test_nunca_passa_de_160(de, respostas):
    for numero in (1, 2, 3):
        texto = mensagens.lembrete_sms(de, respostas, 'umdominiobemcomprido.com.br/m/Ab3dEf9', numero=numero)
        assert len(texto) <= 160 and texto.endswith('umdominiobemcomprido.com.br/m/Ab3dEf9')


def test_marca_longa_sai_antes_de_estourar():
    texto = mensagens.lembrete_sms('Patricia', {'para_quem': 'Mãe', 'nome': 'Juliana'},
                                   'barreiroslivros.com.br/m/Ab3dEf9', 'Canção de Presente - LSN Livros Oficial do Brasil')
    assert len(texto) <= 160 and 'barreiroslivros.com.br/m/Ab3dEf9' in texto and 'Juliana' in texto


def test_texto_padrao_cabe_com_folga():
    texto = mensagens.lembrete_sms('Patricia', {'para_quem': 'Mãe', 'nome': 'Juliana'}, LINK)
    assert len(texto) <= 160


def test_consulta_dos_lembretes_traz_o_celular(monkeypatch):
    """O repositório em memória devolve a música inteira; o do MySQL só as colunas do SELECT. Sem m.whatsapp, nenhum
    SMS sairia em produção (achado da revisão de 14/11/2026)."""
    from musica.adaptadores import repositorio_mysql
    consultas = []
    monkeypatch.setattr(repositorio_mysql.db, 'execute_query', lambda sql, *a, **k: consultas.append(sql) or [])
    repositorio_mysql.RepositorioMysql().candidatas_lembrete()
    assert 'm.whatsapp' in consultas[0]
