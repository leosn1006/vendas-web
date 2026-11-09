import os
import sys

# Imports "planos" como no container (app/ copiado para /app): app/ entra no path para testar fora do Docker.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'app'))

# Agentes criam o cliente OpenAI no import (não é chamado nos testes).
os.environ.setdefault('OPENAI_API_KEY', 'sk-teste-nao-usada')
