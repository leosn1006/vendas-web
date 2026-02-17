import requests
import os
import logging
from config import WHATSAPP_API_URL
from database import Pedido

logger = logging.getLogger(__name__)

def enviar_introducao(pedido):
    if pedido is None:
        raise ValueError("[INTRODUÇÃO] Não é possível enviar mensagem sem um pedido associado.")
    try:
        url_audio="https://lneditor.com.br/arq/audio-introducao.mp3" #default
        if pedido.get("produto_id") == 1:
            url_audio="https://lneditor.com.br/arq/audio-introducao.mp3"

        enviar_audio(pedido, url_audio=url_audio)

    except Exception as e:
        raise e

def enviar_audio(pedido: Pedido, url_audio: str):

    if pedido is None:
        raise ValueError("[AUDIO] Não é possível enviar mensagem sem um pedido associado.")

    try:
        # Envia uma mensagem de audio para o WhatsApp usando a API.
        phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '927793497092010')
        url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
        token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')

        # Headers reais (com token completo, não logado)
        headers_reais = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json"
        }

        # Extrai o número do remetente e o ID da conversa do JSON original
        numero_remetente = pedido.get("contact_phone")

        dados = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero_remetente,
            "type": "audio",
            "audio": {
             "link": "https://lneditor.com.br/static/audios/paes-introducao.mp4"
            }
        }

        print(f"[AUDIO] Enviando mensagem para {numero_remetente} com o seguinte payload:")
        print(headers_reais)
        print(dados)

        # Executar chamada POST para enviar a mensagem
        response = requests.post(url, headers=headers_reais, json=dados)

        response.raise_for_status()
        logger.info("[AUDIO] ✅ Mensagem enviada com sucesso!")

    except Exception as e:
        raise ValueError(f"[AUDIO] ❌ Erro ao enviar audio: {response.text}")
