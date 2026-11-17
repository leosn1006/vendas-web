"""
Mensagens da cliente que não pedem resposta: só emoji, "ok", "obrigada", "amém", "segue o comprovante"...

Responder essas mensagens gasta mensagem do WhatsApp (SERVICE é cobrado) e chamada à IA, e com cliente já paga a
IA ainda respondia fora de contexto ("me envie o nome do pagador"). Decisão de negócio (nov/2026): ficam sem
resposta em qualquer estado do pedido, menos os avisos de pagamento em pedido não pago (ver _EXPRESSOES_PAGAMENTO).

O filtro é conservador de propósito: a mensagem inteira precisa ser composta só de expressões da lista (e emojis).
"obrigada, mas não abriu" ou "segue o comprovante, cadê o bônus?" têm texto fora da lista e vão para a IA.
"""
import re
import unicodedata

_TAMANHO_MAXIMO = 60

# Expressões já normalizadas (minúsculas, sem acento, sem pontuação). Da mais longa para a mais curta não importa:
# a correspondência é feita por regex que aceita qualquer sequência delas.
_EXPRESSOES = [
    # confirmação curta
    r'ok', r'okay', r'oks', r'okk+', r'blz', r'beleza', r'certo', r'ta bom', r'ta', r'ta certo', r'show',
    r'perfeito', r'otimo', r'combinado', r'entendi', r'recebi',
    r'recebido', r'tudo certo', r'tudo bem', r'legal', r'top', r'joia', r'massa',
    # agradecimento e bênção
    r'obrigad[ao]s?', r'obg', r'brigad[ao]', r'muito obrigad[ao]', r'muitissimo obrigad[ao]', r'grat[ao]',
    r'gratidao', r'agradeco', r'eu que agradeco', r'de nada', r'valeu', r'vlw', r'amem', r'amem amem',
    r'deus (continue |continua )?(te |lhe |vos |o |a )?(abencoe|abencoa|abencoando)( sempre| muito| voce| vc)*', r'fique com deus', r'fica com deus',
    r'que deus (te |lhe )?(abencoe|abencoa)( sempre| muito)*', r'igualmente', r'pra voce tambem',
    r'para voce tambem', r'(um )?(beijo|bjo|bjs|bj|abraco|abracos)', r'(beijos|abracos) no coracao',
    # saudação de despedida ("oi"/"olá" sozinhos abrem conversa e ficam de fora)
    r'bom dia', r'boa tarde', r'boa noite',
    # tratamento carinhoso solto
    r'querida', r'meu bem', r'minha linda', r'linda', r'amiga', r'flor',
]

# Aviso de pagamento ("segue o comprovante", "já paguei", "pronto, enviei"): só silencia pedido JÁ PAGO. Em pedido
# não pago vai para a IA, que registra o pagamento informado; o registro espera 30 s, então se a imagem do
# comprovante chegar junto ela tem prioridade. (Antes, silenciado sempre: se a imagem falhasse, a cliente que disse
# ter pago ficava sem resposta e continuava recebendo cobrança.)
_EXPRESSOES_PAGAMENTO = [
    r'segue', r'segui', r'segue (o |a )?(comprovante|pix|pagamento)( do pix| de pagamento)?',
    r'(ai|aqui) (esta|ta|vai)( o| a)? (comprovante|pix|pagamento)( do pix| de pagamento)?',
    r'(esta )?(ai|aqui)', r'(o )?comprovante( do pix| de pagamento)?', r'confira', r'confere',
    r'confira por (gentileza|favor)', r'olha( o| a)? (comprovante|pix)', r'olhe( o| a)? (comprovante|pix)',
    r'(ja )?(paguei|fiz o pix|fiz o pagamento)( viu)?', r'pronto', r'feito', r'enviado', r'enviei', r'ja enviei',
]

# Saudação sozinha ("Bom dia", "Boa tarde, tudo bem") costuma abrir conversa: vai para a IA. Junto de outra
# expressão ("Obrigada, boa noite") é despedida e silencia.
_SAUDACOES = [r'bom dia', r'boa tarde', r'boa noite', r'tudo bem', r'tudo bom', r'querida', r'amiga', r'flor',
              r'meu bem', r'minha linda', r'linda']

# Risco à vida: checagem determinística usada quando a IA está silenciada (pedido em análise pelo admin). Fora
# disso, quem decide é a IA (ferramenta notificar_admin, motivo 'risco_vida').
_RE_RISCO_VIDA = re.compile(
    r'suicid|\bme matar\b|\bvou me matar|tirar (a )?(minha )?propria vida|tirar (a )?minha vida|'
    r'acabar com (a )?minha vida|\bquero morrer\b(?! de)|vontade de morrer\b(?! de)|nao quero (mais )?viver|'
    r'me machucar de proposito')

# Entre duas expressões precisa haver espaço (ou " e "): sem isso "tata" ou "okta" passariam como "ta"+"ta".
_SEPARADOR = r'(?:\s+(?:e\s+|eu\s+)?)'


def _compilar(expressoes):
    alternativas = '|'.join(f'(?:{e})' for e in expressoes)
    return re.compile(rf'^(?:{alternativas})(?:{_SEPARADOR}(?:{alternativas}))*$')


_RE_SO_SAUDACAO = _compilar(_SAUDACOES)
_RE_SEMPRE = _compilar(_EXPRESSOES)
_RE_PAGO = _compilar(_EXPRESSOES + _EXPRESSOES_PAGAMENTO)


def _normalizar(texto: str) -> str:
    sem_acento = ''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c))
    # Tudo que não é letra/número/espaço (emoji, pontuação, símbolos) vira espaço.
    so_palavras = re.sub(r'[^\w\s]|_', ' ', sem_acento.lower())
    return re.sub(r'\s+', ' ', so_palavras).strip()


def mensagem_sem_resposta(texto: str | None, pedido_pago: bool = False) -> bool:
    """True se a mensagem não pede resposta (ver docstring do módulo). `pedido_pago` libera também os avisos de
    pagamento ("segue o comprovante", "já paguei"), que em pedido não pago precisam chegar à IA."""
    if texto is None:
        return False
    bruto = texto.strip()
    if not bruto or len(bruto) > _TAMANHO_MAXIMO or '?' in bruto:
        return False
    normalizado = _normalizar(bruto)
    if not normalizado:
        return True  # só emoji / símbolos / pontuação
    if any(c.isdigit() for c in normalizado):
        return False  # "coloquei 30", chave Pix, valores: deixa a IA ver
    if _RE_SO_SAUDACAO.match(normalizado):
        return False
    regex = _RE_PAGO if pedido_pago else _RE_SEMPRE
    return bool(regex.match(normalizado))


def fala_em_risco_a_vida(texto: str | None) -> bool:
    return bool(texto) and bool(_RE_RISCO_VIDA.search(_normalizar(texto)))
