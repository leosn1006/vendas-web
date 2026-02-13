from enviar_mensagem_whatsApp import enviar_mensagem_texto

def recebe_webhook(mensagem_whatsapp):
    try:
        # Lógica para processar o webhook do WhatsApp
        enviar_mensagem_texto(mensagem_whatsapp, "Obrigado por sua mensagem! Estamos analisando e responderemos em breve.")
        return "Webhook recebido com sucesso!"
    except Exception as e:
        raise e
