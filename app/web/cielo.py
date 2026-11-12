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

# Silent Order Post (SOP): o navegador manda o cartão direto para a Cielo e recebe um
# PaymentToken; o nosso backend só vê o token (PCI SAQ A-EP). Credenciais geradas no portal
# Cielo (Gestão API E-commerce > Microsserviços > Silent Order Post). Padrão = sandbox, como acima.
_SOP_CLIENT_ID     = os.getenv('CIELO_SOP_ID', '')
_SOP_CLIENT_SECRET = os.getenv('CIELO_SOP_KEY', '')
_OAUTH_URL = os.getenv('CIELO_OAUTH_URL', 'https://authsandbox.braspag.com.br/oauth2/token')
_SOP_URL   = os.getenv('CIELO_SOP_URL',
                       'https://transactionsandbox.pagador.com.br/post/api/public/v2/accesstoken')
# Repassado ao script do navegador (`environment` do bpSop_silentOrderPost).
SOP_AMBIENTE = os.getenv('CIELO_SOP_AMBIENTE', 'sandbox')

_CHAVE_REDIS_OAUTH = 'cielo:sop:oauth_token'

# Prefixo do MerchantOrderId (vazio em produção). No dev apontando para a Cielo de PRODUÇÃO, use
# ex. "dev-": os ids de pedido do dev colidem com os da produção, e o sweep da produção consulta a
# Cielo por MerchantOrderId — sem o prefixo, uma venda de teste poderia "pagar" um pedido real.
PREFIXO_PEDIDO = os.getenv('CIELO_PREFIXO_PEDIDO', '')


def merchant_order_id(pedido_id: int) -> str:
    return f'{PREFIXO_PEDIDO}{pedido_id}'

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


_cliente_redis = None


def _redis():
    """Cliente Redis único do processo (o from_url cria um pool de conexões — não recriar a cada chamada)."""
    global _cliente_redis
    if _cliente_redis is None:
        import redis
        _cliente_redis = redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'), decode_responses=True)
    return _cliente_redis


def _oauth_token(renovar: bool = False) -> str:
    """Token OAuth2 (Braspag) das credenciais do SOP, guardado no Redis até perto de expirar
    (~20 min) para os workers do gunicorn compartilharem — sem isso, cada compra faria duas
    chamadas à Cielo em vez de uma. Redis fora do ar não derruba: pede um token novo."""
    if not renovar:
        try:
            guardado = _redis().get(_CHAVE_REDIS_OAUTH)
            if guardado:
                return guardado
        except Exception as e:
            logger.warning(f'[CIELO] Redis indisponível ao ler o token OAuth do SOP: {e}')

    if not _SOP_CLIENT_ID or not _SOP_CLIENT_SECRET:
        raise RuntimeError('CIELO_SOP_ID/CIELO_SOP_KEY não configurados')
    resp = requests.post(
        _OAUTH_URL,
        auth=(_SOP_CLIENT_ID, _SOP_CLIENT_SECRET),
        data={'grant_type': 'client_credentials'},
        timeout=10,
    )
    if not resp.ok:
        _log_erro_resposta(resp)
    resp.raise_for_status()
    corpo = resp.json()
    token = corpo['access_token']
    try:
        ttl = max(60, int(corpo.get('expires_in') or 1200) - 60)
        _redis().set(_CHAVE_REDIS_OAUTH, token, ex=ttl)
    except Exception as e:
        logger.warning(f'[CIELO] Não guardou o token OAuth do SOP no Redis: {e}')
    return token


def gerar_access_token_sop() -> str:
    """POST {CIELO_SOP_URL} — AccessToken que o script do navegador usa para mandar UM cartão
    à Cielo (vale ~20 min). Um token novo a cada tentativa de pagamento. Se o token OAuth
    guardado tiver sido revogado (401), pede outro e tenta mais uma vez."""
    for tentativa in (1, 2):
        resp = requests.post(
            _SOP_URL,
            headers={'Authorization': f'Bearer {_oauth_token(renovar=tentativa == 2)}',
                     'MerchantId': _MERCHANT_ID},
            timeout=10,
        )
        if resp.status_code == 401 and tentativa == 1:
            logger.warning('[CIELO] AccessToken do SOP recusou o token OAuth (401) — renovando')
            continue
        if not resp.ok:
            _log_erro_resposta(resp)
        resp.raise_for_status()
        return resp.json()['AccessToken']
    raise RuntimeError('inalcançável')


# Tipos de credencial de cartão aceitos em criar_transacao. As wallets (Google Pay/Apple Pay)
# entram aqui como novos tipos, montando o bloco `Wallet` da Cielo — o resto do fluxo não muda.
TIPOS_CREDENCIAL = ('sop',)


def _credit_card_da_credencial(credencial: dict) -> dict:
    """Bloco Payment.CreditCard a partir da credencial vinda do checkout. Nunca recebe número
    de cartão nem CVV: só o PaymentToken gerado no navegador pelo SOP."""
    tipo = credencial.get('tipo')
    if tipo != 'sop':
        raise ValueError(f'tipo de credencial de cartão não suportado: {tipo!r}')
    credit_card = {'PaymentToken': credencial['payment_token']}
    bandeira = credencial.get('bandeira')
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
    return credit_card


def criar_transacao(merchant_order_id: str, valor_centavos: int, parcelas: int,
                     soft_descriptor: str, nome: str, cpf: str, credencial: dict) -> dict:
    """
    POST {CIELO_API_URL}sales — autorização com captura imediata (Capture=True)
    e juros sempre por conta do lojista (Interest=ByMerchant; o valor em
    `valor_centavos` já deve vir com os juros embutidos quando parcelas > 1).

    `credencial`: {'tipo': 'sop', 'payment_token': <GUID>, 'bandeira': <nosso nome>}.

    Levanta requests.HTTPError em caso de erro HTTP (o chamador decide como
    tratar timeout/erro de rede vs. negação de negócio — negação de negócio
    NÃO é erro HTTP, vem como 201 com Payment.Status != 2).
    """
    credit_card = _credit_card_da_credencial(credencial)

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
