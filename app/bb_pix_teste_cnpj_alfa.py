"""
Script de teste — API Pix "pura" do BB (não é o BB Pay) — cobrança imediata (POST /cob)
com devedor CNPJ alfanumérico (RFB, a partir de 01/08/2026).

Diferente de bb_pix.py (que só consulta PIX já recebidos), aqui tentamos CRIAR uma
cobrança — algo que a aplicação ainda não faz em produção. As credenciais BB_PIX_*
hoje só têm escopo 'pix.read' (leitura); esse script tenta pedir escopo de escrita
também, pra descobrir se a aplicação no portal do BB já tem permissão pra isso.

Execução: cd app && python bb_pix_teste_cnpj_alfa.py
"""
import os
import json
import pathlib
import logging
import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ── Configuração ──────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent.parent
load_dotenv(ROOT / '.env')

APP_KEY    = os.getenv('BB_PIX_APP_KEY', '')
BASIC      = os.getenv('BB_PIX_CLIENT_BASIC', '')
API_URL    = os.getenv('BB_PIX_API_URL', 'https://api-pix.bb.com.br/pix/v2').rstrip('/')
OAUTH_URL  = os.getenv('BB_PIX_OAUTH_URL', 'https://oauth.bb.com.br/oauth/token')

# BB_PIX_CERT_PEM/KEY no .env apontam pro caminho do container (/app/certs/...) —
# localmente usamos os mesmos certs físicos que bb_pay_teste*.py já usa.
CERT_PEM = str(ROOT / 'infra/nginx/certs/lsnlivros_chain.pem')
CERT_KEY = str(ROOT / 'infra/nginx/certs/lsnlivros.key')

CHAVE_PIX_RECEBEDOR = 'pudim@lsnlivros.com.br'  # chave e-mail

# Escopo ampliado — a app hoje só tem 'pix.read' liberado; testamos se cob.write também está.
_SCOPE = 'cob.write cob.read pix.read'


def get_token(scope: str = _SCOPE) -> str:
    logger.info(f'[TOKEN] POST {OAUTH_URL} (scope="{scope}")')
    resp = requests.post(
        OAUTH_URL,
        data={'grant_type': 'client_credentials', 'scope': scope},
        headers={
            'Authorization': f'Basic {BASIC}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        cert=(CERT_PEM, CERT_KEY),
        timeout=10,
    )
    logger.info(f'[TOKEN] Status: {resp.status_code}')
    logger.debug(f'[TOKEN] Resposta: {resp.text}')
    resp.raise_for_status()
    data = resp.json()
    logger.info(f'[TOKEN] Escopo concedido: {data.get("scope", "")}')
    return data['access_token']


def criar_cobranca_imediata(token: str) -> dict:
    """POST /cob — cria cobrança imediata (BB atribui o txid)."""
    url = f'{API_URL}/cob'
    payload = {
        'calendario': {'expiracao': 86400},  # 24h
        'devedor': {
            'cnpj': '00000000E08G12',  # alfanumérico — RFB, piloto desde 01/08/2026
            'nome': 'Teste CNPJ Alfanumerico RFB',
        },
        'valor': {'original': '0.50'},
        'chave': CHAVE_PIX_RECEBEDOR,
        'solicitacaoPagador': 'Teste CNPJ alfanumerico RFB',
    }
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    params = {'gw-dev-app-key': APP_KEY}

    logger.info(f'[COB] POST {url}')
    logger.debug(f'[COB] Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}')

    resp = requests.post(
        url,
        json=payload,
        headers=headers,
        params=params,
        cert=(CERT_PEM, CERT_KEY),
        timeout=15,
    )

    logger.info(f'[COB] Status: {resp.status_code}')
    try:
        body = resp.json()
        logger.info(f'[COB] Resposta:\n{json.dumps(body, indent=2, ensure_ascii=False)}')
    except Exception:
        logger.info(f'[COB] Resposta (texto): {resp.text}')
        body = resp.text

    return {'status_code': resp.status_code, 'body': body}


if __name__ == '__main__':
    print('=' * 60)
    print(f'API_URL  : {API_URL}')
    print(f'OAUTH_URL: {OAUTH_URL}')
    print(f'APP_KEY  : {APP_KEY[:8]}...' if APP_KEY else 'APP_KEY  : NÃO CONFIGURADO')
    print(f'CERT_PEM : {CERT_PEM}')
    print(f'CERT_KEY : {CERT_KEY}')
    print(f'CHAVE    : {CHAVE_PIX_RECEBEDOR}')
    print('=' * 60)

    try:
        token = get_token()
        print(f'\nToken obtido: {token[:20]}...\n')
    except requests.HTTPError as e:
        print(f'\n❌ Falha ao obter token com escopo de escrita: {e}')
        print('A aplicação BB_PIX provavelmente só tem escopo pix.read liberado no portal do BB.')
        raise SystemExit(1)

    resultado = criar_cobranca_imediata(token)
    body = resultado['body']

    if resultado['status_code'] in (200, 201) and isinstance(body, dict) and body.get('pixCopiaECola'):
        print('\n' + '=' * 60)
        print(f'✅ Cobrança criada: txid={body.get("txid")}')
        print(f'status: {body.get("status")}')
        print('\nCódigo copia-e-cola (PIX puro):\n')
        print(body['pixCopiaECola'])
        print('=' * 60)
    else:
        print(f'\n❌ Falha ao criar cobrança — status {resultado["status_code"]}, ver log acima.')

    print('\n✅ Concluído')
