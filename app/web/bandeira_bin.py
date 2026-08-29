"""
Resolve a bandeira de um cartão a partir do BIN (6 primeiros dígitos),
usando a Consulta BIN da Cielo (cielo.consultar_bin) com cache em
`bandeira_bin` — BIN praticamente nunca muda de bandeira, então o cache não
tem expiração.

Usado tanto pelo endpoint de UI (troca o ícone no blur do campo de número)
quanto pela autorização (web/checkout.py:gerar_cartao) — nesse segundo caso
o cache é o que importa mais: evita depender de uma chamada de rede extra
no meio do caminho crítico de pagamento.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Payment.Provider (Cielo) → nosso enum lowercase (nome dos arquivos em
# static/images/bandeiras/). Só verificado empiricamente pra Visa até agora
# — ajustar aqui se a Cielo devolver uma string diferente da esperada pras
# outras bandeiras (ex: "AMERICAN EXPRESS" em vez de "AMEX").
_MAPA_BANDEIRA = {
    'VISA': 'visa',
    'MASTERCARD': 'mastercard',
    'ELO': 'elo',
    'AMEX': 'amex',
    'AMERICAN EXPRESS': 'amex',
    'HIPERCARD': 'hipercard',
}


def _mapear_bandeira(provider: str) -> str | None:
    return _MAPA_BANDEIRA.get((provider or '').strip().upper())


def resolver_bandeira(numero_ou_bin: str) -> str | None:
    """
    Bandeira do cartão a partir dos 6 primeiros dígitos (cache-aside):
    - Cache hit: devolve direto (inclusive quando o cache guardou NULL —
      significa "já consultamos, não é bandeira com ícone").
    - Cache miss: consulta a Cielo, persiste o resultado (mesmo se NULL) e
      devolve.
    - Erro/timeout na Cielo: NÃO cacheia (pode ser falha transitória) e
      devolve None — quem chamar decide o fallback (nunca bloqueia a compra).
    """
    from database import get_bandeira_bin_cache, salvar_bandeira_bin_cache
    import web.cielo as cielo

    # Só dígitos — protege contra bin= malformado vindo direto da querystring (o caminho da
    # autorização já manda dígitos limpos, mas o endpoint HTTP é chamável diretamente).
    bin_numero = re.sub(r'\D', '', numero_ou_bin or '')[:6]
    if len(bin_numero) < 6:
        return None

    cache = get_bandeira_bin_cache(bin_numero)
    if cache is not None:
        return cache['bandeira']

    try:
        resposta = cielo.consultar_bin(bin_numero)
    except Exception as e:
        logger.warning(f'[BANDEIRA-BIN] Falha ao consultar BIN {bin_numero} na Cielo: {e}')
        return None

    bandeira = _mapear_bandeira(resposta.get('Provider'))
    salvar_bandeira_bin_cache(
        bin_numero, bandeira,
        card_type=resposta.get('CardType'),
        issuer=resposta.get('Issuer'),
        foreign_card=resposta.get('ForeignCard'),
        corporate_card=resposta.get('CorporateCard'),
        prepaid=resposta.get('Prepaid'),
    )
    return bandeira
