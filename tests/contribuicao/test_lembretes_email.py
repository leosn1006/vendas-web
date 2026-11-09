"""E-mails da contribuição: entrega e lembretes, com as travas de horário, de "já pagou" e de envio duplicado."""
from datetime import datetime

import pytest

import database
from fluxos import fluxo_contribuicao_email as fluxo

DIA = datetime(2026, 11, 8, 10, 0)


def _pedido(**extra):
    return {'id': 50, 'guid': 'gteste01', 'estado_id': 1009, 'produto_id': 11, 'email': 'maria@gmail.com',
            'contact_name': 'Maria Silva', 'gmail_thread_id': None, 'lembrete': 1, **extra}


@pytest.fixture
def banco(monkeypatch):
    estado = {'fila': [], 'paga': False, 'reservas': [], 'reservado': True, 'enviados': []}
    monkeypatch.setenv('APP_BASE_URL', 'https://lsnlivros.com.br/')
    monkeypatch.setattr(database, 'buscar_contribuicoes_para_lembrete', lambda: estado['fila'])
    monkeypatch.setattr(database, 'contribuicao_paga', lambda p, por_email=True: estado['paga'])
    estado['limite'] = 'ok'
    estado['desfeitos'] = []
    monkeypatch.setattr(database, 'reservar_envio_email', lambda tipo, pid, ip, lim: estado['limite'])
    monkeypatch.setattr(database, 'desfazer_envio_email', lambda tipo, pid: estado['desfeitos'].append(pid))

    def reservar(pid, n):
        estado['reservas'].append((pid, n))
        return estado['reservado']
    monkeypatch.setattr(database, 'marcar_lembrete_contribuicao', reservar)
    monkeypatch.setattr(database, 'get_produto_by_id', lambda pid: {
        'nome': 'Temperos Caseiros', 'email_remetente': 'tempero@lsnlivros.com.br', 'email_nome_remetente': 'Luiza'})
    monkeypatch.setattr(database, 'get_contribuicao_config', lambda pid: {'persona_nome': 'Luiza'})
    monkeypatch.setattr(database, 'get_plano_venda', lambda pid, slug=None: {'preco_promocional': 10})
    monkeypatch.setattr(database, 'get_pedido', lambda pid: _pedido())
    monkeypatch.setattr(database, 'definir_gmail_thread_pedido', lambda *a: None)
    monkeypatch.setattr(database, 'salvar_mensagem_email_pedido', lambda **k: None)
    monkeypatch.setattr(fluxo, 'rotular_enviado', lambda *a: None)
    monkeypatch.setattr(fluxo, '_enviar_gmail', lambda **k: estado['enviados'].append(k) or {'id': 'm1', 'threadId': 't1'})
    return estado


def test_lembrete_leva_o_link_da_estante_com_o_audio_de_lembrete(banco):
    banco['fila'] = [_pedido(lembrete=1)]
    assert fluxo.executar_lembretes(agora=DIA) == 1
    e = banco['enviados'][0]
    assert 'https://lsnlivros.com.br/pedido2/gteste01?lembrete=1' in e['html']
    assert 'R$ 10' in e['html'] and e['destinatario'] == 'maria@gmail.com'
    assert e['remetente'] == 'tempero@lsnlivros.com.br'
    assert banco['reservas'] == [(50, 1)]


def test_fora_do_horario_nao_envia(banco):
    banco['fila'] = [_pedido()]
    assert fluxo.executar_lembretes(agora=datetime(2026, 11, 8, 23, 0)) == 0
    assert fluxo.executar_lembretes(agora=datetime(2026, 11, 8, 7, 59)) == 0
    assert not banco['enviados'] and not banco['reservas']


def test_quem_ja_pagou_nao_recebe_e_a_serie_encerra(banco):
    banco['fila'] = [_pedido(lembrete=1)]
    banco['paga'] = True
    assert fluxo.executar_lembretes(agora=DIA) == 0
    assert not banco['enviados'] and banco['reservas'] == [(50, 1), (50, 2)]


def test_lembrete_ja_reservado_por_outra_varredura_nao_duplica(banco):
    banco['fila'] = [_pedido(lembrete=2)]
    banco['reservado'] = False
    assert fluxo.executar_lembretes(agora=DIA) == 0 and not banco['enviados']


def test_entrega_manda_o_link_da_estante(banco):
    fluxo.enviar_entrega(50)
    e = banco['enviados'][0]
    assert 'https://lsnlivros.com.br/pedido2/gteste01' in e['html'] and 'Maria' in e['subject']


def test_entrega_ignora_pedido_que_nao_e_entrega(banco, monkeypatch):
    monkeypatch.setattr(database, 'get_pedido', lambda pid: _pedido(estado_id=1000))
    fluxo.enviar_entrega(50)
    assert not banco['enviados']


def test_teto_de_lembretes_por_hora_para_a_varredura(banco):
    """Teto global atingido: nada sai e nada fica reservado (a próxima varredura tenta de novo)."""
    banco['fila'] = [_pedido(lembrete=1), _pedido(id=51, guid='gteste02', lembrete=1)]
    banco['limite'] = 'global'
    assert fluxo.executar_lembretes(agora=DIA) == 0
    assert not banco['enviados'] and not banco['reservas']


def test_lembrete_ja_reservado_devolve_a_vaga_do_limite(banco):
    banco['fila'] = [_pedido(lembrete=1)]
    banco['reservado'] = False  # outra varredura já pegou este lembrete
    assert fluxo.executar_lembretes(agora=DIA) == 0
    assert banco['desfeitos'] == [50] and not banco['enviados']
