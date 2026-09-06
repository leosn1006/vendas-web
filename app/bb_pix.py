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


def consultar_todos_pix(inicio: datetime, fim: datetime, tenant_slug: str = 'lsn-livros', token: str = None) -> list:
    """
    Consulta todos os PIX recebidos no intervalo [inicio, fim] para a conta
    (tenant_slug) informada.

    Args:
        inicio: datetime com timezone (ex: 00:00:00-03:00)
        fim:    datetime com timezone (ex: 23:59:59-03:00)
        tenant_slug: 'lsn-livros' (default) ou 'lbe-livros'
        token: access_token já obtido (opcional) — evita um novo OAuth quando o
            caller já tem um token válido pra essa conta (ex: fluxo_pix_bb.executar,
            que busca PIX e devoluções em sequência pro mesmo tenant/janela).

    Retorna lista de dicts com os campos do PIX (endToEndId, valor, chave, etc.).
    """
    conta = _conta(tenant_slug)
    token = token or _get_token(tenant_slug)
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


def consultar_devolucoes_pix(inicio: datetime, fim: datetime, tenant_slug: str = 'lsn-livros', token: str = None) -> list:
    """
    Consulta devoluções de PIX no intervalo [inicio, fim] para a conta (tenant_slug)
    informada. O intervalo filtra pela data da DEVOLUÇÃO, não pela data do PIX
    original recebido (confirmado empiricamente contra a API real do BB).

    Retorna lista PLANA de dicts, um por devolução individual (um PIX pode ter
    N devoluções — a API devolve cada PIX com um array `devolucoes` aninhado,
    que é achatado aqui), cada um carregando `endToEndId` e `chave` do PIX
    original (a `chave` permite resolver produto_id por fallback mesmo quando o
    PIX original ainda não foi persistido — ver database.salvar_devolucao_pix):
        {endToEndId, chave, rtrId, valor, natureza, descricao, motivo, status,
         horario_solicitacao, horario_liquidacao}

    IMPORTANTE: o BB rejeita (400 OperacaoInvalida) intervalos [inicio, fim] de
    5 dias ou mais — diferente de /pix, que aceita janelas maiores. Confirmado
    empiricamente contra produção. Por isso todo caller (fluxo_pix_bb.executar/
    executar_periodo) usa sempre uma janela de 1 dia por vez.

    Args:
        token: access_token já obtido (opcional) — evita um novo OAuth quando o
            caller já tem um token válido pra essa conta.
    """
    conta = _conta(tenant_slug)
    token = token or _get_token(tenant_slug)
    todos = []
    pagina = 0

    while True:
        resp = requests.get(
            f'{_API_URL}/pix-bb/devolucoes',
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
            logger.info(f'[BB-PIX-DEVOL][{tenant_slug}] Nenhuma devolução encontrada de {inicio.date()} a {fim.date()}')
            break
        if not resp.ok:
            logger.error(f'[BB-PIX-DEVOL][{tenant_slug}] Erro ao consultar devoluções {resp.status_code}: {resp.text}')
            resp.raise_for_status()

        data = resp.json()
        paginacao = data.get('parametros', {}).get('paginacao', {})
        total_paginas = paginacao.get('quantidadeDePaginas', 1)
        total_itens = paginacao.get('quantidadeTotalDeItens', 0)
        pagina_atual = paginacao.get('paginaAtual', pagina)

        pix_pagina = data.get('pix', [])
        todos.extend(pix_pagina)

        logger.info(
            f'[BB-PIX-DEVOL][{tenant_slug}] Página {pagina_atual + 1}/{total_paginas} — '
            f'{len(pix_pagina)} PIX com devolução (total esperado: {total_itens})'
        )

        if pagina_atual >= total_paginas - 1:
            break
        pagina += 1

    achatado = []
    for item in todos:
        for dev in item.get('devolucoes', []):
            horario = dev.get('horario') or {}
            achatado.append({
                'endToEndId':          item.get('endToEndId'),
                'chave':               item.get('chave'),
                'rtrId':               dev.get('rtrId'),
                'valor':               dev.get('valor'),
                'natureza':            dev.get('natureza'),
                'descricao':           dev.get('descricao'),
                'motivo':              dev.get('motivo'),
                'status':              dev.get('status'),
                'horario_solicitacao': horario.get('solicitacao'),
                'horario_liquidacao':  horario.get('liquidacao'),
            })

    logger.info(f'[BB-PIX-DEVOL][{tenant_slug}] ✅ {len(achatado)} devolução(ões) de {inicio.date()} a {fim.date()}')
    return achatado
