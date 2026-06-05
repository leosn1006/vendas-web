import os
import json
import logging
from datetime import datetime, timezone, timedelta

import gspread
from google.oauth2.service_account import Credentials

from database import buscar_produto_id_por_campaignid, upsert_orcamento_campanha

logger = logging.getLogger(__name__)

_SA_ENV_VAR          = 'GOOGLE_SA_JSON_P8'
_SP_TZ               = timezone(timedelta(hours=-3))
_COLUNAS_NECESSARIAS = {'Data', 'ID da Campanha', 'Custo', 'Cliques', 'Impressões'}


def _ontem_sp() -> str:
    return (datetime.now(_SP_TZ) - timedelta(days=1)).strftime('%Y-%m-%d')


def _normalizar_decimal(valor: str) -> float:
    """Converte '1.234,56' ou '1234.56' para float."""
    v = valor.strip().replace(' ', '')
    if ',' in v and '.' in v:
        v = v.replace('.', '').replace(',', '.')
    else:
        v = v.replace(',', '.')
    return float(v) if v else 0.0


def _autenticar() -> gspread.Client:
    sa_json = os.getenv(_SA_ENV_VAR)
    if not sa_json:
        raise ValueError(f"Variável de ambiente {_SA_ENV_VAR} não encontrada")
    creds = Credentials.from_service_account_info(
        json.loads(sa_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return gspread.authorize(creds)


def _cell(nome: str, row: list, col_map: dict) -> str:
    idx = col_map[nome] - 1  # col_map é 1-indexed; row é 0-indexed
    return row[idx].strip() if idx < len(row) else ''


def processar_orcamento_sheets(data_str: str | None = None) -> dict:
    # Bug fix: ler ORCAMENTO_SHEETS_ID em tempo de execução, não no import
    spreadsheet_id = os.getenv('ORCAMENTO_SHEETS_ID', '')
    if not spreadsheet_id:
        raise ValueError("Variável ORCAMENTO_SHEETS_ID não configurada")

    data_alvo = data_str or _ontem_sp()
    logger.info(f"[ORCAMENTO-SHEETS] 🎬 Iniciando processamento — data alvo: {data_alvo}")

    gc = _autenticar()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    worksheets  = spreadsheet.worksheets()

    total_abas = len(worksheets)
    upserts    = 0
    skips      = 0

    for ws in worksheets:
        aba = ws.title

        # Fase 1: leitura do gspread (erros por aba são tolerados)
        try:
            headers = ws.row_values(1)
            if not headers:
                logger.debug(f"[ORCAMENTO-SHEETS] Aba '{aba}' sem cabeçalho — ignorada")
                continue

            col_map = {h.strip(): i + 1 for i, h in enumerate(headers)}  # 1-indexed
            ausentes = _COLUNAS_NECESSARIAS - col_map.keys()
            if ausentes:
                logger.debug(f"[ORCAMENTO-SHEETS] Aba '{aba}' sem colunas {ausentes} — ignorada")
                continue

            # Busca só a coluna de datas — estratégia de baixo consumo de memória
            date_col = ws.col_values(col_map['Data'])

            # Bug fix: encontra TODAS as linhas da data, não só a primeira
            row_indices = [i + 1 for i, d in enumerate(date_col) if d == data_alvo]
            if not row_indices:
                logger.debug(f"[ORCAMENTO-SHEETS] Aba '{aba}' sem data {data_alvo} — ignorada")
                continue

            rows = [ws.row_values(idx) for idx in row_indices]

        except Exception as e:
            # Falha de leitura do gspread: registra e segue para a próxima aba
            logger.error(f"[ORCAMENTO-SHEETS] ❌ Erro ao ler aba '{aba}': {e}")
            skips += 1
            continue

        # Fase 2: escrita no banco — erros propagam para o retry da task
        for row in rows:
            campaignid = _cell('ID da Campanha', row, col_map)
            if not campaignid:
                logger.warning(f"[ORCAMENTO-SHEETS] Aba '{aba}' linha sem campaignid — ignorada")
                skips += 1
                continue

            produto_id = buscar_produto_id_por_campaignid(campaignid)
            if produto_id is None:
                logger.warning(f"[ORCAMENTO-SHEETS] campaignid '{campaignid}' não encontrado em campanhas — ignorado")
                skips += 1
                continue

            custo      = _normalizar_decimal(_cell('Custo', row, col_map))
            cliques_v  = _cell('Cliques', row, col_map)
            imp_v      = _cell('Impressões', row, col_map)
            cliques    = int(cliques_v) if cliques_v else None
            impressoes = int(imp_v) if imp_v else None

            upsert_orcamento_campanha(produto_id, campaignid, data_alvo, custo, cliques, impressoes)
            logger.info(f"[ORCAMENTO-SHEETS] ✅ Aba '{aba}' | campanha {campaignid} | custo={custo} cliques={cliques} imp={impressoes}")
            upserts += 1

    logger.info(
        f"[ORCAMENTO-SHEETS] 🏁 Concluído — {total_abas} abas | {upserts} upserts | {skips} skips"
    )
    return {'abas': total_abas, 'upserts': upserts, 'skips': skips}
