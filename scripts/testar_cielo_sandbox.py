"""
Testa (sandbox/homologacao) a criacao de uma transacao de cartao de credito
via API E-commerce Cielo, usando as credenciais em CIELO_MERCHANT_ID /
CIELO_MERCHANT_KEY do .env.

So valida o fluxo basico de autorizacao (POST /1/sales) contra o ambiente de
homologacao da Cielo — nao mexe em nada do banco/app.

Numeros de cartao de teste (ultimo digito define o resultado simulado):
  0, 1, 4 -> autorizado
  2 -> nao autorizado (negada)
  3 -> nao autorizado (cartao expirado)
  5 -> nao autorizado (cartao bloqueado)
  6 -> nao autorizado (timeout)
  7 -> nao autorizado (cartao cancelado)
  8 -> nao autorizado (problema com o cartao)

Uso:
  python scripts/testar_cielo_sandbox.py
  python scripts/testar_cielo_sandbox.py --status negada
  python scripts/testar_cielo_sandbox.py --status expirado --valor 55.90
"""
import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.join(_AQUI, '..'))
load_dotenv()

_ULTIMO_DIGITO = {
    'aprovada': '1',
    'negada': '2',
    'expirado': '3',
    'bloqueado': '5',
    'timeout': '6',
    'cancelado': '7',
    'problema': '8',
}


def _cartao_teste(status: str) -> str:
    digito = _ULTIMO_DIGITO[status]
    return f'402400715376319{digito}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--status', default='aprovada', choices=sorted(_ULTIMO_DIGITO),
                         help='Resultado simulado pelo cartao de teste (padrao: aprovada).')
    parser.add_argument('--valor', type=float, default=10.00, help='Valor em reais (padrao: 10.00).')
    args = parser.parse_args()

    merchant_id = os.environ['CIELO_MERCHANT_ID']
    merchant_key = os.environ['CIELO_MERCHANT_KEY']
    api_url = os.environ.get('CIELO_API_URL', 'https://apisandbox.cieloecommerce.cielo.com.br/1/')

    cartao = _cartao_teste(args.status)
    valor_centavos = round(args.valor * 100)

    payload = {
        'MerchantOrderId': 'teste-cielo-sandbox-001',
        'Customer': {
            'Name': 'Cliente Teste',
            'Identity': '12345678909',
            'IdentityType': 'CPF',
        },
        'Payment': {
            'Type': 'CreditCard',
            'Amount': valor_centavos,
            'Installments': 1,
            'SoftDescriptor': 'LBELivros',
            'Capture': True,
            'CreditCard': {
                'CardNumber': cartao,
                'Holder': 'Cliente Teste',
                'ExpirationDate': '12/2030',
                'SecurityCode': '123',
                'Brand': 'Visa',
            },
        },
    }

    print(f'>>> Enviando transacao de teste (status esperado: {args.status}, cartao {cartao})...\n')

    resp = requests.post(
        f'{api_url}sales',
        headers={
            'MerchantId': merchant_id,
            'MerchantKey': merchant_key,
            'Content-Type': 'application/json',
        },
        json=payload,
        timeout=30,
    )

    print(f'HTTP {resp.status_code}')
    try:
        corpo = resp.json()
        print(json.dumps(corpo, indent=2, ensure_ascii=False))
        pagamento = corpo.get('Payment', {}) if isinstance(corpo, dict) else {}
        if pagamento:
            print(f"\n>>> Status={pagamento.get('Status')}  "
                  f"ReturnCode={pagamento.get('ReturnCode')}  "
                  f"ReturnMessage={pagamento.get('ReturnMessage')!r}  "
                  f"PaymentId={pagamento.get('PaymentId')}")
    except ValueError:
        print(resp.text)


if __name__ == '__main__':
    main()
