"""Investimento das campanhas da Meta: lê os insights de cada conta e grava em orcamento_campanha, como o Google."""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import requests

import config
from database import atualizar_nome_automatico_campanha, buscar_produto_id_por_campaignid, upsert_orcamento_campanha

logger = logging.getLogger(__name__)

_SP_TZ = timezone(timedelta(hours=-3))
_CAMPOS_INSIGHTS = 'campaign_id,campaign_name,spend,inline_link_clicks,impressions,account_currency,date_start'


def _periodo(data_str: str | None) -> dict:
    """Um dia só no reprocessamento manual. Sem data, os últimos 7 dias contando hoje: entra o gasto anterior ao
    primeiro clique (a campanha ainda não estava em `campanhas`) e os ajustes que a Meta faz depois."""
    if data_str:
        return {'since': data_str, 'until': data_str}
    hoje = datetime.now(_SP_TZ).date()
    return {'since': (hoje - timedelta(days=6)).isoformat(), 'until': hoje.isoformat()}


def _ler_paginas(caminho: str, token: str, params: dict) -> list:
    """GET com todas as páginas. O próximo pedido usa o cursor, porque o `paging.next` da Meta pode trazer o token na URL."""
    linhas = []
    params = dict(params)
    while True:
        resposta = requests.get(
            f"{config.WHATSAPP_API_URL}{caminho}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        if resposta.status_code >= 400:
            raise RuntimeError(f"HTTP {resposta.status_code} — {resposta.text[:500]}")
        corpo = resposta.json()
        if not isinstance(corpo, dict):
            raise ValueError(f"resposta inesperada da Meta em {caminho}")
        linhas.extend(corpo.get('data') or [])
        paging = corpo.get('paging') or {}
        depois = (paging.get('cursors') or {}).get('after')
        if not paging.get('next') or not depois or depois == params.get('after'):
            return linhas
        params['after'] = depois


def _gravar_linha(linha: dict) -> bool:
    campaignid = str(linha.get('campaign_id') or '')
    if linha.get('account_currency') != 'BRL':
        logger.error(f"[ORCAMENTO-META] ❌ Campanha {campaignid} em {linha.get('account_currency')}: só gravamos BRL")
        return False
    produto_id = buscar_produto_id_por_campaignid(campaignid)
    if produto_id is None:
        logger.warning(f"[ORCAMENTO-META] campanha '{campaignid}' não encontrada em campanhas — ignorada")
        return False
    upsert_orcamento_campanha(produto_id, campaignid, linha['date_start'], float(linha.get('spend') or 0),
                              int(linha.get('inline_link_clicks') or 0), int(linha.get('impressions') or 0))
    if linha.get('campaign_name'):
        atualizar_nome_automatico_campanha(produto_id, campaignid, linha['campaign_name'])
    return True


def processar_orcamento_meta(data_str: str | None = None) -> dict:
    """Lê as contas de todos os tokens META_TOKEN_*. Erro numa BM ou numa conta não atrapalha as outras."""
    tokens = {nome: valor.strip() for nome, valor in os.environ.items()
              if nome.startswith('META_TOKEN_') and valor.strip()}
    params = {'level': 'campaign', 'time_increment': 1, 'time_range': json.dumps(_periodo(data_str)),
              'fields': _CAMPOS_INSIGHTS}
    contas_lidas = set()
    resumo = {'contas': 0, 'upserts': 0, 'ignoradas': 0, 'erros': 0}

    for nome, token in tokens.items():
        try:
            contas = _ler_paginas('me/adaccounts', token, {'fields': 'id'})
        except Exception as e:
            logger.error(f"[ORCAMENTO-META] ❌ Erro ao listar as contas de {nome}: {type(e).__name__}: {e}")
            resumo['erros'] += 1
            continue

        for conta in contas:
            act_id = conta.get('id') if isinstance(conta, dict) else None
            if not act_id or act_id in contas_lidas:
                continue
            try:
                for linha in _ler_paginas(f'{act_id}/insights', token, params):
                    try:
                        resumo['upserts' if _gravar_linha(linha) else 'ignoradas'] += 1
                    except Exception as e:  # uma linha ruim não descarta o resto da conta
                        logger.error(f"[ORCAMENTO-META] ❌ Conta {act_id}, linha {linha}: {type(e).__name__}: {e}")
                        resumo['erros'] += 1
                contas_lidas.add(act_id)  # só depois de ler: se este token falhar, outro que veja a conta tenta
                resumo['contas'] += 1
            except Exception as e:
                logger.error(f"[ORCAMENTO-META] ❌ Erro na conta {act_id}: {type(e).__name__}: {e}")
                resumo['erros'] += 1

    logger.info(f"[ORCAMENTO-META] 🏁 {resumo}")
    return resumo
