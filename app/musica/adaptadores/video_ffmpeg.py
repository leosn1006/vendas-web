"""Video com Pillow + ffmpeg (adaptador da porta Video). Videoclipe: as fotos da cliente + a música, em vídeo vertical (Status, Reels, WhatsApp).

Como funciona:
1. As fotos são acertadas (giro do celular, recorte 9:16) com o Pillow.
2. Cada foto vira um trecho com um zoom lento (ffmpeg zoompan) e transição suave.
3. Abre e fecha com um cartão com o título da música, o nome de quem recebe e de quem dá.
4. As fotos se repetem até cobrir a música inteira.

Tamanho 720x1280 (leve para mandar no WhatsApp). Leva de 1 a 3 minutos no servidor.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from musica.adaptadores.audio_ffmpeg import FFMPEG
from musica.dominio.modelos import ErroVideo

LARGURA, ALTURA, FPS = 720, 1280, 30
FONTES = Path(__file__).resolve().parent.parent / "static" / "fonts"
COR_FUNDO = (28, 25, 23)
COR_DESTAQUE = (225, 29, 72)
FORMATOS_ACEITOS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FOTOS = 20


def preparar_foto(origem, destino):
    """Gira conforme o celular, recorta em 9:16 (no dobro do tamanho, para o zoom) e salva em JPEG."""
    with Image.open(origem) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageOps.fit(img, (LARGURA * 2, ALTURA * 2), method=Image.LANCZOS, centering=(0.5, 0.4))
        img.save(destino, "JPEG", quality=88)


def _fonte(nome, tamanho, peso):
    fonte = ImageFont.truetype(str(FONTES / nome), tamanho)
    try:
        fonte.set_variation_by_name(peso)
    except (OSError, ValueError):
        pass
    return fonte


def _quebrar(texto, fonte, largura, desenho):
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = (atual + " " + palavra).strip()
        if desenho.textlength(teste, font=fonte) <= largura:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    return linhas + ([atual] if atual else [])


def cartao(destino, titulo, linha_cima, linha_baixo):
    """Cartão de abertura/fechamento (fundo escuro, título grande, faixa na cor da marca)."""
    img = Image.new("RGB", (LARGURA * 2, ALTURA * 2), COR_FUNDO)
    d = ImageDraw.Draw(img)
    margem = 140
    d.rectangle([0, 0, 24, ALTURA * 2], fill=COR_DESTAQUE)
    f_titulo = _fonte("BricolageGrotesque.ttf", 150, "Bold")
    f_texto = _fonte("Figtree.ttf", 64, "Medium")
    linhas = _quebrar(titulo, f_titulo, LARGURA * 2 - margem * 2, d)
    altura_titulo = len(linhas) * 165
    y = (ALTURA * 2 - altura_titulo) // 2
    d.text((margem, y - 140), linha_cima, font=f_texto, fill=(214, 211, 209))
    for i, linha in enumerate(linhas):
        d.text((margem, y + i * 165), linha, font=f_titulo, fill=(255, 255, 255))
    d.text((margem, y + altura_titulo + 60), linha_baixo, font=f_texto, fill=(214, 211, 209))
    img.save(destino, "JPEG", quality=92)


def _trecho(imagem, saida, segundos, zoom=True):
    quadros = int(segundos * FPS)
    z = "min(zoom+0.0007,1.15)" if zoom else "1"
    filtro = (f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={quadros}:s={LARGURA}x{ALTURA}:fps={FPS},"
              f"fade=t=in:st=0:d=0.5,fade=t=out:st={segundos - 0.5}:d=0.5,scale=out_range=tv,format=yuv420p")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(imagem), "-vf", filtro, "-frames:v", str(quadros),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-color_range", "tv",
                    "-r", str(FPS), str(saida)], check=True)


def duracao_audio(arquivo):
    """Duração em segundos (lida da saída do ffmpeg)."""
    r = subprocess.run([FFMPEG, "-i", str(arquivo)], capture_output=True, text=True)
    for linha in r.stderr.splitlines():
        if "Duration:" in linha:
            h, m, s = linha.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise ErroVideo("não deu para ler a duração da música")


# Os textos dos cartões no Brasil (o padrão); outro idioma manda os dele (textos.json → "video").
TEXTOS_PADRAO = {'abertura_para': 'Para {para}', 'abertura_sub': 'Uma música feita só para você',
                 'fechamento': 'Com carinho,'}


def montar(fotos, musica, saida, titulo, para, de, legenda_ass=None, textos=None):
    """Gera o videoclipe. `fotos` já preparadas com preparar_foto(). `legenda_ass`: arquivo .ass da letra (opcional).
    `textos`: as frases dos cartões de abertura e fechamento no idioma da música (padrão: as do Brasil)."""
    textos = {**TEXTOS_PADRAO, **(textos or {})}
    if not fotos:
        raise ErroVideo("nenhuma foto")
    total = duracao_audio(musica)
    abertura = fechamento = 3.5
    tempo_fotos = max(3.0, total - abertura - fechamento)
    # Cada foto fica entre 4 e 8 segundos; se tiver poucas fotos, elas se repetem.
    por_foto = min(8.0, max(4.0, tempo_fotos / len(fotos)))
    quantidade = max(len(fotos), round(tempo_fotos / por_foto))
    por_foto = tempo_fotos / quantidade

    pasta = Path(tempfile.mkdtemp(prefix="videoclipe-"))
    try:
        cartao(pasta / "abertura.jpg", titulo, textos['abertura_para'].replace('{para}', para), textos['abertura_sub'])
        Path(saida).parent.mkdir(parents=True, exist_ok=True)
        with Image.open(pasta / "abertura.jpg") as capa:   # imagem que aparece antes do play
            capa.resize((LARGURA, ALTURA), Image.LANCZOS).save(Path(saida).with_name("capa.jpg"), "JPEG", quality=85)
        cartao(pasta / "fechamento.jpg", titulo, textos['fechamento'], de)
        trechos = [pasta / "t000.mp4"]
        _trecho(pasta / "abertura.jpg", trechos[0], abertura, zoom=False)
        for i in range(quantidade):
            saida_trecho = pasta / f"t{i + 1:03d}.mp4"
            _trecho(fotos[i % len(fotos)], saida_trecho, por_foto)
            trechos.append(saida_trecho)
        fim = pasta / f"t{quantidade + 1:03d}.mp4"
        _trecho(pasta / "fechamento.jpg", fim, fechamento, zoom=False)
        trechos.append(fim)

        lista = pasta / "lista.txt"
        lista.write_text("".join(f"file '{t}'\n" for t in trechos))
        Path(saida).parent.mkdir(parents=True, exist_ok=True)
        if legenda_ass:   # com legenda, o vídeo precisa ser recodificado para "queimar" a letra
            caminho_ass = str(legenda_ass).replace("\\", "/").replace(":", "\\:")
            video_opcoes = ["-vf", f"ass={caminho_ass}:fontsdir={FONTES}", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "23", "-pix_fmt", "yuv420p"]
        else:
            video_opcoes = ["-c:v", "copy"]
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-i", str(musica),
                        "-map", "0:v", "-map", "1:a", *video_opcoes, "-c:a", "aac", "-b:a", "160k",
                        "-af", f"afade=t=out:st={max(0, total - 2.5)}:d=2.5", "-shortest", "-movflags", "+faststart",
                        str(saida)], check=True)
    except subprocess.CalledProcessError as erro:
        raise ErroVideo("o ffmpeg falhou ao montar o vídeo") from erro
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


class VideoFfmpeg:
    """Adaptador da porta portas.Video."""
    max_fotos = MAX_FOTOS

    def preparar_foto(self, origem, destino):
        preparar_foto(origem, destino)

    def montar(self, fotos, musica, saida, titulo, para, de, legenda_ass=None, textos=None):
        montar(fotos, musica, saida, titulo, para, de, legenda_ass=legenda_ass, textos=textos)
