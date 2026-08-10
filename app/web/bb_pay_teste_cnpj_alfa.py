"""
Script de teste — BB Pay PIX com CNPJ alfanumérico (RFB, a partir de 01/08/2026)
Execução: cd app && python web/bb_pay_teste_cnpj_alfa.py
"""
import os
import json
import pathlib
import logging
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ── Configuração ──────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).parent.parent.parent
load_dotenv(ROOT / '.env')

CLIENT_ID     = os.getenv('BB_PAY_CLIENT_ID', '')
CLIENT_SECRET = os.getenv('BB_PAY_CLIENT_SECRET_BASIC', '')
APP_KEY       = os.getenv('BB_PAY_APP_KEY', '')
API_URL       = os.getenv('BB_PAY_API_URL', 'https://checkout.mtls.api.bb.com.br/v2/').rstrip('/')
OAUTH_URL     = os.getenv('BB_PAY_OUATH_URL', 'https://oauth.bb.com.br/oauth/token')
NUMERO_CONVENIO = int(os.getenv('BB_PAY_NUMERO_CONVENIO', '275513'))

CERT_PEM = str(ROOT / 'infra/nginx/certs/lsnlivros_chain.pem')
CERT_KEY = str(ROOT / 'infra/nginx/certs/lsnlivros.key')

# ── Payload de teste ──────────────────────────────────────────────────────────
_limite = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')

PAYLOAD = {
    "geral": {
        "numeroConvenio": NUMERO_CONVENIO,
        "timestampLimiteSolicitacao": _limite,
        "pagamentoUnico": True,
        "valorSolicitacao": 0.50,
        "codigoConciliacaoSolicitacao": "teste-cnpj-alfa-1",
        "descricaoSolicitacao": "Teste CNPJ alfanumerico RFB",
        "urlCallback": ""
    },
    "devedor": {
        "tipoDocumento": 2,                    # CNPJ
        "numeroDocumento": "00000000E08G12",   # alfanumérico — precisa ir como string
        "cep": 70040010,
        "endereco": "Teste",
        "bairro": "Centro",
        "cidade": "Brasilia",
        "uf": "DF",
        "email": "teste@example.com",
        "dddTelefone": 61,
        "telefone": 999999999,
        "cpfRepresentanteEmpresa": 0
    },
    "formasPagamento": [
        {
            "codigoTipoPagamento": "PIX",
            "quantidadeParcelas": 1
        }
    ]
}


def get_token() -> str:
    logger.info(f'[TOKEN] POST {OAUTH_URL}')
    headers = {
        'Authorization': f'Basic {CLIENT_SECRET}',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    resp = requests.post(
        OAUTH_URL,
        data={'grant_type': 'client_credentials', 'scope': 'checkout.solicitacoes-requisicao checkout.solicitacoes-info checkout.pagamentos-info'},
        headers=headers,
        cert=(CERT_PEM, CERT_KEY),
        timeout=10,
    )
    logger.info(f'[TOKEN] Status: {resp.status_code}')
    logger.debug(f'[TOKEN] Resposta: {resp.text}')
    resp.raise_for_status()
    return resp.json()['access_token']


def criar_cobranca(token: str) -> dict:
    url = f'{API_URL}/solicitacoes'
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


def consultar_pagamento(token: str, id_solicitacao: str) -> dict:
    url = f'{API_URL}/pagamentos?numeroConvenio={NUMERO_CONVENIO}&numeroSolicitacao={id_solicitacao}'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'x-developer-application-key': APP_KEY,
    }

    logger.info(f'[CONSULTA] GET {url}')
    resp = requests.get(
        url,
        headers=headers,
        cert=(CERT_PEM, CERT_KEY),
        timeout=15,
    )

    logger.info(f'[CONSULTA] Status: {resp.status_code}')

    try:
        body = resp.json()
        logger.info(f'[CONSULTA] Resposta:\n{json.dumps(body, indent=2, ensure_ascii=False)}')
    except Exception:
        logger.info(f'[CONSULTA] Resposta (texto): {resp.text}')
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

    if isinstance(resultado, dict) and resultado.get('numeroSolicitacao'):
        texto_qrcode = resultado.get('informacoesPIX', {}).get('textoQrCode', '')
        print('\n' + '=' * 60)
        print(f'✅ Solicitação criada: numeroSolicitacao={resultado["numeroSolicitacao"]}')
        print(f'urlSolicitacao: {resultado.get("urlSolicitacao", "")}')
        print('\nCódigo copia-e-cola (PIX):\n')
        print(texto_qrcode)
        print('=' * 60)
    else:
        print('\n❌ Falha ao criar a solicitação — ver log acima.')

    print('\n✅ Concluído')
