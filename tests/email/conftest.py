import os
import sys
from datetime import datetime

# Os módulos do atendimento por e-mail usam imports "planos" (import database, from fluxos…),
# como no container (app/ copiado para /app); aqui app/ entra no path para testá-los fora do Docker.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'app'))

# Agentes criam o cliente OpenAI no import (não é chamado nos testes).
os.environ.setdefault('OPENAI_API_KEY', 'sk-teste-nao-usada')

import pytest


def pedido(id, estado_id, email='', phone=None, produto_id=11, nome='', pagador='', data=None, **extra):
    return {'id': id, 'guid': f'g{id:07d}'[:8], 'estado_id': estado_id, 'produto_id': produto_id,
            'email': email, 'contact_phone': phone, 'contact_name': nome, 'nome_pagador': pagador,
            'data_pedido': data or datetime(2026, 9, 1), 'dns_origem': None, 'data_envio_pedido': None,
            **extra}


@pytest.fixture
def banco(monkeypatch):
    """Banco falso para a cascata de vínculo: cada busca devolve o que o teste cadastrar e registra
    as chamadas (pra checar que etapas caras não rodam à toa)."""
    import database
    dados = {'thread': None, 'pedidos': {}, 'email': [], 'telefone': [], 'cpf': [],
             'nome': {'completo': [], 'primeiro_ultimo': []}, 'produto_nome': [], 'chamadas': []}

    def registrar(nome, retorno):
        def f(*args, **kwargs):
            dados['chamadas'].append(nome)
            return retorno() if callable(retorno) else retorno
        return f

    monkeypatch.setattr(database, 'resolver_pedido_por_thread_gmail', registrar('thread', lambda: dados['thread']))
    monkeypatch.setattr(database, 'get_pedido', lambda i: dados['pedidos'].get(i))
    monkeypatch.setattr(database, 'buscar_pedidos_vinculo_por_email', registrar('email', lambda: dados['email']))
    monkeypatch.setattr(database, 'buscar_pedidos_vinculo_por_telefone', registrar('telefone', lambda: dados['telefone']))
    monkeypatch.setattr(database, 'buscar_pedidos_vinculo_por_cpf', registrar('cpf', lambda: dados['cpf']))
    monkeypatch.setattr(database, 'buscar_pedidos_vinculo_por_nome', registrar('nome', lambda: dados['nome']))

    def por_produto(produto_id, inicio, fim, palavras):
        dados['chamadas'].append(('produto_nome', produto_id, inicio, fim, tuple(palavras)))
        return dados['produto_nome']
    monkeypatch.setattr(database, 'buscar_pedidos_vinculo_por_produto_e_nome', por_produto)
    return dados
