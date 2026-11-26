"""Cliente da API de vendas da Hotmart — SÓ LEITURA (GET). Ver docs/HOTMART.md → "API de vendas".

Token OAuth client_credentials (válido ~48 h) guardado no processo; um 401 renova uma vez. `listar` percorre todas
as páginas (page_token). Nada aqui pede reembolso nem altera venda.
"""
import logging
import time

import requests

from hotmart import config

logger = logging.getLogger(__name__)

_TIMEOUT = 20
_MAX_POR_PAGINA = 500
_MAX_PAGINAS = 200            # trava contra laço infinito de paginação
_token: dict = {}             # {'valor': str, 'expira': float}


class ApiDesligada(Exception):
    """Sem credencial no .env: a conciliação não roda."""


class ErroApi(Exception):
    pass


def configurada() -> bool:
    return bool(config.CLIENT_ID and config.CLIENT_SECRET and config.CLIENT_TOKEN)


def _basic() -> str:
    token = config.CLIENT_TOKEN.strip()
    return token if token.lower().startswith('basic ') else f'Basic {token}'


def _obter_token(renovar: bool = False) -> str:
    if not configurada():
        raise ApiDesligada('HOTMART_CLIENT_ID / _SECRET / _TOKEN não configurados')
    agora = time.time()
    if not renovar and _token.get('valor') and _token['expira'] > agora:
        return _token['valor']
    resp = requests.post(config.URL_TOKEN, timeout=_TIMEOUT, headers={'Authorization': _basic()},
                         params={'grant_type': 'client_credentials', 'client_id': config.CLIENT_ID,
                                 'client_secret': config.CLIENT_SECRET})
    if resp.status_code != 200:
        raise ErroApi(f'token: HTTP {resp.status_code}')
    corpo = resp.json()
    # Renova 1 h antes de vencer (a Hotmart dá ~48 h).
    _token.update(valor=corpo['access_token'], expira=agora + max(int(corpo.get('expires_in') or 0) - 3600, 60))
    return _token['valor']


def _get(caminho: str, params: dict) -> dict:
    url = f'{config.API_URL}/payments/api/v1/{caminho}'
    for tentativa in (1, 2):
        resp = requests.get(url, params=params, timeout=_TIMEOUT,
                            headers={'Authorization': f'Bearer {_obter_token(renovar=tentativa == 2)}'})
        if resp.status_code == 401 and tentativa == 1:
            continue                      # token vencido/revogado: renova e tenta uma vez
        if resp.status_code != 200:
            try:
                detalhe = resp.json().get('error_description') or resp.text[:200]
            except ValueError:
                detalhe = resp.text[:200]
            raise ErroApi(f'{caminho}: HTTP {resp.status_code} {detalhe}')
        return resp.json()
    raise ErroApi(f'{caminho}: 401 mesmo com token novo')


def listar(caminho: str, **filtros) -> list[dict]:
    """Todos os itens de um endpoint de lista (ex.: 'sales/history'), seguindo a paginação."""
    itens, params = [], {**{k: v for k, v in filtros.items() if v is not None}, 'max_results': _MAX_POR_PAGINA}
    for _ in range(_MAX_PAGINAS):
        corpo = _get(caminho, params)
        itens.extend(corpo.get('items') or [])
        proxima = (corpo.get('page_info') or {}).get('next_page_token')
        if not proxima:
            return itens
        params = {**params, 'page_token': proxima}
    logger.error(f'[HOTMART-API] ❌ {caminho}: mais de {_MAX_PAGINAS} páginas — parei')
    return itens
