"""Estante 2, "Guarde seu livro": bloco (baixar / WhatsApp / e-mail mascarado) e reenvio do e-mail com limites."""
import sys
import types

import pytest
from flask import Flask

import database
from web import estante_acesso as ea


def test_mascara_o_email():
    assert ea.mascarar_email('maria.silva@gmail.com') == 'm•••@gmail.com'
    assert ea.mascarar_email(' a@b.com ') == 'a•••@b.com'
    assert ea.mascarar_email('') == '' and ea.mascarar_email(None) == '' and ea.mascarar_email('semarroba') == ''


@pytest.mark.parametrize('pedido, pode', [
    ({'email': 'a@b.com', 'fluxo_inicial': 'web', 'estado_id': 1000}, True),
    ({'email': 'a@b.com', 'fluxo_inicial': 'web', 'estado_id': 1009}, True),
    ({'email': 'a@b.com', 'fluxo_inicial': 'web', 'estado_id': 1008}, False),  # nada entregue ainda
    ({'email': 'a@b.com', 'fluxo_inicial': 'web', 'estado_id': 1002}, False),  # Pix não pago
    ({'email': 'a@b.com', 'fluxo_inicial': 'wpp', 'estado_id': 0}, False),     # WhatsApp: não temos esse e-mail
    ({'email': None, 'fluxo_inicial': 'web', 'estado_id': 1000}, False),
    (None, False),
])
def test_quem_pode_pedir_reenvio(pedido, pode):
    assert ea.pode_reenviar(pedido) is pode


def test_contexto_do_bloco():
    itens = [{'id': 1, 'guid_pedido': 'gA', 'bloqueado': False}, {'id': 2, 'guid_pedido': 'gA', 'bloqueado': True}]
    ctx = ea.contexto_guardar({'email': 'maria@gmail.com', 'fluxo_inicial': 'web', 'estado_id': 1009},
                              itens, 'gA', 'https://lsnlivros.com.br/')
    assert ctx == {'download': '/pedido/gA/arquivo/1?download=1', 'livro': '', 'varios': False,
                   'link': 'https://lsnlivros.com.br/pedido2/gA', 'email': 'm•••@gmail.com'}
    # Vários liberados: sem o botão grande (baixaria só um), a frase manda pro "Baixar" de cada livro.
    dois = [{'id': 1, 'guid_pedido': 'gA', 'bloqueado': False, 'nome': 'A'},
            {'id': 3, 'guid_pedido': 'gB', 'bloqueado': False, 'nome': 'B'}]
    ctx = ea.contexto_guardar({}, dois, 'gA', 'https://x')
    assert ctx['download'] == '' and ctx['varios'] is True
    assert ea.contexto_guardar({}, dois[:1], 'gA', 'https://x')['livro'] == 'A'
    # Pedido do WhatsApp: baixar e WhatsApp sim; e-mail/reenvio não.
    assert ea.contexto_guardar({'fluxo_inicial': 'wpp', 'estado_id': 0}, itens, 'gA', 'https://x')['email'] == ''
    # Nada liberado: não há o que guardar.
    assert ea.contexto_guardar({}, [itens[1]], 'gA', 'https://x') is None


@pytest.fixture
def http(monkeypatch):
    estado = {'reservas': [], 'enviados': [], 'motivo': 'ok', 'desfeitos': []}
    pedidos = {'gweb0001': {'id': 7, 'guid': 'gweb0001', 'email': 'maria@gmail.com', 'fluxo_inicial': 'web',
                            'estado_id': 1000},
               'gwpp0001': {'id': 8, 'guid': 'gwpp0001', 'email': None, 'fluxo_inicial': 'wpp', 'estado_id': 0}}
    monkeypatch.setattr(database, 'get_pedido_by_guid', lambda g: pedidos.get(g))

    def reservar(tipo, pid, ip, limite):
        estado['reservas'].append((tipo, pid, ip, limite))
        return estado['motivo']
    monkeypatch.setattr(database, 'reservar_envio_email', reservar)
    monkeypatch.setattr(database, 'desfazer_envio_email', lambda tipo, pid: estado['desfeitos'].append((tipo, pid)))
    tarefa = types.SimpleNamespace(delay=lambda pid: estado['enviados'].append(pid))
    monkeypatch.setitem(sys.modules, 'tasks', types.SimpleNamespace(reenviar_email_estante=tarefa))
    app = Flask(__name__)
    app.register_blueprint(ea.web_bp)
    return app.test_client(), estado


def test_reenvio_agenda_para_o_email_do_pedido(http):
    c, estado = http
    r = c.post('/api/v1/estante/gweb0001/reenviar-email', headers={'X-Real-IP': '1.2.3.4'})
    assert r.status_code == 200 and r.get_json() == {'ok': True, 'email': 'm•••@gmail.com'}
    assert estado['reservas'] == [('reenvio_estante', 7, '1.2.3.4', 60)] and estado['enviados'] == [7]


@pytest.mark.parametrize('motivo', ['recente', 'dia', 'ip', 'global'])
def test_reenvio_barrado_pelos_limites_nao_envia(http, motivo):
    c, estado = http
    estado['motivo'] = motivo
    r = c.post('/api/v1/estante/gweb0001/reenviar-email')
    assert r.status_code == 429 and r.get_json() == {'erro': motivo} and not estado['enviados']


def test_reenvio_de_pedido_que_nao_e_do_site_ou_inexistente(http):
    c, estado = http
    assert c.post('/api/v1/estante/gwpp0001/reenviar-email').status_code == 404
    assert c.post('/api/v1/estante/naoexiste/reenviar-email').status_code == 404
    assert not estado['reservas'] and not estado['enviados']


def test_fila_fora_do_ar_devolve_a_vaga(http, monkeypatch):
    c, estado = http

    def falha(pid):
        raise ConnectionError('redis fora')
    monkeypatch.setitem(sys.modules, 'tasks', types.SimpleNamespace(reenviar_email_estante=types.SimpleNamespace(delay=falha)))
    assert c.post('/api/v1/estante/gweb0001/reenviar-email').status_code == 503
    assert estado['desfeitos'] == [('reenvio_estante', 7)]


def test_limite_global_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv('REENVIO_ESTANTE_LIMITE_HORA', '15')
    assert ea._limite_global_hora() == 15
    monkeypatch.setenv('REENVIO_ESTANTE_LIMITE_HORA', 'abc')
    assert ea._limite_global_hora() == 60
