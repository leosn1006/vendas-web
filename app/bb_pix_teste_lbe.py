"""
Script de teste — valida a integração mTLS + OAuth do BB Pix para a nova empresa
LBE LIVROS LTDA (credenciais BB_PIX_*_LBE, ainda não usadas em produção).

Consulta os PIX recebidos em uma data específica (default: ontem).

Execução: cd app && python bb_pix_teste_lbe.py [dd/mm/yyyy]
"""
import os
import sys
import json
import pathlib
import logging
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).parent.parent
load_dotenv(ROOT / '.env')

APP_KEY   = os.getenv('BB_PIX_APP_KEY_LBE', '')
BASIC     = os.getenv('BB_PIX_CLIENT_BASIC_LBE', '')
API_URL   = os.getenv('BB_PIX_API_URL', 'https://api-pix.bb.com.br/pix/v2').rstrip('/')
OAUTH_URL = os.getenv('BB_PIX_OAUTH_URL', 'https://oauth.bb.com.br/oauth/token')

CERT_PEM = str(ROOT / 'infra/nginx/certs/lbe-livros_chain.pem')
CERT_KEY = str(ROOT / 'infra/nginx/certs/lbe-livros.key')

_SP_TZ = timezone(timedelta(hours=-3))


def get_token() -> str:
    logger.info(f'[TOKEN] POST {OAUTH_URL}')
    resp = requests.post(
        OAUTH_URL,
        data={'grant_type': 'client_credentials', 'scope': 'pix.read'},
        headers={
            'Authorization': f'Basic {BASIC}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        cert=(CERT_PEM, CERT_KEY),
        timeout=10,
    )
    logger.info(f'[TOKEN] Status: {resp.status_code}')
    if not resp.ok:
        logger.error(f'[TOKEN] Resposta: {resp.text}')
    resp.raise_for_status()
    return resp.json()['access_token']


def consultar_pix(token: str, inicio: datetime, fim: datetime) -> list:
    todos = []
    pagina = 0
    while True:
        resp = requests.get(
            f'{API_URL}/pix',
            params={
                'inicio':                   inicio.isoformat(),
                'fim':                      fim.isoformat(),
                'gw-dev-app-key':           APP_KEY,
                'paginacao.paginaAtual':    pagina,
                'paginacao.itensPorPagina': 100,
            },
            headers={'Authorization': f'Bearer {token}'},
            cert=(CERT_PEM, CERT_KEY),
            timeout=15,
        )
        logger.info(f'[PIX] página {pagina} — status {resp.status_code}')
        if resp.status_code == 404:
            logger.info('[PIX] Nenhuma transação encontrada no período.')
            break
        if not resp.ok:
            logger.error(f'[PIX] Resposta: {resp.text}')
        resp.raise_for_status()
        body = resp.json()
        todos.extend(body.get('pix', []))
        pag = body.get('parametros', {}).get('paginacao', {})
        if pagina >= pag.get('quantidadeDePaginas', 1) - 1:
            break
        pagina += 1
    return todos


if __name__ == '__main__':
    if len(sys.argv) > 1:
        base = datetime.strptime(sys.argv[1], '%d/%m/%Y').replace(tzinfo=_SP_TZ)
    else:
        base = datetime.now(_SP_TZ) - timedelta(days=1)

    inicio = base.replace(hour=0, minute=0, second=0, microsecond=0)
    fim    = base.replace(hour=23, minute=59, second=59, microsecond=0)

    print('=' * 60)
    print(f'API_URL  : {API_URL}')
    print(f'OAUTH_URL: {OAUTH_URL}')
    print(f'APP_KEY  : {APP_KEY[:8]}...' if APP_KEY else 'APP_KEY  : NAO CONFIGURADO')
    print(f'CERT_PEM : {CERT_PEM}')
    print(f'CERT_KEY : {CERT_KEY}')
    print(f'Período  : {inicio.isoformat()} a {fim.isoformat()}')
    print('=' * 60)

    try:
        token = get_token()
        print(f'\n✅ Token obtido (mTLS + OAuth OK): {token[:20]}...\n')
    except requests.exceptions.SSLError as e:
        print(f'\n❌ Falha de mTLS (certificado): {e}')
        raise SystemExit(1)
    except requests.HTTPError as e:
        print(f'\n❌ Falha ao obter token: {e}')
        raise SystemExit(1)

    pix_list = consultar_pix(token, inicio, fim)

    print(f'\n{"=" * 60}')
    print(f'✅ {len(pix_list)} PIX encontrado(s) em {base.date()}')
    print('=' * 60)
    for p in pix_list:
        print(json.dumps({
            'endToEndId': p.get('endToEndId'),
            'valor':      p.get('valor'),
            'horario':    p.get('horario'),
            'chave':      p.get('chave'),
            'pagador':    p.get('pagador', {}).get('nome'),
        }, indent=2, ensure_ascii=False))

    print('\n✅ Concluído')
