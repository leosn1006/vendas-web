from enviar_mensagem_whatsApp import enviar_mensagem_texto

def recebe_webhook(mensagem_whatsapp):
    # Lógica para processar o webhook do WhatsApp
    enviar_mensagem_texto(mensagem_whatsapp, "Obrigado por sua mensagem! Estamos analisando e responderemos em breve.")
    print("Webhook recebido:", mensagem_whatsapp)
    return "Webhook recebido com sucesso!"
