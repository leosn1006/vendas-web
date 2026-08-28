import os
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

_API_URL   = os.getenv('BB_PIX_API_URL', 'https://api-pix.bb.com.br/pix/v2').rstrip('/')
_OAUTH_URL = os.getenv('BB_PIX_OAUTH_URL', 'https://oauth.bb.com.br/oauth/token')

# Credenciais por conta/tenant BB Pix. Cada conta só retorna PIX das próprias
# chaves cadastradas — a origem (tenant_slug) é conhecida estruturalmente no
# momento da consulta, não precisa ser inferida depois pela chave_pix.
_CONTAS = {
    'lsn-livros': {
        'app_key':  os.getenv('BB_PIX_APP_KEY', ''),
        'basic':    os.getenv('BB_PIX_CLIENT_BASIC', ''),
        'cert_pem': os.getenv('BB_PIX_CERT_PEM', '/app/certs/lsnlivros_chain.pem'),
        'cert_key': os.getenv('BB_PIX_CERT_KEY', '/app/certs/lsnlivros.key'),
    },
    'lbe-livros': {
        'app_key':  os.getenv('BB_PIX_APP_KEY_LBE', ''),
        'basic':    os.getenv('BB_PIX_CLIENT_BASIC_LBE', ''),
        'cert_pem': os.getenv('BB_PIX_CERT_PEM_LBE', '/app/certs/lbe-livros_chain.pem'),
        'cert_key': os.getenv('BB_PIX_CERT_KEY_LBE', '/app/certs/lbe-livros.key'),
    },
}


def _conta(tenant_slug: str) -> dict:
    conta = _CONTAS.get(tenant_slug)
    if not conta:
        raise ValueError(f'[BB-PIX] tenant_slug desconhecido: {tenant_slug!r}')
    return conta


def _get_token(tenant_slug: str = 'lsn-livros') -> str:
    """Obtém access_token via OAuth Basic (com mTLS) para a conta informada."""
    conta = _conta(tenant_slug)
    resp = requests.post(
        _OAUTH_URL,
        data={'grant_type': 'client_credentials', 'scope': 'pix.read'},
        headers={
            'Authorization': f"Basic {conta['basic']}",
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        cert=(conta['cert_pem'], conta['cert_key']),
        timeout=10,
    )
    if not resp.ok:
        logger.error(f'[BB-PIX][{tenant_slug}] Erro ao obter token {resp.status_code}: {resp.text}')
    resp.raise_for_status()
    logger.debug(f'[BB-PIX][{tenant_slug}] Token obtido com sucesso')
    return resp.json()['access_token']


def consultar_todos_pix(inicio: datetime, fim: datetime, tenant_slug: str = 'lsn-livros') -> list:
    """
    Consulta todos os PIX recebidos no intervalo [inicio, fim] para a conta
    (tenant_slug) informada.

    Args:
        inicio: datetime com timezone (ex: 00:00:00-03:00)
        fim:    datetime com timezone (ex: 23:59:59-03:00)
        tenant_slug: 'lsn-livros' (default) ou 'lbe-livros'

    Retorna lista de dicts com os campos do PIX (endToEndId, valor, chave, etc.).
    """
    conta = _conta(tenant_slug)
    token = _get_token(tenant_slug)
    todos = []
    pagina = 0

    while True:
        resp = requests.get(
            f'{_API_URL}/pix',
            params={
                'inicio':                   inicio.isoformat(),
                'fim':                      fim.isoformat(),
                'gw-dev-app-key':           conta['app_key'],
                'paginacao.paginaAtual':    pagina,
                'paginacao.itensPorPagina': 100,
            },
            headers={
                'Authorization': f'Bearer {token}',
            },
            cert=(conta['cert_pem'], conta['cert_key']),
            timeout=15,
        )
        if resp.status_code == 404:
            logger.info(f'[BB-PIX][{tenant_slug}] Nenhuma transação encontrada de {inicio.date()} a {fim.date()}')
            break
        if not resp.ok:
            logger.error(f'[BB-PIX][{tenant_slug}] Erro ao consultar PIX {resp.status_code}: {resp.text}')
            resp.raise_for_status()

        data = resp.json()
        paginacao = data.get('parametros', {}).get('paginacao', {})
        total_paginas = paginacao.get('quantidadeDePaginas', 1)
        total_itens = paginacao.get('quantidadeTotalDeItens', 0)
        pagina_atual = paginacao.get('paginaAtual', pagina)

        pix_pagina = data.get('pix', [])
        todos.extend(pix_pagina)

        logger.info(
            f'[BB-PIX][{tenant_slug}] Página {pagina_atual + 1}/{total_paginas} — '
            f'{len(pix_pagina)} transação(ões) (total esperado: {total_itens})'
        )

        if pagina_atual >= total_paginas - 1:
            break
        pagina += 1

    logger.info(f'[BB-PIX][{tenant_slug}] ✅ {len(todos)} transação(ões) recebida(s) de {inicio.date()} a {fim.date()}')
    return todos
