from flask import Flask, send_file, request, jsonify, render_template
from webhook_whatsApp import recebe_webhook
from seguranca import whatsapp_security
import os

# Configurar Flask para procurar static na raiz do projeto
app = Flask(__name__,
            static_folder='../static',
            static_url_path='/static')

# Rota GET para verificação inicial do webhook (WhatsApp envia challenge)
@app.get("/api/v1/webhook-whatsapp")
def webhook_verify():
    print("Verificando webhook do WhatsApp...")
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
    print("=" * 80)
    print(f"[WEBHOOK] Requisição recebida de: {request.remote_addr}")
    print(f"[WEBHOOK] Content-Type: {request.content_type}")
    print(f"[WEBHOOK] X-Hub-Signature-256: {request.headers.get('X-Hub-Signature-256', 'AUSENTE')}")
    """
    Endpoint para receber notificações de mensagens do WhatsApp Business API.
    Valida a assinatura HMAC-SHA256 antes de processar.
    """
    # Valida a assinatura do WhatsApp usando a classe de segurança
    if not whatsapp_security.validate_signature():
        print('[WEBHOOK] ❌ Assinatura INVÁLIDA!')
        print(f"[WEBHOOK] App Secret usado: {whatsapp_security.app_secret[:10]}***")
        return jsonify({'error': 'Unauthorized', 'message': 'Assinatura inválida'}), 401

    print("[WEBHOOK] ✅ Assinatura VÁLIDA!")

    try:
        # Obtém o JSON do corpo da requisição
        body = request.get_json(force=True, silent=True)

        if body is None:
            print("[WEBHOOK] ❌ JSON inválido ou ausente")
            print(f"[WEBHOOK] Raw data: {request.get_data()[:200]}")
            return jsonify({'error': 'Bad Request', 'message': 'JSON inválido ou ausente'}), 400

        print(f"[WEBHOOK] 📦 Dados recebidos: {body}")
        resposta = recebe_webhook(body)
        print(f"[WEBHOOK] ✅ Processado com sucesso!")
        print("=" * 80)
        return resposta, 200
    except Exception as e:
        print(f"[WEBHOOK] ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80)
        return jsonify({'error': 'Erro ao processar webhook', 'details': str(e)}), 400

@app.get("/")
def index():
    return render_template('portifolio.html')

@app.get("/portifolio")
def portifolio():
    return render_template('portifolio.html')

@app.get("/politica-privacidade")
def politica_privacidade():
    return render_template('politica-privacidade.html')

@app.get("/termos-de-uso")
def termos_de_uso():
    return render_template('termos-de-uso.html')

@app.get("/contato")
def contato():
    return render_template('contato.html')

@app.get("/lanche")
def lanche():
    return render_template('lanche.html')
