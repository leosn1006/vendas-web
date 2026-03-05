import os
import logging
import requests

logger = logging.getLogger(__name__)

_CLIENT_ID     = os.getenv('BB_PAY_CLIENT_ID', '')
_CLIENT_SECRET = os.getenv('BB_PAY_CLIENT_SECRET_BASIC', '')
_APP_KEY       = os.getenv('BB_PAY_APP_KEY', '')
_API_URL       = os.getenv('BB_PAY_API_URL', 'https://checkout.mtls.api.bb.com.br/v2/').rstrip('/')
_OAUTH_URL     = os.getenv('BB_PAY_OUATH_URL', 'https://oauth.bb.com.br/oauth/token')

# Caminhos do certificado mTLS — /app/certs/ no Docker, ou configurável via env
_CERT_PEM = os.getenv('BB_PAY_CERT_PEM', '/app/certs/lsnlivros_chain.pem')
_CERT_KEY = os.getenv('BB_PAY_CERT_KEY', '/app/certs/lsnlivros.key')


def _get_token() -> str:
    """Obtém access_token via OAuth Basic (sem mTLS)."""
    # _CLIENT_SECRET já é base64(client_id:client_secret) pronto — usar direto no header
    resp = requests.post(
        _OAUTH_URL,
        data={'grant_type': 'client_credentials', 'scope': 'checkout.solicitacoes-requisicao'},
        headers={
            'Authorization': f'Basic {_CLIENT_SECRET}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        cert=(_CERT_PEM, _CERT_KEY),   # BB exige mTLS também no token
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()['access_token']
    logger.debug('[BB-PAY] Token obtido com sucesso')
    return token


def gerar_qrcode_pix(valor: float, pedido_id: int, descricao: str = '') -> dict:
    """
    Gera QR Code PIX dinâmico no BB Pay via mTLS.

    Retorna dict com:
      - txid          : identificador da cobrança no BB
      - qrcode_texto  : string copia-e-cola (EMV)
      - qrcode_imagem : imagem PNG em base64
      - valor         : valor cobrado
    """
    token = _get_token()

    payload = {
        'valor': {'original': round(valor, 2)},
        'solicitacaoPagador': descricao or f'Pedido #{pedido_id}',
        'infoAdicionais': [{'nome': 'pedido_id', 'valor': str(pedido_id)}],
    }

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'x-developer-application-key': _APP_KEY,
    }

    resp = requests.post(
        f'{_API_URL}/pix/qrcodes-dinamicos',
        json=payload,
        headers=headers,
        cert=(_CERT_PEM, _CERT_KEY),   # mTLS — apresenta o certificado do cliente
        timeout=15,
    )

    if not resp.ok:
        logger.error(f'[BB-PAY] ❌ Erro {resp.status_code}: {resp.text}')
    resp.raise_for_status()

    data = resp.json()
    logger.info(f"[BB-PAY] ✅ QR Code gerado — pedido #{pedido_id} txid={data.get('txid')}")

    return {
        'txid':          data.get('txid'),
        'qrcode_texto':  data.get('qrcode'),
        'qrcode_imagem': data.get('imagemQrcode'),
        'valor':         valor,
    }


if __name__ == '__main__':
    import json
    import pathlib
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(message)s')

    # Caminhos locais para execução fora do Docker
    ROOT = pathlib.Path(__file__).parent.parent
    os.environ.setdefault('BB_PAY_CERT_PEM', str(ROOT / 'infra/nginx/certs/lsnlivros_chain.pem'))
    os.environ.setdefault('BB_PAY_CERT_KEY', str(ROOT / 'infra/nginx/certs/lsnlivros.key'))
    load_dotenv(ROOT / '.env')

    # Recarrega variáveis após o load_dotenv
    globals().update({
        '_CLIENT_ID':     os.getenv('BB_PAY_CLIENT_ID', ''),
        '_CLIENT_SECRET': os.getenv('BB_PAY_CLIENT_SECRET_BASIC', ''),
        '_APP_KEY':       os.getenv('BB_PAY_APP_KEY', ''),
        '_API_URL':       os.getenv('BB_PAY_API_URL', 'https://checkout.mtls.api.bb.com.br/v2/').rstrip('/'),
        '_OAUTH_URL':     os.getenv('BB_PAY_OUATH_URL', 'https://oauth.bb.com.br/oauth/token'),
        '_CERT_PEM':      os.environ['BB_PAY_CERT_PEM'],
        '_CERT_KEY':      os.environ['BB_PAY_CERT_KEY'],
    })

    resultado = gerar_qrcode_pix(valor=10.00, pedido_id=0, descricao='Teste BB Pay')
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
