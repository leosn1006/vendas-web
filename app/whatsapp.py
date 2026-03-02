import requests
import os
import logging
from config import WHATSAPP_API_URL
from database import Pedido

logger = logging.getLogger(__name__)

def enviar_introducao(pedido, url_audio=None):
    if pedido is None:
        raise ValueError("[INTRODUÇÃO] Não é possível enviar mensagem sem um pedido associado.")
    try:
        url_audio="https://lneditor.com.br/static/audios/introducao-paes.ogg" #default
        if pedido.get("produto_id") == 1:
            url_audio="https://lneditor.com.br/static/audios/introducao-paes.ogg"
            # url_audio= "https://s3.projetosdobruno.com/audios/Audios%20Luiza/Luiza2.ogg"


        enviar_audio(pedido, url_audio=url_audio)

    except Exception as e:
        raise e

def marcar_como_lida(message_id: str, phone_number_id: str = None):

    phone_number_id = phone_number_id or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    dados = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id  # wamid.xxx que vem no webhook
    }

    response = requests.post(url, headers=headers, json=dados)
    response.raise_for_status()
    return response.json()

def enviar_audio(pedido: Pedido, url_audio: str):
    id_message = None

    if pedido is None:
        raise ValueError("[AUDIO-ENVIAR] Não é possível enviar mensagem sem um pedido associado.")

    try:
        # Envia uma mensagem de audio para o WhatsApp usando a API.
        phone_number_id = pedido.get('phone_number_id') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
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
             "link": url_audio,
             "voice": "true"
            }
        }

        logger.info(f"[AUDIO-ENVIAR] Enviando mensagem para {numero_remetente} com o seguinte payload:")
        # logger.info(f"[AUDIO-ENVIAR] headers: {headers_reais}")
        logger.info(f"[AUDIO-ENVIAR] dados: {dados}")

        # Executar chamada POST para enviar a mensagem
        response = requests.post(url, headers=headers_reais, json=dados)

        if response.status_code == 200:
            id_message = response.json().get('messages', [{}])[0].get('id')
            logger.info(f"[AUDIO-ENVIAR] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
            return id_message

        response.raise_for_status()

    except Exception as e:
        raise ValueError(f"[AUDIO-ENVIAR] ❌ Erro ao enviar audio: {response.json()}")

def enviar_mensagem(pedido: Pedido, mensagem: str):
    id_message = None

    if pedido is None:
        raise ValueError("[MENSAGEM-ENVIAR] Não é possível enviar mensagem sem um pedido associado.")

    try:
        # Envia uma mensagem de audio para o WhatsApp usando a API.
        phone_number_id = pedido.get('phone_number_id') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
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
            "type": "text",
            "text": {
                "preview_url": "true",
                "body": mensagem
            }
        }

        logger.info(f"[MENSAGEM-ENVIAR] Enviando mensagem para {numero_remetente} com o seguinte payload:")
        # logger.info(f"[MENSAGEM-ENVIAR] headers: {headers_reais}")
        logger.info(f"[MENSAGEM-ENVIAR] dados: {dados}")

        # Executar chamada POST para enviar a mensagem
        response = requests.post(url, headers=headers_reais, json=dados)

        if response.status_code == 200:
            id_message = response.json().get('messages', [{}])[0].get('id')
            logger.info(f"[MENSAGEM-ENVIAR] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
            return id_message

        response.raise_for_status()

    except Exception as e:
        raise ValueError(f"[MENSAGEM-ENVIAR] ❌ Erro ao enviar mensagem: {response.json()}")

def enviar_mensagem_digitando(message_id: str, phone_number_id: str = None):
    id_message = None

    if message_id is None:
        raise ValueError("[MENSAGEM-DIGITANDO] Não é possível enviar mensagem sem um ID de mensagem associado.")

    try:
        # Envia uma mensagem de audio para o WhatsApp usando a API.
        phone_number_id = phone_number_id or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
        token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')

        # Headers reais (com token completo, não logado)
        headers_reais = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json"
        }

        dados = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {
            "type": "text"
          }
        }

        logger.info(f"[MENSAGEM-DIGITANDO] Enviando status de digitando para a mensagem ID {message_id} com o seguinte payload:")
        # logger.info(f"[MENSAGEM-ENVIAR] headers: {headers_reais}")
        logger.info(f"[MENSAGEM-DIGITANDO] dados: {dados}")

        # Executar chamada POST para enviar a mensagem
        response = requests.post(url, headers=headers_reais, json=dados)

        if response.status_code == 200:
            id_message = response.json().get('messages', [{}])[0].get('id')
            logger.info(f"[MENSAGEM-DIGITANDO] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
            return id_message

        response.raise_for_status()

    except Exception as e:
        raise ValueError(f"[MENSAGEM-ENVIAR] ❌ Erro ao enviar mensagem: {response.json()}")


def enviar_documento(pedido: Pedido, url_documento: str, caption: str, filename: str):
    id_message = None

    if pedido is None:
        raise ValueError("[DOCUMENTO-ENVIAR] Não é possível enviar mensagem sem um pedido associado.")

    try:
        # Envia uma mensagem de documento para o WhatsApp usando a API.
        phone_number_id = pedido.get('phone_number_id') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
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
            "type": "document",
            "document": {
                "link": url_documento,
                "filename": filename,  # nome que aparece para o cliente
                "caption": caption
              }
            }

        logger.info(f"[DOCUMENTO-ENVIAR] Enviando mensagem para {numero_remetente} com o seguinte payload:")
        # logger.info(f"[DOCUMENTO-ENVIAR] headers: {headers_reais}")
        logger.info(f"[DOCUMENTO-ENVIAR] dados: {dados}")

        # Executar chamada POST para enviar a mensagem
        response = requests.post(url, headers=headers_reais, json=dados)

        if response.status_code == 200:
            id_message = response.json().get('messages', [{}])[0].get('id')
            logger.info(f"[DOCUMENTO-ENVIAR] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
            return id_message

        response.raise_for_status()

    except Exception as e:
        raise ValueError(f"[DOCUMENTO-ENVIAR] ❌ Erro ao enviar documento: {response.json()}")

def enviar_imagem(pedido: Pedido, url_imagem: str):
    logger.info(f"[IMAGEM-ENVIAR] Iniciando envio de imagem para o cliente. Pedido ID: {pedido.get('id')}, URL da imagem: {url_imagem}")
    id_message = None

    if pedido is None:
        raise ValueError("[IMAGEM-ENVIAR] Não é possível enviar mensagem sem um pedido associado.")

    try:
        # Envia uma mensagem de imagem para o WhatsApp usando a API.
        phone_number_id = pedido.get('phone_number_id') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
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
            "type": "image",
            "image": {
                "link": url_imagem
              }
            }

        logger.info(f"[IMAGEM-ENVIAR] Enviando mensagem para {numero_remetente} com o seguinte payload:")
        # logger.info(f"[IMAGEM-ENVIAR] headers: {headers_reais}")
        logger.info(f"[IMAGEM-ENVIAR] dados: {dados}")

        # Executar chamada POST para enviar a mensagem
        response = requests.post(url, headers=headers_reais, json=dados)

        if response.status_code == 200:
            id_message = response.json().get('messages', [{}])[0].get('id')
            logger.info(f"[IMAGEM-ENVIAR] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
            return id_message

        response.raise_for_status()

    except Exception as e:
        raise ValueError(f"[IMAGEM-ENVIAR] ❌ Erro ao enviar imagem: {response.json()}")


def notificar_admin_pedido(pedido: dict, mensagem: str):
    """Envia notificação ao admin pelo mesmo número WhatsApp do produto (phone_number_id do pedido)."""
    admin_phone = os.getenv('ADMIN_WHATSAPP_NUMBER', '').replace('+', '')
    if not admin_phone:
        logger.warning("[NOTIF-ADMIN] ADMIN_WHATSAPP_NUMBER não configurado — notificação ignorada")
        return
    pedido_admin = {
        'phone_number_id': pedido.get('phone_number_id'),
        'contact_phone': admin_phone,
    }
    try:
        enviar_mensagem(pedido_admin, mensagem)
        logger.info(f"[NOTIF-ADMIN] ✅ Notificação enviada para {admin_phone}")
    except Exception as e:
        logger.error(f"[NOTIF-ADMIN] ❌ Falha ao notificar admin: {e}")
