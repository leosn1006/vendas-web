"""Texto do SMS: sem acento e no máximo 160 caracteres (1 parte). Um acento (ou emoji) muda a codificação para UCS-2
e o limite cai para 70: a mensagem vira 2 ou 3 partes e custa 2 ou 3 vezes."""
import re
import unicodedata

LIMITE = 160
# Caracteres do alfabeto GSM-7 básico que existem no ASCII (os de "escape" — [ ] { } \ ^ ~ | — contam 2 e ficam fora).
_PERMITIDOS = set("@$\n\r !\"#%&'()*+,-./0123456789:;<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz")


def sem_acento(texto: str) -> str:
    """é→e, ç→c, ã→a; tira emoji e o que não for GSM-7 básico; espaços repetidos viram um."""
    decomposto = unicodedata.normalize('NFKD', str(texto or ''))
    limpo = ''.join(c for c in decomposto if not unicodedata.combining(c))
    limpo = limpo.replace('–', '-').replace('—', '-').replace('“', '"').replace('”', '"').replace('’', "'")
    limpo = ''.join(c for c in limpo if c in _PERMITIDOS)
    return re.sub(r'[ \t]+', ' ', limpo).strip()


def partes(texto: str) -> int:
    """Quantas partes a operadora cobra (GSM-7: 160 numa só; acima disso, 153 por parte)."""
    n = len(texto or '')
    return 1 if n <= LIMITE else -(-n // 153)
