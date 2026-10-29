"""Onde ficam os arquivos de cada música (pasta privada; o Flask serve só depois de conferir o acesso).

storage/musica/<token>/completa/<n>.mp3   música inteira (só depois de paga)
storage/musica/<token>/previa/<n>.mp3     trecho grátis
storage/musica/<token>/video/             fotos/, letra.ass, videoclipe.mp4, capa.jpg
"""
import os
import re
import shutil
from pathlib import Path


class Arquivos:
    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)

    def pasta(self, token: str) -> Path:
        if not re.fullmatch(r'[0-9a-f]{32}', token or ''):   # o token vira nome de pasta: nada além de hex
            raise ValueError('token inválido')
        return self.raiz / token

    def completa(self, token: str, numero: int) -> Path:
        return self.pasta(token) / 'completa' / f'{int(numero)}.mp3'

    def previa(self, token: str, numero: int) -> Path:
        return self.pasta(token) / 'previa' / f'{int(numero)}.mp3'

    def pasta_video(self, token: str) -> Path:
        return self.pasta(token) / 'video'

    def videoclipe(self, token: str) -> Path:
        return self.pasta_video(token) / 'videoclipe.mp4'

    def capa_video(self, token: str) -> Path:
        return self.pasta_video(token) / 'capa.jpg'

    def copiar_audios(self, de_token: str, para_token: str, numeros) -> None:
        """Admin "refazer a música": as versões completas e as prévias do rascunho passam para a música da cliente.
        Cada arquivo é copiado para um temporário e trocado com os.replace (atômico): quem estiver ouvindo nunca pega
        um arquivo pela metade. Em duas fases: primeiro copia TODOS para temporários (se faltar um arquivo ou disco,
        nada da original mudou), só depois troca. Uma versão que a original tinha a mais (ex.: 2 e o rascunho só 1) sai."""
        numeros = {int(n) for n in numeros}
        trocas = []
        try:
            for tipo in ('completa', 'previa'):
                (self.pasta(para_token) / tipo).mkdir(parents=True, exist_ok=True)
                for numero in numeros:
                    destino = self.pasta(para_token) / tipo / f'{numero}.mp3'
                    temporario = destino.with_suffix('.mp3.novo')
                    shutil.copyfile(self.pasta(de_token) / tipo / f'{numero}.mp3', temporario)
                    trocas.append((temporario, destino))
        except OSError:
            for temporario, _ in trocas:
                temporario.unlink(missing_ok=True)
            raise
        for temporario, destino in trocas:
            os.replace(temporario, destino)
        for tipo in ('completa', 'previa'):
            for sobra in (self.pasta(para_token) / tipo).glob('*.mp3'):
                if sobra.stem.isdigit() and int(sobra.stem) not in numeros:
                    sobra.unlink(missing_ok=True)

    def tem_fotos(self, token: str) -> bool:
        return any((self.pasta_video(token) / 'fotos').glob('*.jpg'))

    def apagar(self, token: str) -> None:
        shutil.rmtree(self.pasta(token), ignore_errors=True)
