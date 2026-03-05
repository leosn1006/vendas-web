"""
Script de teste — BB Pay (Boleto)
Execução: cd app && python bb_pay_teste.py
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

CLIENT_ID     = os.getenv('BB_PAY_CLIENT_ID', '')
CLIENT_SECRET = os.getenv('BB_PAY_CLIENT_SECRET_BASIC', '')
APP_KEY       = os.getenv('BB_PAY_APP_KEY', '')
API_URL       = os.getenv('BB_PAY_API_URL', 'https://checkout.mtls.api.bb.com.br/v2/').rstrip('/')
OAUTH_URL     = os.getenv('BB_PAY_OUATH_URL', 'https://oauth.bb.com.br/oauth/token')

CERT_PEM = str(ROOT / 'infra/nginx/certs/lsnlivros_chain.pem')
CERT_KEY = str(ROOT / 'infra/nginx/certs/lsnlivros.key')

# ── Payload de teste ──────────────────────────────────────────────────────────
PAYLOAD = {
    "geral": {
        "numeroConvenio": 275513,
        "timestampLimiteSolicitacao": "2026-04-30T03:00:00Z",
        "pagamentoUnico": True,
        "valorSolicitacao": 10.9,
        "codigoConciliacaoSolicitacao": "12",
        "descricaoSolicitacao": "Teste primeiro",
        "urlCallback": ""
    },
    "devedor": {
        "tipoDocumento": 1,
        "numeroDocumento": 2055466178,
        "cep": 73252200,
        "endereco": "RK",
        "bairro": "Sobradinho",
        "cidade": "Brasilia",
        "uf": "DF",
        "email": "larissa@gmail.com",
        "dddTelefone": 61,
        "telefone": 983012211,
        "cpfRepresentanteEmpresa": 0
    },
    "vencimento": {
        "data": "2026-03-20",
        "multaValorFixo": 0,
        "jurosPercentual": 0.2,
        "descontos": [
            {
                "dataLimite": "2026-03-10",
                "valorFixo": 1,
                "valorPercentual": 0
            }
        ]
    },
    "formasPagamento": [
        {
            "codigoTipoPagamento": "BLT",
            "quantidadeParcelas": 1
        }
    ]
}


def get_token() -> str:
    logger.info(f'[TOKEN] POST {OAUTH_URL}')
    # BB_PAY_CLIENT_SECRET_BASIC já é o base64(client_id:client_secret) pronto
    # Enviamos diretamente no header em vez de deixar requests re-encodar
    headers = {
        'Authorization': f'Basic {CLIENT_SECRET}',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    resp = requests.post(
        OAUTH_URL,
        data={'grant_type': 'client_credentials', 'scope': 'checkout.solicitacoes-requisicao'},
        headers=headers,
        cert=(CERT_PEM, CERT_KEY),
        timeout=10,
    )
    logger.info(f'[TOKEN] Status: {resp.status_code}')
    logger.debug(f'[TOKEN] Resposta: {resp.text}')
    resp.raise_for_status()
    return resp.json()['access_token']


def criar_cobranca(token: str) -> dict:
    url = f'{API_URL}/checkouts'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'x-developer-application-key': APP_KEY,
    }

    logger.info(f'[COBRANÇA] POST {url}')
    logger.debug(f'[COBRANÇA] Payload: {json.dumps(PAYLOAD, indent=2, ensure_ascii=False)}')

    resp = requests.post(
        url,
        json=PAYLOAD,
        headers=headers,
        cert=(CERT_PEM, CERT_KEY),
        timeout=15,
    )

    logger.info(f'[COBRANÇA] Status: {resp.status_code}')
    logger.debug(f'[COBRANÇA] Headers resposta: {dict(resp.headers)}')

    try:
        body = resp.json()
        logger.info(f'[COBRANÇA] Resposta:\n{json.dumps(body, indent=2, ensure_ascii=False)}')
    except Exception:
        logger.info(f'[COBRANÇA] Resposta (texto): {resp.text}')
        body = resp.text

    return body


if __name__ == '__main__':
    print('=' * 60)
    print(f'API_URL  : {API_URL}')
    print(f'OAUTH_URL: {OAUTH_URL}')
    print(f'APP_KEY  : {APP_KEY[:8]}...' if APP_KEY else 'APP_KEY  : NÃO CONFIGURADO')
    print(f'CERT_PEM : {CERT_PEM}')
    print(f'CERT_KEY : {CERT_KEY}')
    print('=' * 60)

    token = get_token()
    print(f'\nToken obtido: {token[:20]}...\n')

    resultado = criar_cobranca(token)
    print('\n✅ Concluído')
