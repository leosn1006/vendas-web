#!/usr/bin/env python3
"""
Reenvia (backfill) para o Google Sheets os pedidos de um produto/DNS que JÁ
tinham sido enviados anteriormente (data_envio_google_ads IS NOT NULL).
Útil para repopular uma planilha que foi limpa manualmente.

Reproduz as mesmas regras de negócio de exportar_para_google_sheets()
(app/fluxos/fluxo_upload_google_ads.py): cabeçalho, formato de conversion_time,
conversion_value fixo (10.00, ou 20.00 para o produto 12) e colunas wbraid/gbraid.

Não limpa a planilha (isso é manual) e NÃO atualiza data_envio_google_ads
(preserva a data original de envio; pedidos ainda não enviados continuam
sendo tratados normalmente pelo fluxo diário, sem interferência deste script).

Uso:
    python scripts/reenviar_gclids_google_sheets.py --dry-run
    python scripts/reenviar_gclids_google_sheets.py
    python scripts/reenviar_gclids_google_sheets.py --produto-id 10 --dns lsnlivros.com.br
"""
import argparse
import json
import os
import sys
from datetime import datetime

import pytz
from dotenv import load_dotenv

load_dotenv()

# Este script roda no host, fora da rede Docker: DB_HOST='db' (nome do serviço,
# usado pelos containers) não resolve aqui. O MySQL é publicado em 127.0.0.1:3306
# (ver docker-compose.yml), então trocamos para localhost quando aplicável.
if os.getenv('DB_HOST') == 'db':
    os.environ['DB_HOST'] = 'localhost'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import db

HEADER = ["Google Click ID", "Conversion Name", "Conversion Time", "Conversion Value", "Currency Code", "wbraid", "gbraid"]


def buscar_config_planilha(produto_id, dns):
    query = """
        SELECT google_sheets_spreadsheet_id, google_sheets_sheet_name,
               google_ads_conversion_name, google_sa_env_var
        FROM google_ads_planilha_dns
        WHERE produto_id = %s AND dns = %s AND ativo = TRUE
    """
    config = db.execute_query(query, (produto_id, dns), fetch_one=True)
    if not config:
        print(f"❌ Nenhuma config ativa em google_ads_planilha_dns para produto_id={produto_id} dns={dns}")
        sys.exit(1)
    return config


def buscar_pedidos_ja_enviados(produto_id, dns):
    query = """
        SELECT id, gclid, wbraid, gbraid, data_pagamento
        FROM pedidos
        WHERE produto_id = %s
          AND dns_origem = %s
          AND estado_id IN (0, 1000)
          AND data_envio_google_ads IS NOT NULL
          AND ((gclid IS NOT NULL AND gclid != '')
            OR (wbraid IS NOT NULL AND wbraid != '')
            OR (gbraid IS NOT NULL AND gbraid != ''))
        ORDER BY data_pagamento ASC
    """
    pedidos = db.execute_query(query, (produto_id, dns), fetch_all=True)
    return pedidos or []


def montar_linha(pedido, produto_id, conversion_name, now_sp):
    dp = pedido['data_pagamento']
    if isinstance(dp, str):
        try:
            dp = datetime.fromisoformat(dp)
        except ValueError:
            dp = datetime.strptime(dp, "%Y-%m-%d %H:%M:%S")

    if dp.date() > now_sp.date():
        dp = now_sp

    conversion_time = dp.strftime("%Y-%m-%d %H:%M:%S") + " America/Sao_Paulo"
    conversion_value = "20.00" if produto_id == 12 else "10.00"

    return [
        pedido['gclid'] or '',
        conversion_name,
        conversion_time,
        conversion_value,
        "BRL",
        pedido.get('wbraid') or '',
        pedido.get('gbraid') or '',
    ]


def enviar_para_sheets(spreadsheet_id, sheet_name, sa_env_var, rows):
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

    if not ws.row_values(1):
        ws.insert_row(HEADER, index=1)

    ws.append_rows(rows, value_input_option="USER_ENTERED")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--produto-id', type=int, default=10)
    parser.add_argument('--dns', default='lsnlivros.com.br')
    parser.add_argument('--dry-run', action='store_true', help="Só mostra a contagem, não escreve no Sheets.")
    args = parser.parse_args()

    config = buscar_config_planilha(args.produto_id, args.dns)
    pedidos = buscar_pedidos_ja_enviados(args.produto_id, args.dns)

    print(f"Produto {args.produto_id} / dns {args.dns}")
    print(f"Planilha: {config['google_sheets_spreadsheet_id']} / aba '{config['google_sheets_sheet_name']}'")
    print(f"Conversion name: {config['google_ads_conversion_name']} / SA env var: {config['google_sa_env_var']}")
    print(f"Pedidos já enviados anteriormente (data_envio_google_ads IS NOT NULL): {len(pedidos)}")

    if not pedidos:
        return

    if args.dry_run:
        amostra = pedidos[:3] + pedidos[-3:]
        print("\nAmostra (id / data_pagamento):")
        for p in amostra:
            print(f"  {p['id']} / {p['data_pagamento']}")
        print("\n(dry-run: nada foi escrito na planilha)")
        return

    sp_tz = pytz.timezone("America/Sao_Paulo")
    now_sp = datetime.now(sp_tz)

    rows = [montar_linha(p, args.produto_id, config['google_ads_conversion_name'], now_sp) for p in pedidos]

    enviar_para_sheets(
        config['google_sheets_spreadsheet_id'],
        config['google_sheets_sheet_name'],
        config['google_sa_env_var'],
        rows,
    )

    print(f"\n✅ {len(rows)} linhas exportadas (data_envio_google_ads não foi alterada).")


if __name__ == '__main__':
    main()
