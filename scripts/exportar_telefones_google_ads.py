#!/usr/bin/env python3
"""
Exporta telefones de pedidos pagos (via WhatsApp) para uma planilha Google Sheets,
para uso em audiências de campanhas Google Ads (ex: Customer Match).

A aba de destino é sobrescrita a cada execução (evita duplicatas em reprocessamentos).

Uso:
    python scripts/exportar_telefones_google_ads.py
    python scripts/exportar_telefones_google_ads.py --valor-minimo 50
    make exportar-telefones-google-ads
    make exportar-telefones-google-ads valor=50
"""
import argparse
import json
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()

# Este script roda no host, fora da rede Docker: DB_HOST='db' (nome do serviço,
# usado pelos containers) não resolve aqui. O MySQL é publicado em 127.0.0.1:3306
# (ver docker-compose.yml), então trocamos para localhost quando aplicável.
if os.getenv('DB_HOST') == 'db':
    os.environ['DB_HOST'] = 'localhost'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import db

SPREADSHEET_ID_DEFAULT = "1x1IGn8LqmbD2iFCBsONhX7pku-HEB9hqEGW9l4DeYmg"
SHEET_NAME_DEFAULT = "Página1"
SA_ENV_VAR_DEFAULT = "GOOGLE_SA_JSON_P8"
HEADER = ["Telefone"]


def buscar_telefones(valor_minimo):
    query = """
        SELECT DISTINCT contact_phone
        FROM pedidos
        WHERE estado_id = 0
          AND valor_pago > %s
          AND contact_phone IS NOT NULL
          AND contact_phone != ''
    """
    linhas = db.execute_query(query, (valor_minimo,), fetch_all=True) or []

    telefones = []
    for linha in linhas:
        somente_digitos = re.sub(r'\D', '', linha['contact_phone'])
        if somente_digitos:
            telefones.append(f"+{somente_digitos}")

    return telefones


def exportar_para_sheets(telefones, spreadsheet_id, sheet_name, sa_env_var):
    import gspread
    from google.oauth2.service_account import Credentials

    sa_json = os.getenv(sa_env_var)
    if not sa_json:
        print(f"❌ {sa_env_var} não encontrada no .env")
        sys.exit(1)

    creds = Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(spreadsheet_id).worksheet(sheet_name)

    # RAW evita que o Sheets interprete "+55..." como número e descarte o "+".
    ws.clear()
    ws.append_rows([HEADER] + [[tel] for tel in telefones], value_input_option="RAW")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--valor-minimo', type=float, default=10,
                         help="Valor mínimo pago no pedido (default: 10).")
    parser.add_argument('--spreadsheet-id', default=SPREADSHEET_ID_DEFAULT)
    parser.add_argument('--sheet-name', default=SHEET_NAME_DEFAULT)
    parser.add_argument('--sa-env-var', default=SA_ENV_VAR_DEFAULT)
    args = parser.parse_args()

    telefones = buscar_telefones(args.valor_minimo)
    exportar_para_sheets(telefones, args.spreadsheet_id, args.sheet_name, args.sa_env_var)

    print(f"Telefones exportados: {len(telefones)}")
    print(f"Planilha: {args.spreadsheet_id} / aba '{args.sheet_name}'")


if __name__ == '__main__':
    main()
