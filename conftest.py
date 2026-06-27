import sys
import os

# Adiciona a raiz do projeto ao path para que os testes importem via app.fiscal.*
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
