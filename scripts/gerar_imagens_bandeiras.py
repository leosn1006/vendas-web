"""
Gera os ícones .webp de bandeira de cartão usados no checkout (detecção de
bandeira ao digitar o número). Não são os logotipos oficiais das bandeiras —
são badges simples (cor + nome) geradas localmente, pra não depender de
hotlink de asset de terceiros sem licença confirmada. Se um dia quiserem os
logotipos oficiais pixel-perfect, basta baixar do media kit de cada bandeira
e substituir os arquivos em app/static/images/bandeiras/ (mesmo nome/tamanho).

Uso: python scripts/gerar_imagens_bandeiras.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

DESTINO = os.path.join(os.path.dirname(__file__), '..', 'static', 'images', 'bandeiras')
LARGURA, ALTURA = 240, 150
FONTE_BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'

BANDEIRAS = [
    ('visa',       '#1A1F71', '#FFFFFF', 'VISA'),
    ('mastercard', '#16171C', '#FFFFFF', 'mastercard'),
    ('elo',        '#000000', '#FFCB05', 'elo'),
    ('amex',       '#2E77BC', '#FFFFFF', 'AMEX'),
    ('hipercard',  '#B3131B', '#FFFFFF', 'hipercard'),
]


def _badge(cor_fundo: str, cor_texto: str, texto: str) -> Image.Image:
    img = Image.new('RGB', (LARGURA, ALTURA), cor_fundo)
    draw = ImageDraw.Draw(img)
    tamanho_fonte = 44 if len(texto) <= 5 else 34
    fonte = ImageFont.truetype(FONTE_BOLD, tamanho_fonte)
    bbox = draw.textbbox((0, 0), texto, font=fonte)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((LARGURA - w) / 2 - bbox[0], (ALTURA - h) / 2 - bbox[1]), texto, font=fonte, fill=cor_texto)
    return _arredondar(img)


def _arredondar(img: Image.Image, raio: int = 18) -> Image.Image:
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], radius=raio, fill=255)
    fundo = Image.new('RGBA', img.size, (0, 0, 0, 0))
    fundo.paste(img, (0, 0), mask)
    return fundo


def _generico() -> Image.Image:
    """Ícone genérico de cartão — usado antes de qualquer detecção de bandeira."""
    img = Image.new('RGB', (LARGURA, ALTURA), '#E5E7EB')
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 32, LARGURA, 58], fill='#9CA3AF')  # tarja magnética
    draw.rounded_rectangle([20, 88, 70, 108], radius=4, fill='#D1D5DB')  # linha decorativa
    draw.rounded_rectangle([20, 116, 120, 128], radius=4, fill='#D1D5DB')
    return _arredondar(img)


def main():
    os.makedirs(DESTINO, exist_ok=True)
    for nome, cor_fundo, cor_texto, texto in BANDEIRAS:
        caminho = os.path.join(DESTINO, f'{nome}.webp')
        _badge(cor_fundo, cor_texto, texto).save(caminho, 'WEBP', quality=90)
        print(f'✅ {caminho}')

    caminho_generico = os.path.join(DESTINO, 'generico.webp')
    _generico().save(caminho_generico, 'WEBP', quality=90)
    print(f'✅ {caminho_generico}')


if __name__ == '__main__':
    main()
