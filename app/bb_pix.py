import os
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

_APP_KEY   = os.getenv('BB_PIX_APP_KEY', '')
_BASIC     = os.getenv('BB_PIX_CLIENT_BASIC', '')
_API_URL   = os.getenv('BB_PIX_API_URL', 'https://api-pix.bb.com.br/pix/v2').rstrip('/')
_OAUTH_URL = os.getenv('BB_PIX_OAUTH_URL', 'https://oauth.bb.com.br/oauth/token')
_CERT_PEM  = os.getenv('BB_PIX_CERT_PEM', '/app/certs/lsnlivros_chain.pem')
_CERT_KEY  = os.getenv('BB_PIX_CERT_KEY', '/app/certs/lsnlivros.key')


def _get_token() -> str:
    """Obtém access_token via OAuth Basic (com mTLS)."""
    resp = requests.post(
        _OAUTH_URL,
        data={'grant_type': 'client_credentials', 'scope': 'pix.read'},
        headers={
            'Authorization': f'Basic {_BASIC}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        cert=(_CERT_PEM, _CERT_KEY),
        timeout=10,
    )
    if not resp.ok:
        logger.error(f'[BB-PIX] Erro ao obter token {resp.status_code}: {resp.text}')
    resp.raise_for_status()
    logger.debug('[BB-PIX] Token obtido com sucesso')
    return resp.json()['access_token']


def consultar_todos_pix(inicio: datetime, fim: datetime) -> list:
    """
    Consulta todos os PIX recebidos no intervalo [inicio, fim].

    Args:
        inicio: datetime com timezone (ex: 00:00:00-03:00)
        fim:    datetime com timezone (ex: 23:59:59-03:00)

    Retorna lista de dicts com os campos do PIX (endToEndId, valor, chave, etc.).
    """
    token = _get_token()
    todos = []
    pagina = 0

    while True:
        resp = requests.get(
            f'{_API_URL}/pix',
            params={
                'inicio':                   inicio.isoformat(),
                'fim':                      fim.isoformat(),
                'gw-dev-app-key':           _APP_KEY,
                'paginacao.paginaAtual':    pagina,
                'paginacao.itensPorPagina': 100,
            },
            headers={
                'Authorization': f'Bearer {token}',
            },
            cert=(_CERT_PEM, _CERT_KEY),
            timeout=15,
        )
        if resp.status_code == 404:
            logger.info(f'[BB-PIX] Nenhuma transação encontrada de {inicio.date()} a {fim.date()}')
            break
        if not resp.ok:
            logger.error(f'[BB-PIX] Erro ao consultar PIX {resp.status_code}: {resp.text}')
            resp.raise_for_status()

        data = resp.json()
        paginacao = data.get('parametros', {}).get('paginacao', {})
        total_paginas = paginacao.get('quantidadeDePaginas', 1)
        total_itens = paginacao.get('quantidadeTotalDeItens', 0)
        pagina_atual = paginacao.get('paginaAtual', pagina)

        pix_pagina = data.get('pix', [])
        todos.extend(pix_pagina)

        logger.info(
            f'[BB-PIX] Página {pagina_atual + 1}/{total_paginas} — '
            f'{len(pix_pagina)} transação(ões) (total esperado: {total_itens})'
        )

        if pagina_atual >= total_paginas - 1:
            break
        pagina += 1

    logger.info(f'[BB-PIX] ✅ {len(todos)} transação(ões) recebida(s) de {inicio.date()} a {fim.date()}')
    return todos
