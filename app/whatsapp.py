import requests
import os
import logging
import pytz
from datetime import datetime
from config import WHATSAPP_API_URL
from database import Pedido, get_whatsapp_token

logger = logging.getLogger(__name__)



def marcar_como_lida(message_id: str, phone_number_id: str = None):

    phone_number_id = phone_number_id or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = get_whatsapp_token(phone_number_id)

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
    if pedido is None:
        raise ValueError("[AUDIO-ENVIAR] Não é possível enviar mensagem sem um pedido associado.")

    phone_number_id = pedido.get('phone_number_id') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = get_whatsapp_token(phone_number_id)

    headers_reais = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    numero_remetente = pedido.get("contact_phone")

    dados = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero_remetente,
        "type": "audio",
        "audio": {
            "link": url_audio,
            "voice": True
        }
    }

    logger.info(f"[AUDIO-ENVIAR] Enviando mensagem para {numero_remetente} com o seguinte payload:")
    logger.info(f"[AUDIO-ENVIAR] dados: {dados}")

    response = requests.post(url, headers=headers_reais, json=dados, timeout=30)

    if response.status_code == 200:
        id_message = response.json().get('messages', [{}])[0].get('id')
        logger.info(f"[AUDIO-ENVIAR] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
        return id_message

    raise ValueError(f"[AUDIO-ENVIAR] ❌ Erro ao enviar audio: status={response.status_code} body={response.text}")

def enviar_mensagem(pedido: Pedido, mensagem: str):
    if pedido is None:
        raise ValueError("[MENSAGEM-ENVIAR] Não é possível enviar mensagem sem um pedido associado.")

    phone_number_id = pedido.get('phone_number_id') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = get_whatsapp_token(phone_number_id)

    headers_reais = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    numero_remetente = pedido.get("contact_phone")

    dados = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero_remetente,
        "type": "text",
        "text": {
            "preview_url": True,
            "body": mensagem
        }
    }

    logger.info(f"[MENSAGEM-ENVIAR] Enviando mensagem para {numero_remetente} com o seguinte payload:")
    logger.info(f"[MENSAGEM-ENVIAR] dados: {dados}")

    response = requests.post(url, headers=headers_reais, json=dados, timeout=30)

    if response.status_code == 200:
        id_message = response.json().get('messages', [{}])[0].get('id')
        logger.info(f"[MENSAGEM-ENVIAR] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
        return id_message

    raise ValueError(f"[MENSAGEM-ENVIAR] ❌ Erro ao enviar mensagem: status={response.status_code} body={response.text}")

def enviar_mensagem_digitando(message_id: str, phone_number_id: str = None):
    if message_id is None:
        raise ValueError("[MENSAGEM-DIGITANDO] Não é possível enviar mensagem sem um ID de mensagem associado.")

    phone_number_id = phone_number_id or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = get_whatsapp_token(phone_number_id)

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
    logger.info(f"[MENSAGEM-DIGITANDO] dados: {dados}")

    response = requests.post(url, headers=headers_reais, json=dados, timeout=30)

    if response.status_code == 200:
        id_message = response.json().get('messages', [{}])[0].get('id')
        logger.info(f"[MENSAGEM-DIGITANDO] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
        return id_message

    raise ValueError(f"[MENSAGEM-DIGITANDO] ❌ Erro ao enviar digitando: status={response.status_code} body={response.text}")


def enviar_documento(pedido: Pedido, url_documento: str, caption: str, filename: str):
    if pedido is None:
        raise ValueError("[DOCUMENTO-ENVIAR] Não é possível enviar mensagem sem um pedido associado.")

    phone_number_id = pedido.get('phone_number_id') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = get_whatsapp_token(phone_number_id)

    headers_reais = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    numero_remetente = pedido.get("contact_phone")

    dados = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero_remetente,
        "type": "document",
        "document": {
            "link": url_documento,
            "filename": filename,
            "caption": caption
        }
    }

    logger.info(f"[DOCUMENTO-ENVIAR] Enviando mensagem para {numero_remetente} com o seguinte payload:")
    logger.info(f"[DOCUMENTO-ENVIAR] dados: {dados}")

    response = requests.post(url, headers=headers_reais, json=dados, timeout=30)

    if response.status_code == 200:
        id_message = response.json().get('messages', [{}])[0].get('id')
        logger.info(f"[DOCUMENTO-ENVIAR] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
        return id_message

    raise ValueError(f"[DOCUMENTO-ENVIAR] ❌ Erro ao enviar documento: status={response.status_code} body={response.text}")

def enviar_imagem(pedido: Pedido, url_imagem: str):
    if pedido is None:
        raise ValueError("[IMAGEM-ENVIAR] Não é possível enviar mensagem sem um pedido associado.")

    phone_number_id = pedido.get('phone_number_id') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = get_whatsapp_token(phone_number_id)

    headers_reais = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

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
    logger.info(f"[IMAGEM-ENVIAR] dados: {dados}")

    response = requests.post(url, headers=headers_reais, json=dados, timeout=30)

    if response.status_code == 200:
        id_message = response.json().get('messages', [{}])[0].get('id')
        logger.info(f"[IMAGEM-ENVIAR] Mensagem enviada com sucesso! ID da mensagem: {id_message}")
        return id_message

    raise ValueError(f"[IMAGEM-ENVIAR] ❌ Erro ao enviar imagem: status={response.status_code} body={response.text}")


def enviar_produto_whatsapp(pedido: dict, template_name: str, language: str,
                            doc_url: str, doc_filename: str, body_params: list) -> str:
    """
    Envia uma WhatsApp Template Message com documento no header e parâmetros de texto no body.
    Usado para iniciar conversas pelo sistema (ex: entrega de ebook após compra web),
    onde a API exige templates pré-aprovados pois não há janela de 24h ativa.
    """
    phone_number_id = pedido.get('phone_number_id') or os.getenv('WHATSAPP_PHONE_NUMBER_ID')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = get_whatsapp_token(phone_number_id)

    headers_reais = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    numero_remetente = pedido.get("contact_phone")

    dados = {
        "messaging_product": "whatsapp",
        "to": numero_remetente,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language or "pt_BR"},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {"type": "document", "document": {
                            "link": doc_url,
                            "filename": doc_filename
                        }}
                    ]
                },
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": p} for p in body_params
                    ]
                }
            ]
        }
    }

    logger.info(f"[TEMPLATE-ENVIAR] Enviando template '{template_name}' para {numero_remetente}")
    logger.info(f"[TEMPLATE-ENVIAR] dados: {dados}")

    response = requests.post(url, headers=headers_reais, json=dados, timeout=30)

    if response.status_code == 200:
        id_message = response.json().get('messages', [{}])[0].get('id')
        logger.info(f"[TEMPLATE-ENVIAR] Template enviado com sucesso! ID: {id_message}")
        return id_message

    raise ValueError(f"[TEMPLATE-ENVIAR] ❌ Erro ao enviar template: status={response.status_code} body={response.text}")


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


