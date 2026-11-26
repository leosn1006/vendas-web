"""Cotações em reais.

- Telas do admin (ex.: custo do WhatsApp no ROI): PTAX de venda do dólar (API pública Olinda do BCB) + IOF de compra
  internacional no cartão, que é o que de fato sai da conta. Nada disso é gravado — whatsapp_custo_diario guarda valor
  e moeda originais.
- Webhook da Hotmart (cotacao_em_reais): PTAX quando a moeda existe no BCB; senão a referência do BCE (MXN, INR).
"""
import datetime
import logging
import os
import time
from typing import Callable

import requests

logger = logging.getLogger(__name__)

_URL_PTAX_MOEDA = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
                   "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)")
_URL_BCE = 'https://api.frankfurter.dev/v1/latest'   # taxas de referência do Banco Central Europeu (sem chave)
# Moedas que o BCB publica na PTAX (endpoint Moedas, nov/2026). Peso mexicano, rupia, naira etc. NÃO estão aqui.
MOEDAS_PTAX = {'AUD', 'CAD', 'CHF', 'DKK', 'EUR', 'GBP', 'JPY', 'NOK', 'SEK', 'USD'}
_CACHE_TTL_S = 6 * 3600
_cache_moedas: dict = {}  # {'ptax:USD' | 'bce:MXN': {'valor', 'data', 'expira'}}
_cache_usd_tela: dict = {}  # o fallback fixo da tela de ROI (só obter_ptax_usd)


def _iof_percentual() -> float:
    try:
        return float(os.getenv('IOF_CARTAO_INTERNACIONAL', '3.5'))
    except ValueError:
        return 3.5


def _com_cache(chave: str, buscar: Callable[[], tuple[float, datetime.date]], descricao: str) -> dict | None:
    """Uma cotação em reais por 1 unidade, cacheada por 6h no processo. Falha (rede, cotação zerada, resposta vazia)
    → None, com aviso no log, sem guardar nada (a próxima chamada tenta de novo)."""
    agora = time.time()
    guardada = _cache_moedas.get(chave)
    if guardada and guardada['expira'] > agora:
        return {'valor': guardada['valor'], 'data': guardada['data']}
    try:
        valor, data = buscar()
        if valor <= 0:
            raise ValueError('cotação zerada')
    except Exception as e:
        logger.warning(f"[COTACAO] ⚠️ {descricao} indisponível ({type(e).__name__}: {e})")
        return None
    _cache_moedas[chave] = {'valor': valor, 'data': data, 'expira': agora + _CACHE_TTL_S}
    return {'valor': valor, 'data': data}


def ptax_venda(moeda: str, timeout: float = 5) -> dict | None:
    """PTAX de venda mais recente (últimos 7 dias, cobre fim de semana/feriado) de uma moeda do BCB, em reais por
    1 unidade. Usa o boletim de fechamento (a PTAX oficial do dia) quando houver. {'valor', 'data'} ou None."""
    moeda = (moeda or '').upper()

    def buscar():
        hoje = datetime.date.today()
        resp = requests.get(_URL_PTAX_MOEDA, params={
            '@moeda': f"'{moeda}'",
            '@dataInicial': f"'{hoje - datetime.timedelta(days=7):%m-%d-%Y}'",
            '@dataFinalCotacao': f"'{hoje:%m-%d-%Y}'",
            '$format': 'json',
        }, timeout=timeout)
        resp.raise_for_status()
        boletins = resp.json()['value']
        fechamentos = [b for b in boletins if b.get('tipoBoletim') == 'Fechamento']
        ultima = (fechamentos or boletins)[-1]
        return float(ultima['cotacaoVenda']), datetime.date.fromisoformat(ultima['dataHoraCotacao'][:10])

    return _com_cache(f'ptax:{moeda}', buscar, f'PTAX de {moeda}')


def _referencia_bce(moeda: str, timeout: float) -> dict | None:
    def buscar():
        resp = requests.get(_URL_BCE, params={'base': moeda, 'symbols': 'BRL'}, timeout=timeout)
        resp.raise_for_status()
        corpo = resp.json()
        return float(corpo['rates']['BRL']), datetime.date.fromisoformat(corpo['date'])

    return _com_cache(f'bce:{moeda}', buscar, f'Referência do BCE para {moeda}')


def cotacao_em_reais(moeda: str, timeout: float = 5) -> dict | None:
    """Reais por 1 unidade de `moeda`: PTAX de venda do BCB quando a moeda existe lá; senão a referência do BCE
    (cobre MXN e INR; NGN não). Retorna {'valor', 'data', 'fonte': 'ptax'|'bce'} ou None."""
    moeda = (moeda or '').upper()
    if moeda in MOEDAS_PTAX:
        cot = ptax_venda(moeda, timeout)
        if cot:
            return {**cot, 'fonte': 'ptax'}
    cot = _referencia_bce(moeda, timeout)
    return {**cot, 'fonte': 'bce'} if cot else None


def obter_ptax_usd() -> dict:
    """PTAX de venda do dólar para as telas do admin. {'valor': float, 'data': date|None, 'fallback': bool}. Se o BCB
    falhar, usa COTACAO_USD_FALLBACK (padrão 5.50) com fallback=True — e só tenta o BCB de novo em 10 min (sem isso, com
    o BCB fora do ar, cada produto da tela de ROI esperaria o timeout de 10 s e a página passaria do limite do Gunicorn)."""
    agora = time.time()
    # a PTAX de verdade, se já está no cache DESTE processo (ex.: outro pedido de cotação em dólar a trouxe depois da
    # falha): vale mais que a reserva
    guardada = _cache_moedas.get('ptax:USD')
    if guardada and guardada['expira'] > agora:
        return {'valor': guardada['valor'], 'data': guardada['data'], 'fallback': False}
    if _cache_usd_tela and _cache_usd_tela['expira'] > agora:
        return {'valor': _cache_usd_tela['valor'], 'data': None, 'fallback': True}
    cot = ptax_venda('USD', timeout=10)
    if cot:
        return {**cot, 'fallback': False}
    # o BCB falhou: guarda a reserva por 10 min
    logger.warning('[COTACAO] ⚠️ Usando COTACAO_USD_FALLBACK na tela')
    try:
        valor = float(os.getenv('COTACAO_USD_FALLBACK', '5.50'))
    except ValueError:
        valor = 5.50
    _cache_usd_tela.update(valor=valor, expira=agora + 600)
    return {'valor': _cache_usd_tela['valor'], 'data': None, 'fallback': True}


def custo_wpp_para_tela(usd: float, brl: float) -> dict:
    """Monta o que as telas de ROI precisam: os dois valores originais e o total convertido em Real
    (USD × PTAX × (1 + IOF) + BRL), mais a cotação usada para mostrar na legenda."""
    ptax = obter_ptax_usd() if usd else {'valor': 0.0, 'data': None, 'fallback': False}
    iof = _iof_percentual()
    fator = ptax['valor'] * (1 + iof / 100)  # R$ por US$ já com IOF — o que a tela mostra para conferir a conta
    convertido = brl + usd * fator
    return {'usd': usd, 'brl': brl, 'convertido': convertido, 'fator': fator,
            'ptax': ptax['valor'], 'ptax_data': ptax['data'], 'ptax_fallback': ptax['fallback'], 'iof': iof}
