import os
import sys

# Os módulos de WhatsApp usam imports "planos" (from config import ..., from database import ...)
# porque o container copia app/ para /app; aqui app/ entra no path para testá-los fora do Docker.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'app'))

# fluxo_responder importa o agente de IA, que cria o cliente OpenAI já no import (não é chamado nos testes).
os.environ.setdefault('OPENAI_API_KEY', 'sk-teste-nao-usada')

import pytest


@pytest.fixture(autouse=True)
def _limpar_caches(monkeypatch):
    import database
    database._whatsapp_provedor_cache.clear()
    yield
    database._whatsapp_provedor_cache.clear()


@pytest.fixture
def provedores(monkeypatch):
    """Simula telefones_produto: {api_phone_number_id: provedor}. Devolve o dict e conta as consultas."""
    import database
    tabela = {}
    consultas = []

    def fake_execute_query(query, params=None, fetch_one=False, fetch_all=False):
        consultas.append(params)
        pid = params[0] if params else None
        if pid in tabela:
            return {'provedor': tabela[pid]}
        return None

    monkeypatch.setattr(database.db, 'execute_query', fake_execute_query)
    tabela['_consultas'] = consultas  # só para leitura nos testes
    return tabela