def notificar_admin_via_template(pedido: dict, nome_produto: str, mensagem: str):
    """
    Envia notificação ao admin usando o template 'administrativa_resposta'.
    Usa phone_number_id fixo (974838442380155) onde o template está aprovado,
    independente do produto. Obrigatório para mensagens fora da janela de 24h.
    Parâmetros do template: {{1}} pedido, {{2}} nome_produto, {{3}} mensagem.
    """
    admin_phone = os.getenv('ADMIN_WHATSAPP_NUMBER', '').replace('+', '')
    if not admin_phone:
        logger.warning("[NOTIF-ADMIN-TEMPLATE] ADMIN_WHATSAPP_NUMBER não configurado — ignorado")
        return

    ADMIN_PHONE_NUMBER_ID = '974838442380155'
    url = f"{WHATSAPP_API_URL}{ADMIN_PHONE_NUMBER_ID}/messages"
    token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')
    pedido_num = f"#{pedido.get('id', '?')}"

    dados = {
        "messaging_product": "whatsapp",
        "to": admin_phone,
        "type": "template",
        "template": {
            "name": "administrativa_resposta",
            "language": {"code": "pt_BR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": pedido_num},
                        {"type": "text", "text": nome_produto or "Desconhecido"},
                        {"type": "text", "text": mensagem[:1024]},
                    ]
                }
            ]
        }
    }

    try:
        response = requests.post(url, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }, json=dados, timeout=10)
        if response.status_code == 200:
            logger.info(f"[NOTIF-ADMIN-TEMPLATE] ✅ Enviado para {admin_phone} — pedido {pedido_num}")
        else:
            logger.error(f"[NOTIF-ADMIN-TEMPLATE] ❌ Erro {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"[NOTIF-ADMIN-TEMPLATE] ❌ Exceção: {e}")


def notificar_admin_erro_sistema(descricao: str, log: str = "log_worker"):
    """
    Notifica o admin via template 'administrativa_erro_sistema' quando um worker falha.
    Parâmetros do template: {{1}} momento (horário SP), {{2}} descrição breve.
    """
    return  # temporariamente desabilitado — rate limit
    admin_phone = os.getenv('ADMIN_WHATSAPP_NUMBER', '').replace('+', '')
    if not admin_phone:
        logger.warning("[NOTIF-ADMIN-ERRO-SISTEMA] ADMIN_WHATSAPP_NUMBER não configurado — ignorado")
        return

    momento = datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%d/%m %H:%M')
    descricao = f"{descricao} | log: {log}"

    ADMIN_PHONE_NUMBER_ID = '974838442380155'
    url = f"{WHATSAPP_API_URL}{ADMIN_PHONE_NUMBER_ID}/messages"
    token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')

    dados = {
        "messaging_product": "whatsapp",
        "to": admin_phone,
        "type": "template",
        "template": {
            "name": "administrativa_erro_sistema",
            "language": {"code": "pt_BR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": momento},
                        {"type": "text", "text": descricao[:512]},
                    ]
                }
            ]
        }
    }

    try:
        response = requests.post(url, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }, json=dados, timeout=10)
        if response.status_code == 200:
            logger.info(f"[NOTIF-ADMIN-ERRO-SISTEMA] ✅ Enviado para {admin_phone} — {descricao[:80]}")
        else:
            logger.error(f"[NOTIF-ADMIN-ERRO-SISTEMA] ❌ Erro {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"[NOTIF-ADMIN-ERRO-SISTEMA] ❌ Exceção: {e}")
