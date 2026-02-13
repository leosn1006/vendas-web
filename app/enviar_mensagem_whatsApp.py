import requests
import json
import os
from config import WHATSAPP_API_URL

def enviar_mensagem_texto(msg_original_json, mensagem_resposta):
    """
    Envia uma mensagem de texto para o WhatsApp usando a API.
    msg_original_json: O JSON original recebido do webhook do WhatsApp.
    mensagem_resposta: O texto da mensagem que queremos enviar como resposta.
    """
    print("=" * 80)
    print("[MENSAGEM] 📥 JSON RECEBIDO DO WHATSAPP (REQUEST):")
    print(json.dumps(msg_original_json, indent=2, ensure_ascii=False))
    print("=" * 80)

    phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '927793497092010')
    url = f"{WHATSAPP_API_URL}{phone_number_id}/messages"
    token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')
    headers = {
        "Authorization": f"Bearer {token[:20]}***",  # Mascarado no log
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    # Headers reais (com token completo, não logado)
    headers_reais = {
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

        print(f"[MENSAGEM] 📤 Enviando para: {numero_remetente}")
        print(f"[MENSAGEM] 🔗 URL da API: {url}")
        print(f"[MENSAGEM] 📝 PAYLOAD (JSON que será enviado):")
        print(json.dumps(dados, indent=2, ensure_ascii=False))
        print("=" * 80)

        # Executar chamada POST para enviar a mensagem
        response = requests.post(url, headers=headers_reais, json=dados)

        print(f"[MENSAGEM] 📊 STATUS CODE: {response.status_code}")
        print(f"[MENSAGEM] 📥 RESPONSE (JSON recebido da API):")
        try:
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        except:
            print(response.text)
        print("=" * 80)

        response.raise_for_status()
        print("[MENSAGEM] ✅ Mensagem enviada com sucesso!")

    except requests.exceptions.HTTPError as e:
        print(f"[MENSAGEM] ❌ Erro HTTP: {e}")
        print(f"[MENSAGEM] Response: {response.text}")
        print("=" * 80)
        raise e
    except Exception as e:
        print(f"[MENSAGEM] ❌ Erro ao enviar mensagem: {e}")
        print("=" * 80)
        raise e
