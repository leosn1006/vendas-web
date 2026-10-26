"""Tema do checkout por produto (migration 093): a moldura escura e a cor de destaque da landing de onde a cliente
vem, para o checkout não parecer outro site. Os cards do formulário continuam brancos (leitura fácil para o
público 35+); daqui saem só as cores derivadas das duas do produto. Sem cores (ou cor inválida) = None = o
checkout claro de sempre."""
import re

_HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
_BRANCO = (255, 255, 255)
_PRETO = (0, 0, 0)


def _rgb(hexa):
    return tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return '#' + ''.join(f'{round(c):02X}' for c in rgb)


def _misturar(rgb, outra, quanto):
    """`quanto` (0–1) de `outra` sobre `rgb`."""
    return tuple(a + (b - a) * quanto for a, b in zip(rgb, outra))


def _luminancia(rgb):
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(rgb_a, rgb_b):
    """Razão de contraste WCAG entre duas cores (1 a 21)."""
    claro, escuro = sorted((_luminancia(rgb_a), _luminancia(rgb_b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


def _legivel_no_branco(rgb):
    """O destaque escurecido aos poucos até dar 4,5:1 sobre o card branco (total, preços, método ativo)."""
    quanto = 0.0
    cor = rgb
    while contraste(cor, _BRANCO) < 4.5 and quanto < 1:
        quanto += 0.05
        cor = _misturar(rgb, _PRETO, quanto)
    return cor


def tema_checkout(produto):
    """As variáveis de CSS do tema do produto, ou None (checkout claro padrão)."""
    fundo = (produto or {}).get('checkout_cor_fundo') or ''
    destaque = (produto or {}).get('checkout_cor_destaque') or ''
    if not (_HEX.match(fundo) and _HEX.match(destaque)):
        return None
    f, d = _rgb(fundo), _rgb(destaque)
    # Texto do botão (grande e em negrito: 3:1 basta): branco como nas landings quando dá (vermelho do Fatia);
    # em destaque claro (rosa da Música, esmeralda do Tempero), o próprio destaque bem escuro.
    sobre = _BRANCO if contraste(d, _BRANCO) >= 3 else _misturar(d, _PRETO, 0.88)
    marca = ((produto or {}).get('checkout_marca') or '').strip()
    return {
        'fundo': _hex(f),
        'fundo_2': _hex(_misturar(f, _BRANCO, 0.06)),
        'linha': _hex(_misturar(f, _BRANCO, 0.14)),
        'destaque': _hex(d),
        'destaque_hover': _hex(_misturar(d, _BRANCO, 0.2)),
        'sobre_destaque': _hex(sobre),
        'destaque_texto': _hex(_legivel_no_branco(d)),
        'destaque_claro': _hex(_misturar(d, _BRANCO, 0.9)),
        'destaque_claro_2': _hex(_misturar(d, _BRANCO, 0.82)),
        'destaque_borda': _hex(_misturar(d, _BRANCO, 0.45)),
        'marca': marca,
        'inicial': marca[:1].upper(),
    }
