"""
Integração com a API E-commerce Cielo (cartão de crédito) — modelo clássico
MerchantId/MerchantKey, sem OAuth/mTLS. Espelha app/web/bb_pay.py: só faz a
chamada HTTP e devolve o dado cru; decidir o que fazer com o resultado
(mudar estado do pedido, disparar e-mail, etc.) é responsabilidade de quem
chama, não deste módulo.
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

_MERCHANT_ID   = os.getenv('CIELO_MERCHANT_ID', '')
_MERCHANT_KEY  = os.getenv('CIELO_MERCHANT_KEY', '')
_API_URL       = os.getenv('CIELO_API_URL', 'https://apisandbox.cieloecommerce.cielo.com.br/1/').rstrip('/')
_API_QUERY_URL = os.getenv('CIELO_API_QUERY_URL', 'https://apiquerysandbox.cieloecommerce.cielo.com.br/1/').rstrip('/')

# Nosso nome interno (bandeira_bin.py, ícones em static/images/bandeiras/) -> valor exigido
# pelo BrandEnum da Cielo, só onde os dois divergem. Confirmado empiricamente no sandbox.
_BRAND_CIELO = {
    'mastercard': 'Master',
}


def _headers() -> dict:
    return {
        'MerchantId': _MERCHANT_ID,
        'MerchantKey': _MERCHANT_KEY,
        'Content-Type': 'application/json',
    }


def _log_erro_resposta(resp: requests.Response) -> None:
    """Loga só o essencial do erro — nunca resp.text cru (pode ecoar payload).
    A Cielo usa dois formatos de corpo de erro: {"Payment": {...}} pra negação de negócio
    (cartão recusado etc.) e uma lista [{"Code":.., "Message":..}] pra erro de gateway/
    validação (credencial, campo inválido, feature não habilitada) — sem isso, erros desse
    segundo tipo logavam ReturnCode/ReturnMessage sempre None, escondendo a causa real."""
    try:
        corpo = resp.json()
        if isinstance(corpo, dict):
            payment = corpo.get('Payment', {})
            logger.error(
                f'[CIELO] Erro HTTP {resp.status_code} — '
                f'ReturnCode={payment.get("ReturnCode")} ReturnMessage={payment.get("ReturnMessage")!r}'
            )
        elif isinstance(corpo, list):
            mensagens = '; '.join(
                f'{item.get("Code")}: {item.get("Message")}'
                for item in corpo if isinstance(item, dict)
            )
            logger.error(f'[CIELO] Erro HTTP {resp.status_code} — {mensagens}')
        else:
            logger.error(f'[CIELO] Erro HTTP {resp.status_code} — corpo inesperado: {corpo!r}')
    except ValueError:
        logger.error(f'[CIELO] Erro HTTP {resp.status_code} (corpo não é JSON)')


def criar_transacao(merchant_order_id: str, valor_centavos: int, parcelas: int,
                     soft_descriptor: str, nome: str, cpf: str,
                     numero_cartao: str, titular: str, validade: str,
                     cvv: str, bandeira: str) -> dict:
    """
    POST {CIELO_API_URL}sales — autorização com captura imediata (Capture=True)
    e juros sempre por conta do lojista (Interest=ByMerchant; o valor em
    `valor_centavos` já deve vir com os juros embutidos quando parcelas > 1).

    `validade` no formato "MM/AAAA".

    Levanta requests.HTTPError em caso de erro HTTP (o chamador decide como
    tratar timeout/erro de rede vs. negação de negócio — negação de negócio
    NÃO é erro HTTP, vem como 201 com Payment.Status != 2).
    """
    credit_card = {
        'CardNumber': numero_cartao,
        'Holder': titular,
        'ExpirationDate': validade,
        'SecurityCode': cvv,
    }
    if bandeira:
        # Brand é um enum forte na API da Cielo — mandar string vazia quebra com 400
        # ("Error converting value '' to type BrandEnum"), confirmado no sandbox. Omitir a
        # chave inteira (em vez de mandar vazio) funciona normalmente (Brand volta "Undefined"
        # na resposta, mas a autorização segue).
        #
        # 'mastercard' (nosso nome interno, usado no ícone/cache/auditoria) NÃO é um valor
        # válido do BrandEnum — só 'Master' é aceito (confirmado no sandbox: 'Mastercard' e
        # 'MasterCard' quebram com o mesmo erro 999 "Error converting value..."; causou falha
        # real em produção pra um cliente com cartão Mastercard). Visa/Elo/Amex/Hipercard já
        # batem com o enum sem tradução.
        credit_card['Brand'] = _BRAND_CIELO.get(bandeira, bandeira)

    payload = {
        'MerchantOrderId': merchant_order_id,
        'Customer': {
            'Name': nome,
            'Identity': cpf,
            'IdentityType': 'CPF',
        },
        'Payment': {
            'Type': 'CreditCard',
            'Amount': valor_centavos,
            'Installments': parcelas,
            'SoftDescriptor': soft_descriptor,
            'Capture': True,
            'Interest': 'ByMerchant',
            'Provider': 'Cielo',
            'CreditCard': credit_card,
        },
    }

    logger.info(f'[CIELO] Criando transação — MerchantOrderId={merchant_order_id} '
                f'valor={valor_centavos} parcelas={parcelas}')

    resp = requests.post(f'{_API_URL}/sales', json=payload, headers=_headers(), timeout=30)

    if not resp.ok:
        _log_erro_resposta(resp)
    resp.raise_for_status()

    corpo = resp.json()
    payment = corpo.get('Payment', {})
    logger.info(f'[CIELO] Resposta — Status={payment.get("Status")} '
                f'ReturnCode={payment.get("ReturnCode")} PaymentId={payment.get("PaymentId")}')
    return corpo


def consultar_bin(bin_numero: str) -> dict:
    """GET {CIELO_API_QUERY_URL}cardBin/{bin} — 6 a 8 primeiros dígitos do cartão.
    Requer habilitação prévia da Consulta BIN pelo suporte Cielo (erro 323 se não habilitado).
    Timeout curto (4s) de propósito: essa chamada também acontece no caminho crítico da
    autorização (gerar_cartao) quando o BIN ainda não está em cache — como uma falha nunca é
    cacheada (pode ser transitória) e é tentada de novo a cada request, um timeout longo aqui
    vira lentidão real no checkout toda vez que a Consulta BIN estiver fora do ar."""
    resp = requests.get(f'{_API_QUERY_URL}/cardBin/{bin_numero}', headers=_headers(), timeout=4)
    if not resp.ok:
        _log_erro_resposta(resp)
    resp.raise_for_status()
    return resp.json()


def consultar_por_merchant_order_id(merchant_order_id: str) -> dict:
    """GET {CIELO_API_QUERY_URL}sales?merchantOrderId=<id> — janela de 3 meses."""
    resp = requests.get(
        f'{_API_QUERY_URL}/sales',
        params={'merchantOrderId': merchant_order_id},
        headers=_headers(),
        timeout=15,
    )
    if not resp.ok:
        _log_erro_resposta(resp)
    resp.raise_for_status()
    return resp.json()


def consultar_por_payment_id(payment_id: str) -> dict:
    """GET {CIELO_API_QUERY_URL}sales/{PaymentId}."""
    resp = requests.get(f'{_API_QUERY_URL}/sales/{payment_id}', headers=_headers(), timeout=15)
    if not resp.ok:
        _log_erro_resposta(resp)
    resp.raise_for_status()
    return resp.json()
