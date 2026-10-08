"""Custo das mensagens da API oficial da Meta, lido do pricing_analytics de cada WABA.

Desde 01/10/2026 a Meta cobra cada mensagem de atendimento (SERVICE) que enviamos; recebida não é
cobrada e o preço não muda com o tipo (texto, áudio, arquivo). O pricing_analytics devolve, por
número/categoria/tipo, quantas mensagens e quanto custaram, na moeda da WABA (USD ou BRL), quase em
tempo real (o dia é cortado à meia-noite de Brasília). Ver migrations/079_whatsapp_custo_diario.sql.

Só leitura: nunca envia mensagem. Fora de produção não chama a Meta (config.EH_PRODUCAO).
"""
import datetime
import json
import logging
from collections import defaultdict
from zoneinfo import ZoneInfo

import requests

import config

logger = logging.getLogger(__name__)

_TZ = ZoneInfo('America/Sao_Paulo')
_TAG = "CUSTO-WPP"


def janela_do_dia(data: datetime.date) -> tuple[int, int]:
    """Timestamps (UTC) de 00:00 a 24:00 do dia em horário de Brasília."""
    ini = datetime.datetime.combine(data, datetime.time.min, tzinfo=_TZ)
    fim = ini + datetime.timedelta(days=1)
    return int(ini.timestamp()), int(fim.timestamp())


def agregar_pricing_analytics(resposta: dict) -> dict:
    """Soma os data_points do pricing_analytics por (telefone, categoria).

    Returns:
        {(telefone, categoria): {'custo': float, 'msgs_cobradas': int, 'msgs_gratis': int}}
        REGULAR conta como cobrada; FREE_CUSTOMER_SERVICE/FREE_ENTRY_POINT como grátis.
    """
    total = defaultdict(lambda: {'custo': 0.0, 'msgs_cobradas': 0, 'msgs_gratis': 0})
    for bloco in (resposta.get('pricing_analytics') or {}).get('data', []):
        for p in bloco.get('data_points', []):
            telefone = p.get('phone_number')
            if not telefone:
                continue
            item = total[(telefone, p.get('pricing_category') or 'DESCONHECIDA')]
            item['custo'] += float(p.get('cost') or 0)
            volume = int(p.get('volume') or 0)
            if (p.get('pricing_type') or '').startswith('FREE'):
                item['msgs_gratis'] += volume
            else:
                item['msgs_cobradas'] += volume
    return dict(total)


def consultar_waba(waba_id: str, token: str, data: datetime.date) -> dict:
    """GET na WABA com moeda + pricing_analytics diário do dia. Lança requests.HTTPError em erro."""
    ini, fim = janela_do_dia(data)
    campo = (f"pricing_analytics.start({ini}).end({fim}).granularity(DAILY)"
             f".metric_types({json.dumps(['COST', 'VOLUME'])})"
             f".dimensions({json.dumps(['PHONE', 'PRICING_CATEGORY', 'PRICING_TYPE'])})")
    resp = requests.get(
        f"{config.WHATSAPP_API_URL}{waba_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": f"currency,{campo}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def coletar_dia(data: datetime.date, fonte: str) -> dict:
    """Lê o custo do dia de todas as WABAs dos números Meta cadastrados e grava em whatsapp_custo_diario.

    Os números vêm de telefones_produto (provedor 'meta'; os do gateway WhatsApp Web não passam pela
    Meta). Uma chamada por WABA. Erro numa WABA não interrompe as outras.

    Returns:
        {'wabas': n, 'falhas': n, 'falhas_conectados': [waba_id, ...], 'linhas': n}
        falhas_conectados = WABAs que falharam e têm número CONNECTED (as de número banido/parado falham
        sempre por token morto e não merecem alerta).
    """
    from database import listar_telefones_com_token, get_whatsapp_token, upsert_custo_whatsapp_dia

    if not config.EH_PRODUCAO:
        logger.info(f"[{_TAG}] ⏭ Fora de produção — não consulta a Meta")
        return {'wabas': 0, 'falhas': 0, 'falhas_conectados': [], 'linhas': 0}

    # waba_id -> {telefone: telefone_produto}
    wabas = defaultdict(dict)
    for t in listar_telefones_com_token():
        if t.get('provedor') != 'meta':
            continue
        if not t.get('waba_id'):
            logger.warning(f"[{_TAG}] ⚠️ Número {t['telefone']} (produto #{t['produto_id']}) sem waba_id "
                           f"— fica de fora até a checagem horária de qualidade preencher")
            continue
        wabas[t['waba_id']][t['telefone']] = t

    falhas = linhas = 0
    falhas_conectados = []
    for waba_id, telefones in wabas.items():
        conectado = any(t.get('status_api') == 'CONNECTED' for t in telefones.values())
        # O token é por número (token_env_key): usa o de um número CONNECTED com token no .env, para um
        # número banido/sem token na mesma WABA não derrubar a coleta dos outros.
        candidatos = sorted(telefones.values(), key=lambda t: t.get('status_api') != 'CONNECTED')
        algum, token = candidatos[0], None
        for t in candidatos:
            try:
                token = get_whatsapp_token(t['api_phone_number_id'])
                algum = t
                break
            except ValueError as e:
                erro_token = e
        try:
            if token is None:
                raise erro_token
            resposta = consultar_waba(waba_id, token, data)
        except (ValueError, requests.RequestException) as e:
            falhas += 1
            if conectado:
                falhas_conectados.append(waba_id)
            detalhe = e.response.text[:200] if getattr(e, 'response', None) is not None else str(e)[:200]
            logger.warning(f"[{_TAG}] ⚠️ WABA {waba_id} ({algum['telefone']}): {detalhe}")
            continue

        moeda = resposta.get('currency') or 'USD'
        for (telefone, categoria), v in agregar_pricing_analytics(resposta).items():
            t = telefones.get(telefone)
            if not t:
                logger.warning(f"[{_TAG}] ⚠️ WABA {waba_id} devolveu o número {telefone}, que não está "
                               f"cadastrado em telefones_produto — custo {v['custo']} {moeda} ignorado")
                continue
            upsert_custo_whatsapp_dia(data, telefone, categoria, t['produto_id'], waba_id, moeda,
                                      v['custo'], v['msgs_cobradas'], v['msgs_gratis'], fonte)
            linhas += 1

    logger.info(f"[{_TAG}] ✅ {data} ({fonte}): {len(wabas)} WABAs, {falhas} falhas, {linhas} linhas gravadas")
    return {'wabas': len(wabas), 'falhas': falhas, 'falhas_conectados': falhas_conectados, 'linhas': linhas}
