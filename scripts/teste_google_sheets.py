"""
Script de teste: valida conexão com Google Sheets e insere uma linha mock.

Pré-requisito (rodar uma vez localmente):
    pip install gspread google-auth

Uso:
    python scripts/teste_google_sheets.py
"""

import os
import json
import sys
from pathlib import Path

# Carrega o .env com suporte a valores JSON multilinhas (ex: GOOGLE_SERVICE_ACCOUNT_JSON={...})
def _load_env(env_file):
    lines = Path(env_file).read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#") or "=" not in line:
            i += 1
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Bloco multilinhas: valor começa com { mas não termina com }
        if value.startswith("{") and not value.rstrip().endswith("}"):
            block = [value]
            i += 1
            while i < len(lines):
                block.append(lines[i])
                if lines[i].strip() == "}":
                    i += 1
                    break
                i += 1
            value = "\n".join(block)
        else:
            value = value.strip("'\"")
            i += 1
        os.environ.setdefault(key, value)

env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    _load_env(env_file)

# ---------------------------------------------------------------------------
# Configuração do teste (mock)
# ---------------------------------------------------------------------------
SPREADSHEET_ID  = "1L1aBClzfrz-QskHW4lW8XRTCkAnDv3TtPHtqSavnfmQ"
SHEET_TAB_NAME  = "Página1"

MOCK_ROW = [

    "Cj0KCQjwgr_NBhDFARIsAHiUWr5NMrN6Z_GN5ElG7EUaEq82fqn42toQLEONARDOm3Hai4AR1B4n0mpCqt9akUIaAhweEALw_wcB",
    "Venda WhatsApp",
    "2026-03-10 04:11:54 America/Sao_Paulo",
    "44.44",
    "BRL",
]

HEADER = [
    "Google Click ID",
    "Conversion Name",
    "Conversion Time",
    "Conversion Value",
    "Conversion Currency",
]

# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
if not sa_json:
    print("❌ GOOGLE_SERVICE_ACCOUNT_JSON não encontrada no .env")
    sys.exit(1)

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("❌ Dependências não instaladas. Rode:")
    print("   pip install gspread google-auth")
    sys.exit(1)

print("🔐 Autenticando com Service Account...")
try:
    creds = Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    print("✅ Autenticado com sucesso!")
except Exception as e:
    print(f"❌ Erro na autenticação: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Abre a planilha
# ---------------------------------------------------------------------------
print(f"📄 Abrindo planilha {SPREADSHEET_ID} / aba '{SHEET_TAB_NAME}'...")
try:
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_TAB_NAME)
    print(f"✅ Aba encontrada: '{ws.title}'")
except gspread.exceptions.SpreadsheetNotFound:
    print("❌ Planilha não encontrada. Verifique se o SPREADSHEET_ID está correto")
    print("   e se a planilha foi compartilhada com o e-mail da Service Account.")
    sys.exit(1)
except gspread.exceptions.WorksheetNotFound:
    print(f"❌ Aba '{SHEET_TAB_NAME}' não encontrada na planilha.")
    print("   Verifique o nome exato da aba (maiúsculas/acentos importam).")
    sys.exit(1)
except Exception as e:
    print(f"❌ Erro ao abrir planilha: {type(e).__name__}: {e}")
    print("   Provável causa: planilha não compartilhada com a Service Account.")
    print(f"   Compartilhe com: {json.loads(sa_json).get('client_email', '?')}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Garante cabeçalho
# ---------------------------------------------------------------------------
existing_header = ws.row_values(1)
if existing_header != HEADER:
    print(f"ℹ️  Cabeçalho ausente ou diferente. Inserindo na linha 1...")
    ws.insert_row(HEADER, index=1)
    print(f"✅ Cabeçalho inserido: {HEADER}")
else:
    print(f"✅ Cabeçalho já existe: {existing_header}")

# ---------------------------------------------------------------------------
# Insere linha mock
# ---------------------------------------------------------------------------
print(f"📝 Inserindo linha de teste...")
print(f"   {MOCK_ROW}")
try:
    ws.append_rows([MOCK_ROW], value_input_option="USER_ENTERED")
    print("✅ Linha inserida com sucesso!")
    print()
    print("Verifique a planilha no Google Drive e depois delete a linha de teste.")
except Exception as e:
    print(f"❌ Erro ao inserir linha: {e}")
    sys.exit(1)
