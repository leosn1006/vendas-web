"""
Fluxo Responder não marca a mensagem como lida nem mostra "digitando".
Motivo: quando a IA escala (ex.: pedido de estorno) e ninguém respondeu ainda, os tiques azuis faziam a
cliente achar que estávamos ignorando o pedido.
"""
import pytest

import whatsapp
from fluxos import fluxo_responder

WEBHOOK = {'entry': [{'changes': [{'value': {'messages': [{'id': 'wamid.CLIENTE', 'text': {'body': 'quero estorno'}}]}}]}]}
PEDIDO = {'id': 7, 'produto_id': 1, 'phone_number_id': 'web-1'}


@pytest.fixture
def cenario(monkeypatch):
    # Registra (em vez de lançar erro) qualquer POST à API: o código antigo chamava marcar_como_lida/digitando
    # dentro de try/except Exception, que engoliria um AssertionError. A lista é conferida em cada teste.
    posts = []
    monkeypatch.setattr(whatsapp.requests, 'post', lambda *a, **k: posts.append((a, k)))
    monkeypatch.setattr(whatsapp, 'get_whatsapp_api_url', lambda _p: 'http://api.teste/')
    monkeypatch.setattr(whatsapp, 'get_whatsapp_token', lambda _p: 'token')
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda _p: 'meta')
    # e as próprias funções, no whatsapp e no fluxo (caso voltem a ser importadas por nome lá)
    for nome in ('marcar_como_lida', 'enviar_mensagem_digitando'):
        registrar = lambda *a, _n=nome, **k: posts.append((_n, a))
        monkeypatch.setattr(whatsapp, nome, registrar)
        monkeypatch.setattr(fluxo_responder, nome, registrar, raising=False)
    monkeypatch.setattr(fluxo_responder, 'tem_notificacao_em_analise', lambda _p: False)
    monkeypatch.setattr(fluxo_responder, 'contar_total_mensagens_pedido', lambda _p: 1)
    monkeypatch.setattr(fluxo_responder, 'buscar_ultima_mensagem_recebida_por_pedido', lambda *_a, **_k: None)
    monkeypatch.setattr(fluxo_responder, 'get_produto_by_id', lambda _p: {'prompt_vendas': 'x', 'nome': 'P'})
    monkeypatch.setattr(fluxo_responder, 'buscar_historico_conversa', lambda *_a, **_k: [])
    monkeypatch.setattr(fluxo_responder, 'salvar_mensagem_pedido', lambda *_a, **_k: None)
    agendadas = []
    monkeypatch.setattr(fluxo_responder.celery_app, 'send_task',
                        lambda nome, args, countdown: agendadas.append((nome, countdown)))
    yield agendadas
    assert posts == [], 'o fluxo Responder não pode marcar como lida nem enviar digitando'


def test_ia_escala_nao_marca_lida(monkeypatch, cenario):
    monkeypatch.setattr(fluxo_responder, 'responder_cliente_com_historico_produto', lambda *_a: None)
    fluxo_responder.executar(PEDIDO, WEBHOOK)
    assert cenario == []


def test_pedido_em_analise_nao_marca_lida(monkeypatch, cenario):
    monkeypatch.setattr(fluxo_responder, 'tem_notificacao_em_analise', lambda _p: True)
    fluxo_responder.executar(PEDIDO, WEBHOOK)
    assert cenario == []


def test_ia_responde_agenda_com_delay_sem_digitando(monkeypatch, cenario):
    monkeypatch.setattr(fluxo_responder, 'responder_cliente_com_historico_produto', lambda *_a: 'oi!')
    fluxo_responder.executar(PEDIDO, WEBHOOK)
    assert len(cenario) == 1
    nome, countdown = cenario[0]
    assert nome == 'tasks.enviar_resposta_cliente'
    assert 5.0 <= countdown <= 8.0
