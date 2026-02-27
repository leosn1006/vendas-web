from flask import Flask, request, jsonify, render_template
from whatsapp_seguranca import whatsapp_security, validar_assinatura_whatsapp
from lide_incluir import persistir_lide
from notificacoes import notificador, notificar_erro
from error_handlers import registrar_error_handlers
from celery_app import celery_app
from logging_setup import setup_rotating_file_logging
import logging

setup_rotating_file_logging("app")

logger = logging.getLogger(__name__)

# Configurar Flask para procurar static na raiz do projeto
app = Flask(__name__,
            static_folder='../static',
            static_url_path='/static')

# Configurar JSON para não escapar caracteres Unicode (permite acentuação)
app.config['JSON_AS_ASCII'] = False

# Registrar error handlers centralizados
registrar_error_handlers(app)

# ============ ROTAS DA APLICAÇÃO ============

# Rota para evitar erro 404 do favicon
@app.get("/favicon.ico")
def favicon():
    """Retorna 204 No Content para evitar erro 404 nos logs."""
    return '', 204

# Rota de health check para Docker
@app.get("/health")
def health():
    """Endpoint de health check para verificar se a aplicação está rodando."""
    return jsonify({'status': 'healthy', 'service': 'vendas-web'}), 200

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
@validar_assinatura_whatsapp()
@notificar_erro()
def webhook_receive():
    logger.info("=" * 80)
    logger.info(f"[WEBHOOK] Requisição recebida de: {request.remote_addr}")
    logger.info(f"[WEBHOOK] Content-Type: {request.content_type}")
    logger.info(f"[WEBHOOK] X-Hub-Signature-256: {request.headers.get('X-Hub-Signature-256', 'AUSENTE')}")

    try:
        body = request.get_json(force=True, silent=True)

        if body is None:
            logger.error("[WAP-WEBHOOK] ❌ JSON inválido ou ausente")
            return jsonify({'error': 'Bad Request', 'message': 'JSON inválido ou ausente'}), 400

        logger.info(f"[WAP-WEBHOOK] 📦 Dados recebidos: {body}")

        # Joga na fila e responde 200 imediatamente
        celery_app.send_task("tasks.processar_webhook", args=[body])

        logger.info("[WAP-WEBHOOK] ✅ Mensagem enfileirada!")
        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.critical(f"[WAP-WEBHOOK] ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
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

@app.get("/paes-sem-gluten")
def paes_sem_gluten():
    return render_template('paes-sem-gluten.html')

@app.post("/api/v1/webhook/gravar-lide")
def gravar_lide():
    try:
        # Obtém o JSON do corpo da requisição
        body = request.get_json(force=True, silent=True)
        resposta = persistir_lide(body)
        logger.info(f"[LIDE] ✅ Processado com sucesso!")
        return resposta
    except Exception as e:
        logger.critical(f"[LIDE] ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Erro ao processar webhook'}), 400
