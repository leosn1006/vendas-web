"""Cotação do dólar para EXIBIR custos em USD em Real nas telas do admin (ex.: custo do WhatsApp no ROI).

Usa a PTAX de venda mais recente do Banco Central (API pública Olinda) + IOF de compra internacional
no cartão, que é o que de fato sai da conta. Nada disso é gravado no banco — whatsapp_custo_diario
guarda valor e moeda originais.
"""
import datetime
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

_URL_PTAX = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
             "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)")
_CACHE_TTL_S = 6 * 3600
_cache: dict = {}  # {'valor': float, 'data': date|None, 'expira': float}


def _iof_percentual() -> float:
    try:
        return float(os.getenv('IOF_CARTAO_INTERNACIONAL', '3.5'))
    except ValueError:
        return 3.5


def obter_ptax_usd() -> dict:
    """PTAX de venda mais recente (últimos 7 dias, cobre fim de semana/feriado), cacheada por 6h no processo.

    Returns:
        {'valor': float, 'data': date|None, 'fallback': bool}. Se o BCB falhar, usa COTACAO_USD_FALLBACK
        (padrão 5.50) com fallback=True — e tenta de novo em 10 min.
    """
    agora = time.time()
    if _cache and _cache['expira'] > agora:
        return {k: _cache[k] for k in ('valor', 'data', 'fallback')}

    hoje = datetime.date.today()
    ini = hoje - datetime.timedelta(days=7)
    try:
        resp = requests.get(_URL_PTAX, params={
            '@dataInicial': f"'{ini:%m-%d-%Y}'",
            '@dataFinalCotacao': f"'{hoje:%m-%d-%Y}'",
            '$format': 'json',
        }, timeout=10)
        resp.raise_for_status()
        ultima = resp.json()['value'][-1]
        _cache.update(valor=float(ultima['cotacaoVenda']),
                      data=datetime.date.fromisoformat(ultima['dataHoraCotacao'][:10]),
                      fallback=False, expira=agora + _CACHE_TTL_S)
    except Exception as e:
        logger.warning(f"[COTACAO] ⚠️ PTAX indisponível ({type(e).__name__}: {e}) — usando COTACAO_USD_FALLBACK")
        try:
            valor = float(os.getenv('COTACAO_USD_FALLBACK', '5.50'))
        except ValueError:
            valor = 5.50
        _cache.update(valor=valor, data=None, fallback=True, expira=agora + 600)
    return {k: _cache[k] for k in ('valor', 'data', 'fallback')}


def custo_wpp_para_tela(usd: float, brl: float) -> dict:
    """Monta o que as telas de ROI precisam: os dois valores originais e o total convertido em Real
    (USD × PTAX × (1 + IOF) + BRL), mais a cotação usada para mostrar na legenda."""
    ptax = obter_ptax_usd() if usd else {'valor': 0.0, 'data': None, 'fallback': False}
    iof = _iof_percentual()
    fator = ptax['valor'] * (1 + iof / 100)  # R$ por US$ já com IOF — o que a tela mostra para conferir a conta
    convertido = brl + usd * fator
    return {'usd': usd, 'brl': brl, 'convertido': convertido, 'fator': fator,
            'ptax': ptax['valor'], 'ptax_data': ptax['data'], 'ptax_fallback': ptax['fallback'], 'iof': iof}
