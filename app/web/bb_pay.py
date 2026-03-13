import os
import logging
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_CLIENT_SECRET = os.getenv('BB_PAY_CLIENT_SECRET_BASIC', '')
_APP_KEY       = os.getenv('BB_PAY_APP_KEY', '')
_API_URL       = os.getenv('BB_PAY_API_URL', 'https://checkout.mtls.api.bb.com.br/v2/').rstrip('/')
_OAUTH_URL     = os.getenv('BB_PAY_OUATH_URL', 'https://oauth.bb.com.br/oauth/token')

# Caminhos do certificado mTLS — /app/certs/ no Docker, ou configurável via env
_CERT_PEM = os.getenv('BB_PAY_CERT_PEM', '/app/certs/lsnlivros_chain.pem')
_CERT_KEY = os.getenv('BB_PAY_CERT_KEY', '/app/certs/lsnlivros.key')

_SCOPES = ('checkout.solicitacoes-requisicao '
           'checkout.solicitacoes-info '
           'checkout.pagamentos-info')


def _get_token() -> str:
    """Obtém access_token via OAuth Basic (com mTLS)."""
    resp = requests.post(
        _OAUTH_URL,
        data={'grant_type': 'client_credentials', 'scope': _SCOPES},
        headers={
            'Authorization': f'Basic {_CLIENT_SECRET}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        cert=(_CERT_PEM, _CERT_KEY),
        timeout=10,
    )
    resp.raise_for_status()
    logger.debug('[BB-PAY] Token obtido com sucesso')
    return resp.json()['access_token']


def criar_solicitacao(valor: float, pedido_web_id: int,
                      numero_convenio: int, descricao: str = '',
                      url_retorno: str = '') -> dict:
    """
    Cria uma solicitação de cobrança PIX no BB Pay.

    Retorna dict com:
      - numero_solicitacao : int  — identificador da cobrança
      - qrcode_texto       : str  — string copia-e-cola EMV (usar para gerar QR)
      - url_solicitacao    : str  — link direto para a página de pagamento BB Pay
      - valor              : float
    """
    token = _get_token()
    logger.info(f'[BB-PAY] Criando solicitação — pedido #{pedido_web_id} valor={valor:.2f}, url_retorno="{url_retorno}"')
    # Limite de 24 h a partir de agora (UTC)
    limite = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')

    payload = {
        'geral': {
            'numeroConvenio':               numero_convenio,
            'timestampLimiteSolicitacao':   limite,
            'pagamentoUnico':               True,
            'valorSolicitacao':             round(valor, 2),
            'codigoConciliacaoSolicitacao': str(pedido_web_id),
            'descricaoSolicitacao':         descricao or f'Pedido #{pedido_web_id}',
            'urlCallback':                  '',
            'urlRetorno':                   url_retorno,
        },
        'formasPagamento': [
            {'codigoTipoPagamento': 'PIX', 'quantidadeParcelas': 1}
        ],
    }

    headers = {
        'Authorization':               f'Bearer {token}',
        'Content-Type':                'application/json',
        'x-developer-application-key': _APP_KEY,
    }

    resp = requests.post(
        f'{_API_URL}/solicitacoes',
        json=payload,
        headers=headers,
        cert=(_CERT_PEM, _CERT_KEY),
        timeout=15,
    )

    if not resp.ok:
        logger.error(f'[BB-PAY] ❌ Erro {resp.status_code}: {resp.text}')
    resp.raise_for_status()

    data = resp.json()
    numero = data.get('numeroSolicitacao')
    logger.info(f'[BB-PAY] ✅ Solicitação criada — pedido #{pedido_web_id} numero={numero}')

    return {
        'numero_solicitacao': numero,
        'qrcode_texto':       data.get('informacoesPIX', {}).get('textoQrCode', ''),
        'url_solicitacao':    data.get('urlSolicitacao', ''),
        'valor':              valor,
    }


def consultar_pagamentos(numero_solicitacao: int, numero_convenio: int) -> dict:
    """
    Consulta pagamentos de uma solicitação pelo número de solicitação.

    Retorna dict com:
      - pago      : bool      — True se houver pagamento com codigoEstadoPagamento == 200
      - pagamento : dict|None — dados do primeiro pagamento confirmado
    """
    token = _get_token()
    headers = {
        'Authorization':               f'Bearer {token}',
        'x-developer-application-key': _APP_KEY,
    }
    resp = requests.get(
        f'{_API_URL}/pagamentos',
        params={'numeroConvenio': numero_convenio, 'numeroSolicitacao': numero_solicitacao},
        headers=headers,
        cert=(_CERT_PEM, _CERT_KEY),
        timeout=10,
    )
    if not resp.ok:
        logger.error(f'[BB-PAY] ❌ Erro status {resp.status_code}: {resp.text}')
    resp.raise_for_status()

    data = resp.json()
    lista = data.get('listaPagamentos', [])
    pagamento = next((p for p in lista if p.get('codigoEstadoPagamento') == 200), None)

    if pagamento:
        logger.info(f'[BB-PAY] Pagamento confirmado — dados completos: {pagamento}')

    return {
        'pago':      pagamento is not None,
        'pagamento': pagamento,
    }
