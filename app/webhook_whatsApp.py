from enviar_mensagem_whatsApp import enviar_mensagem_texto

def recebe_webhook(mensagem_whatsapp):
    print("Webhook recebido:", mensagem_whatsapp)
    try:
        # Lógica para processar o webhook do WhatsApp
        enviar_mensagem_texto(mensagem_whatsapp, "Obrigado por sua mensagem! Estamos analisando e responderemos em breve.")
        print("Webhook recebido:", mensagem_whatsapp)
        return "Webhook recebido com sucesso!"
    except Exception as e:
        print(f"Erro ao processar webhook: {e}")
        # lanca uma exceção para ser capturada no app.py
        raise e
