"""Transcritor pela OpenAI (whisper-1, tempo de cada palavra), para a legenda do videoclipe.
Custa uns R$ 0,10 por música de 3 minutos. O encaixe da letra fica em dominio/legenda.py."""
from openai import OpenAI


class TranscritorOpenAI:
    def palavras(self, arquivo_mp3, dica: str, idioma: str = 'pt') -> list[dict]:
        with open(arquivo_mp3, 'rb') as audio:
            r = OpenAI(timeout=180).audio.transcriptions.create(
                model='whisper-1', file=audio, language=idioma, response_format='verbose_json',
                timestamp_granularities=['word'], prompt=dica[:800],
            )
        return [{'palavra': w.word, 'inicio': w.start, 'fim': w.end} for w in (r.words or [])]
