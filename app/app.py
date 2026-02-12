from flask import Flask, send_file, request, jsonify
from webhook_whatsApp import recebe_webhook
from seguranca import whatsapp_security

app = Flask(__name__)

# Rota GET para verificação inicial do webhook (WhatsApp envia challenge)
@app.get("/api/v1/webhook-whatsapp")
def webhook_verify():
    """
    Endpoint de verificação do webhook do WhatsApp Business API.
    O WhatsApp envia: hub.mode, hub.verify_token, hub.challenge
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    # Verifica se o token corresponde ao configurado usando a classe de segurança
    if whatsapp_security.validate_webhook_verification(mode, token):
        print('Webhook verificado com sucesso!')
        return challenge, 200
    else:
        print('Falha na verificação do webhook')
        return jsonify({'error': 'Forbidden', 'message': 'Token de verificação inválido'}), 403

# Rota POST para receber mensagens do WhatsApp Business API
@app.post("/api/v1/webhook-whatsapp")
def webhook_receive():
    """
    Endpoint para receber notificações de mensagens do WhatsApp Business API.
    Valida a assinatura HMAC-SHA256 antes de processar.
    """
    # Valida a assinatura do WhatsApp usando a classe de segurança
    if not whatsapp_security.validate_signature():
        print('Assinatura inválida no webhook')
        return jsonify({'error': 'Unauthorized', 'message': 'Assinatura inválida'}), 401

    try:
        resposta = recebe_webhook(body=request.get_json())
        return resposta, 200
    except Exception as e:
        print(f"Erro ao processar webhook: {e}")
        return jsonify({'error': 'Erro ao processar webhook', 'details': str(e)}), 400

@app.get("/")
def index():
    return send_file('portifolio.html', mimetype='text/html')

@app.get("/portifolio")
def portifolio():
    return send_file('portifolio.html', mimetype='text/html')

@app.get("/lancheira.webp")
def lancheira_webp():
    return send_file('imagens/lancheira.webp', mimetype='image/webp')

@app.get("/politica-privacidade")
def politica_privacidade():
    return send_file('politica-privacidade.html', mimetype='text/html')

@app.get("/termos-de-uso")
def termos_de_uso():
    return send_file('termos-de-uso.html', mimetype='text/html')

@app.get("/contato")
def contato():
    return send_file('contato.html', mimetype='text/html')

@app.get("/lanche")
def lanche():
    return send_file('lanche.html', mimetype='text/html')
