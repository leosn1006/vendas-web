"""
Validação forte de e-mail para o checkout web — bloqueia formatos malformados e
domínios que são claramente uma versão "quebrada" de um domínio comum (ex:
gmail.comm, hotmail.comn, gmail.compraiagrande — casos reais de bounce por
digitação identificados na análise dos e-mails de entrega que não chegaram).

MANTER SINCRONIZADO manualmente com DOMINIOS_COMUNS / validarEmailForte() em
templates/checkout.html — JS e Python não compartilham código aqui.

Usado por web/checkout.py (gerar_pix, gerar_cartao) como segunda barreira,
independente da validação do JS (defesa contra bypass client-side), e por
scripts/auditar_emails_invalidos.py para varrer pedidos existentes.

Também confirma via DNS (MX, com fallback pra A) que o domínio existe de fato —
pega domínios inventados/digitados errado que não são parecidos com nenhum dos
provedores da lista (ex: "lneditor.com.br.cc", que não bate com nada acima mas
não tem NENHUM registro DNS — bounce garantido). Isso só roda no servidor (o
JS do checkout não tem como consultar DNS do navegador), então só aparece pro
cliente depois que ele clica em "Finalizar compra", não em tempo real.
"""
import logging
import re

import dns.resolver

logger = logging.getLogger(__name__)

_resolver = dns.resolver.Resolver()
# timeout = tempo máx. por tentativa; lifetime = orçamento total da chamada resolve() (com
# retries). Mantidos baixos de propósito: essa consulta roda dentro da requisição HTTP do
# checkout, num app com poucos workers síncronos (ver Dockerfile) que também atende o webhook
# do WhatsApp — um valor alto aqui vira uma forma fácil de travar o pool inteiro (bastam
# algumas requisições simultâneas pra domínios com DNS que não responde). Pior caso agora:
# ~1.5s (MX) + ~1.5s (fallback A) = 3s por requisição, não 6s.
_resolver.timeout = 1.0
_resolver.lifetime = 1.5

DOMINIOS_COMUNS = [
    'gmail.com', 'hotmail.com', 'outlook.com', 'hotmail.com.br', 'outlook.com.br',
    'yahoo.com.br', 'yahoo.com', 'icloud.com', 'bol.com.br', 'uol.com.br',
    'terra.com.br', 'ig.com.br', 'live.com', 'msn.com', 'oi.com.br',
    'globo.com', 'globo.com.br',
]

_REGEX_ESTRUTURAL = re.compile(
    r'^[a-zA-Z0-9._%+-]+@(?:[a-zA-Z0-9_](?:[a-zA-Z0-9_-]{0,61}[a-zA-Z0-9_])?\.)+[a-zA-Z]{2,24}$'
)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        atual = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            custo = 0 if ca == cb else 1
            atual[j] = min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + custo)
        anterior = atual
    return anterior[-1]


def _dominio_existe(dominio: str):
    """
    Confirma via DNS (MX, com fallback pra A) se o domínio tem como receber e-mail.

    Retorna True (existe), False (confirmado que NÃO existe — NXDOMAIN, ou existe
    mas não tem nem MX nem A) ou None (não deu pra confirmar — timeout/falha de
    rede/servidor DNS instável). None é tratado como "válido" por quem chama:
    não bloqueamos uma compra real por uma instabilidade de DNS do nosso lado.
    """
    try:
        _resolver.resolve(dominio, 'MX')
        return True
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        pass  # domínio existe (tem SOA) mas sem MX — tenta A antes de decidir
    except Exception as e:
        logger.warning(f'[EMAIL-VALIDACAO] Falha ao consultar MX de {dominio}: {e}')
        return None

    try:
        _resolver.resolve(dominio, 'A')
        return True
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        return False  # domínio existe mas não tem nem MX nem A — não recebe e-mail
    except Exception as e:
        logger.warning(f'[EMAIL-VALIDACAO] Falha ao consultar A de {dominio}: {e}')
        return None


def validar_email(email: str) -> dict:
    """
    Retorna {'valido': bool, 'motivo': str|None, 'sugestao': str|None}.

    'motivo' só é preenchido quando valido=False (bloqueio real):
      - 'formato': regex estrutural falhou
      - 'sobra_apos_dominio': domínio começa com um domínio comum + sobra de texto
        (ex: gmail.comm, gmail.compraiagrande) — casos de altíssima confiança de typo.
      - 'dominio_inexistente': domínio fora da lista de comuns e sem NENHUM registro
        DNS (MX/A) — confirmação de que o e-mail não tem como chegar.

    Near-miss por Levenshtein NUNCA bloqueia aqui (mesma decisão do JS: é só
    sugestão) — servidor só rejeita os casos de altíssima confiança, pra não
    travar domínios corporativos/raros legítimos.
    """
    e = (email or '').strip().lower()
    if not _REGEX_ESTRUTURAL.match(e):
        return {'valido': False, 'motivo': 'formato', 'sugestao': None}

    dominio = e.split('@', 1)[1]

    # Primeiro passa por TODOS os domínios procurando igualdade exata — só depois de
    # descartar essa hipótese é que testa "começa com" (ex: sem isso, "hotmail.com.br"
    # seria injustamente bloqueado por "começar com" a entrada "hotmail.com" da lista).
    if dominio in DOMINIOS_COMUNS:
        return {'valido': True, 'motivo': None, 'sugestao': None}
    for d in DOMINIOS_COMUNS:
        if dominio.startswith(d):
            return {'valido': False, 'motivo': 'sobra_apos_dominio', 'sugestao': d}

    # Domínio fora da lista dos comuns: confirma por DNS que ele existe de verdade
    # antes de aceitar — pega casos tipo "lneditor.com.br.cc" (não parece com nenhum
    # provedor conhecido, mas também não tem MX nem A — bounce garantido).
    if _dominio_existe(dominio) is False:
        return {'valido': False, 'motivo': 'dominio_inexistente', 'sugestao': None}

    melhor = None
    for d in DOMINIOS_COMUNS:
        # Limiar fixo em 2: é só sugestão (não bloqueia), então o custo de um falso positivo
        # é baixo — e 2 é o necessário pra pegar typos comuns por transposição de letra
        # adjacente (ex: "gmial.com"), que em Levenshtein "puro" custam 2 edições, não 1.
        limiar = 2
        dist = _levenshtein(dominio, d)
        if 0 < dist <= limiar and (melhor is None or dist < melhor[1]):
            melhor = (d, dist)

    return {'valido': True, 'motivo': None, 'sugestao': melhor[0] if melhor else None}
