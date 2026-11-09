"""Regra de acesso da Estante com a entrega da contribuição (estado 1009): o principal libera e o bônus fica com
cadeado, como no WhatsApp — sem mudar nada para os pedidos de antes (WhatsApp, site pago e não pago)."""
import pytest

import importlib

import database

checkout = importlib.import_module('web.checkout')  # `web.checkout` também é o nome de uma rota no pacote


def _pedido(estado_id, **extra):
    return {'id': 50, 'guid': 'gteste01', 'estado_id': estado_id, 'produto_id': 11, 'email': 'maria@gmail.com',
            'contact_phone': None, 'data_envio_pedido': None, **extra}


ITENS = {
    1: {'id': 1, 'tipo': 'principal', 'path_arquivo': 'livro.pdf', 'entregavel_id': 7},
    2: {'id': 2, 'tipo': 'bonus', 'path_arquivo': 'bonus.pdf', 'entregavel_id': 11},
}


@pytest.fixture
def banco(monkeypatch):
    estado = {'pedido': None}
    monkeypatch.setattr(database, 'get_pedido_by_guid', lambda guid: estado['pedido'])
    monkeypatch.setattr(database, 'get_item_pedido_ebook', lambda item_id, pedido_id: ITENS.get(item_id))
    return estado


@pytest.mark.parametrize('estado_id, erro', [
    (1, 'ainda_nao_entregue'),      # lead do WhatsApp que só clicou
    (2, None),                       # WhatsApp: respondeu a introdução (prévia)
    (3, None),
    (0, None),                       # WhatsApp pago
    (1000, None),                    # site pago
    (1002, 'aguardando_pagamento'),  # site com PIX gerado, não pago: nada abre
    (1003, 'aguardando_pagamento'),
    (1008, 'ainda_nao_entregue'),    # contribuição: clicou, ainda sem e-mail
    (1009, None),                    # contribuição: livro entregue
])
def test_acesso_a_estante_por_estado(banco, estado_id, erro):
    banco['pedido'] = _pedido(estado_id)
    _, _, e = checkout.resolver_pedido_por_guid('gteste01')
    assert e == erro


@pytest.mark.parametrize('estado_id, item_id, erro', [
    (1009, 1, None),                    # contribuição: principal libera
    (1009, 2, 'aguardando_pagamento'),  # contribuição: bônus com cadeado
    (3, 2, 'aguardando_pagamento'),     # WhatsApp não pago: bônus com cadeado (igual antes)
    (0, 2, None),
    (1000, 2, None),
])
def test_item_do_leitor(banco, estado_id, item_id, erro):
    banco['pedido'] = _pedido(estado_id)
    _, _, e = checkout.resolver_pedido_por_guid('gteste01', item_id=item_id)
    assert e == erro


@pytest.fixture
def itens_banco(monkeypatch):
    estado = {'vinculados': [], 'itens_outros': []}
    monkeypatch.setattr(database, 'listar_itens_pedido_ebook', lambda pid: [dict(i) for i in ITENS.values()])
    monkeypatch.setattr(database, 'listar_pedidos_pagos_relacionados', lambda *a: [])
    monkeypatch.setattr(database, 'listar_pedidos_vinculados_pagos', lambda pid: estado['vinculados'])
    monkeypatch.setattr(database, 'listar_itens_pedido_ebook_multiplos', lambda ids: estado['itens_outros'])
    monkeypatch.setattr(database, 'garantir_guid_pedido', lambda pid: 'x')
    return estado


def _bloqueados(itens):
    return {i['entregavel_id']: i['bloqueado'] for i in itens}


def test_contribuicao_entregue_mostra_bonus_com_cadeado(itens_banco):
    itens = checkout.listar_itens_ebook_do_cliente(_pedido(1009))
    assert _bloqueados(itens) == {7: False, 11: True}


def test_contribuicao_paga_libera_o_bonus_pelo_pedido_vinculado(itens_banco):
    itens_banco['vinculados'] = [{'id': 99, 'guid': 'gpago999'}]
    itens_banco['itens_outros'] = [{'id': 5, 'tipo': 'bonus', 'path_arquivo': 'bonus.pdf', 'entregavel_id': 11,
                                    'guid_pedido': 'gpago999'}]
    itens = checkout.listar_itens_ebook_do_cliente(_pedido(1009))
    assert _bloqueados(itens) == {7: False, 11: False}
    assert next(i for i in itens if i['entregavel_id'] == 11)['guid_pedido'] == 'gpago999'


def test_entrega_nunca_junta_pedidos_pelo_email_digitado(itens_banco, monkeypatch):
    """O e-mail da entrega não é verificado: digitar o de outra pessoa não pode mostrar os livros dela."""
    chamadas = []
    monkeypatch.setattr(database, 'listar_pedidos_pagos_relacionados',
                        lambda *a: chamadas.append(a) or [{'id': 77, 'guid': 'gvitima'}])
    itens_banco['itens_outros'] = [{'id': 9, 'tipo': 'principal', 'path_arquivo': 'outro.pdf', 'entregavel_id': 40,
                                    'guid_pedido': 'gvitima'}]
    itens = checkout.listar_itens_ebook_do_cliente(_pedido(1009, email='vitima@gmail.com'))
    assert 40 not in _bloqueados(itens) and not chamadas
    # Pedido pago do site continua juntando pelo e-mail, como sempre.
    itens = checkout.listar_itens_ebook_do_cliente(_pedido(1000, email='cliente@gmail.com'))
    assert 40 in _bloqueados(itens) and chamadas


@pytest.mark.parametrize('estado_id, bonus_bloqueado', [(3, True), (0, False), (1000, False)])
def test_bloqueio_dos_outros_canais_nao_muda(itens_banco, estado_id, bonus_bloqueado):
    itens = checkout.listar_itens_ebook_do_cliente(_pedido(estado_id))
    assert _bloqueados(itens) == {7: False, 11: bonus_bloqueado}
