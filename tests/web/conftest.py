import os
import sys

# Como no container (app/ copiado para /app): imports "database", "web"...
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'app'))
os.environ.setdefault('OPENAI_API_KEY', 'sk-teste-nao-usada')
