from openai import OpenAI
from pathlib import Path

def transcrever_audio(path_audio: str) -> str:
    # Converte caminho relativo para absoluto (o path vem como "storage/audios/...")
    if not Path(path_audio).is_absolute():
        base_path = Path(__file__).parent.absolute()  # /app
        path_audio = str(base_path / path_audio)

    client = OpenAI()
    with open(path_audio, 'rb') as f:
        transcricao = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=f,
            language="pt"
        )
    return transcricao.text
