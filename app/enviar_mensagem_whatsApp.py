import requests
import json
import os
from constante import WHATSAPP_API_URL

def enviar_mensagem_texto(msg_original_json, mensagem_resposta):
    """
    Envia uma mensagem de texto para o WhatsApp usando a API.
    msg_original_json: O JSON original recebido do webhook do WhatsApp.
    mensagem_resposta: O texto da mensagem que queremos enviar como resposta.
    """
    phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '927793497092010')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    # Extrai o número do remetente e o ID da conversa do JSON original
    try:
        numero_remetente = msg_original_json['entry'][0]['changes'][0]['value']['messages'][0]['from']
        id_conversa = msg_original_json['entry'][0]['changes'][0]['value']['messages'][0]['id']

        dados = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero_remetente,
            "type": "text",
            "text": {
                "preview_url": "true",
                "body": mensagem_resposta
                }
            }
        print(f"[MENSAGEM] Enviando resposta para {numero_remetente} (ID da conversa: {id_conversa})")

        # executar uma chamada a API POST para enviar a mensagem
        response = requests.post(url, headers=headers, json=dados)
        response.raise_for_status()
        print("[MENSAGEM] Mensagem enviada com sucesso!")

    except Exception as e:
        print(f"[MENSAGEM] Erro ao enviar mensagem: {e}")
