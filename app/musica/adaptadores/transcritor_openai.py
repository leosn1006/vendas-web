"""Transcritor pela OpenAI (whisper-1, tempo de cada palavra), para a legenda do videoclipe.
Custa uns R$ 0,10 por música de 3 minutos. O encaixe da letra fica em dominio/legenda.py.
DitadoOpenAI: o microfone da tela de lembranças (fala → texto, até 2 min; ~US$ 0,006 por minuto)."""
from openai import OpenAI


class TranscritorOpenAI:
    def palavras(self, arquivo_mp3, dica: str, idioma: str = 'pt') -> list[dict]:
        with open(arquivo_mp3, 'rb') as audio:
            r = OpenAI(timeout=180).audio.transcriptions.create(
                model='whisper-1', file=audio, language=idioma, response_format='verbose_json',
                timestamp_granularities=['word'], prompt=dica[:800],
            )
        return [{'palavra': w.word, 'inicio': w.start, 'fim': w.end} for w in (r.words or [])]


class DitadoOpenAI:
    """Fala → texto para a caixa de lembranças. O áudio não é guardado (o caso de uso apaga o arquivo na hora)."""

    def __init__(self, modelo: str = 'whisper-1'):
        self.modelo = modelo

    def texto(self, arquivo, idioma: str = 'pt', dica: str = '') -> str:
        with open(arquivo, 'rb') as audio:
            r = OpenAI(timeout=25).audio.transcriptions.create(model=self.modelo, file=audio, language=idioma,
                                                               prompt=dica[:200] or None)
        return (r.text or '').strip()


class DitadoSimulado:
    """Dev e testes: não chama a OpenAI."""

    FRASES = {'pt': 'A gente se conheceu numa festa junina e dançamos a quadrilha juntos.',
              'es': 'Nos conocimos en una kermés y bailamos toda la noche.'}

    def texto(self, arquivo, idioma: str = 'pt', dica: str = '') -> str:
        return self.FRASES.get(idioma, self.FRASES['pt'])
