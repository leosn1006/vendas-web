import requests
import os
import logging
from dotenv import load_dotenv
from config import WHATSAPP_API_URL

load_dotenv()

logger = logging.getLogger(__name__)

def ativa_whatsapp(numero, token: str = None) -> bool:
    """Ativa o WhatsApp para o número fornecido usando a API do WhatsApp."""
    token = token or os.getenv('WHATSAPP_ACCESS_TOKEN', '')
    url = f"{WHATSAPP_API_URL}{numero}/register"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "pin": "123456",
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        logger.info(f"WhatsApp ativado com sucesso ")
        return True
    except requests.Timeout:
        logger.error(f"Timeout ao ativar WhatsApp para o número {numero} (>30s)")
        print("Detalhe da API: timeout — verifique conectividade com graph.facebook.com")
        return False
    except requests.RequestException as e:
        body = e.response.text if e.response is not None else ''
        logger.error(f"Erro ao ativar WhatsApp para o número {numero}: {e} | resposta: {body}")
        print(f"Detalhe da API: {body}")
        return False


def enviar_mensagem_template(numero_destino: str, template_name: str, language_code: str = "pt_BR", phone_id: str = "1012710858592627") -> bool:
    """Envia uma mensagem de template WhatsApp para o número destino."""
    token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')
    url = f"{WHATSAPP_API_URL}{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero_destino,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code}
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Mensagem template '{template_name}' enviada para {numero_destino}")
        return True
    except requests.RequestException as e:
        body = e.response.text if e.response is not None else ''
        logger.error(f"Erro ao enviar mensagem para {numero_destino}: {e} | resposta: {body}")
        print(f"Detalhe da API: {body}")
        return False


if __name__ == '__main__':
    # Exemplo de uso
    # numero = "1012710858592627"
    # numero = '1026973267170405'
    # numero = '1010970915440720'
    # numero = 1062772840249831
    # numero = 1054425447760930
    # numero = 1121969160997310
    # numero = 107536289899882
    numero = 1073990592466886


# (61) 98402-2952
    sucesso = ativa_whatsapp(numero)
    if sucesso:
        print(f"WhatsApp ativado com sucesso")
    else:
        print(f"Falha ao ativar WhatsApp para o número {numero}")
    ## Enviar mensagem de template
    #template_enviado = enviar_mensagem_template(numero_destino="556181163324", template_name="hello_world")
    #if template_enviado:
    #    print(f"Mensagem de template enviada com sucesso para {numero}")
    #else:
    #    print(f"Falha ao enviar mensagem de template para {numero}")
