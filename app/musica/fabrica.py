"""Monta os serviços (adaptadores das portas) a partir do .env. É o único lugar que conhece os provedores.

MUSICA_GERADOR=apiframe (MVP) | suno (conta própria, quando existir) | simulado (dev e testes).
"""
from dataclasses import dataclass
from functools import lru_cache

from musica import config, idiomas, portas


@dataclass
class Servicos:
    gerador: portas.GeradorMusica
    escritor: portas.EscritorLetra
    transcritor: portas.Transcritor | None
    audio: portas.Audio
    video: portas.Video
    repositorio: portas.Repositorio
    notificador: portas.Notificador
    agenda: portas.Agenda
    arquivos: object
    instrucoes_letra: str
    estilos: dict


def criar_gerador(nome: str) -> portas.GeradorMusica:
    if nome == 'apiframe':
        from musica.adaptadores.gerador_apiframe import GeradorApiframe
        return GeradorApiframe(config.APIFRAME_API_KEY, config.SUNO_VERSAO)
    if nome == 'suno':
        from musica.adaptadores.gerador_suno import GeradorSuno
        return GeradorSuno()
    from musica.adaptadores.gerador_simulado import GeradorSimulado
    return GeradorSimulado()


def criar_escritor() -> portas.EscritorLetra:
    if config.LETRA_SIMULADA:
        from musica.adaptadores.letra_openai import LetraSimulada
        return LetraSimulada()
    from musica.adaptadores.letra_openai import LetraOpenAI
    return LetraOpenAI(config.MODELO_LETRA, config.ESFORCO_LETRA)


@lru_cache(maxsize=1)
def servicos() -> Servicos:
    from musica.adaptadores.agenda_celery import AgendaCelery
    from musica.adaptadores.arquivos import Arquivos
    from musica.adaptadores.audio_ffmpeg import AudioFfmpeg
    from musica.adaptadores.notificador import Notificador
    from musica.adaptadores.repositorio_mysql import RepositorioMysql
    from musica.adaptadores.video_ffmpeg import VideoFfmpeg

    transcritor = None
    if config.LEGENDA_VIDEO and not config.LETRA_SIMULADA:
        from musica.adaptadores.transcritor_openai import TranscritorOpenAI
        transcritor = TranscritorOpenAI()
    repositorio = RepositorioMysql()
    return Servicos(
        gerador=criar_gerador(config.GERADOR),
        escritor=criar_escritor(),
        transcritor=transcritor,
        audio=AudioFfmpeg(),
        video=VideoFfmpeg(),
        repositorio=repositorio,
        notificador=Notificador(repositorio, config.WHATSAPP_ATIVO),
        agenda=AgendaCelery(),
        arquivos=Arquivos(config.PASTA_ARQUIVOS),
        # Conteúdo do Brasil (o padrão). Música de outro idioma lê o dela em musica/idiomas.py (casos_de_uso).
        instrucoes_letra=idiomas.instrucoes_letra(idiomas.IDIOMA_PADRAO),
        estilos=idiomas.estilos(idiomas.IDIOMA_PADRAO),
    )
