from openai import OpenAI

def transcrever_audio(path_audio: str) -> str:
    client = OpenAI()
    with open(path_audio, 'rb') as f:
        transcricao = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="pt"
        )
    return transcricao.text
