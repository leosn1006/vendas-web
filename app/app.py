from flask import Flask, send_file, request, jsonify, render_template
from whatsapp_webhook import recebe_webhook
from seguranca import whatsapp_security, validar_assinatura_whatsapp
from lide_incluir import persistir_lide
from notificacoes import notificador, notificar_erro
import os
import logging

logger = logging.getLogger(__name__)

# Configurar Flask para procurar static na raiz do projeto
app = Flask(__name__,
            static_folder='../static',
            static_url_path='/static')

# Configurar JSON para não escapar caracteres Unicode (permite acentuação)
app.config['JSON_AS_ASCII'] = False


# ============ HANDLER GLOBAL DE ERROS ============
@app.errorhandler(Exception)
def handle_exception(e):
    """
    Captura TODOS os erros não tratados da aplicação.
    Envia notificação simples para o WhatsApp do admin (exceto 404 de bots).
    """
    # Coleta contexto mínimo
    contexto = {}
    try:
        if request and request.endpoint:
            contexto['Endpoint'] = request.endpoint
    except:
        pass

    # Notifica o erro (mensagem será simples)
    notificador.notificar_erro(e, contexto_adicional=contexto)

    # Loga detalhes completos no servidor
    print(f"[ERRO GLOBAL] {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

    # Retorna resposta apropriada
    return jsonify({
        'error': 'Erro interno do servidor',
        'message': 'Um erro ocorreu e nossa equipe foi notificada'
    }), 500


@app.errorhandler(404)
def handle_404(e):
    """
    Tratamento especial para 404 - NÃO notifica via WhatsApp.
    Evita spam de bots fazendo scan de vulnerabilidades.
    """
    caminho = request.path
    user_agent = request.headers.get('User-Agent', '')

    # Log apenas para análise (não notifica)
    print(f"[404] {caminho} | UA: {user_agent[:50]}")

    # Lista expandida de padrões suspeitos de bots/scanners
    padroes_suspeitos = [
        # WordPress
        'wp-', 'wordpress', 'xmlrpc', 'wlwmanifest',
        # Ferramentas admin/debug
        'phpmyadmin', 'adminer', 'debug', 'phpinfo', 'console', 'panel',
        # Arquivos sensíveis
        'config.', 'aws-config', 'aws.', 'credentials', '.env', '.git', '.sql',
        # PHP files
        '.php', '.phtml',
        # Outros scanners
        'jasperserver', 'helpdesk', 'aspera', 'cf_scripts', 'WebObjects'
    ]

    # Se for rota suspeita, retorna resposta mínima (sem gastar recursos)
    if any(padrao in caminho.lower() for padrao in padroes_suspeitos):
        return '', 404

    # Para 404 legítimos (usuário digitou URL errada), retorna JSON amigável
    return jsonify({
        'error': 'Página não encontrada',
        'message': f'A rota {caminho} não existe'
    }), 404
# ==================================================


# Rotas comuns da aplicação

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
@validar_assinatura_whatsapp()  # Valida assinatura HMAC-SHA256
@notificar_erro()  # Notifica qualquer erro nesta rota crítica
def webhook_receive():
    logger.info("=" * 80)
    logger.info(f"[WEBHOOK] Requisição recebida de: {request.remote_addr}")
    logger.info(f"[WEBHOOK] Content-Type: {request.content_type}")
    logger.info(f"[WEBHOOK] X-Hub-Signature-256: {request.headers.get('X-Hub-Signature-256', 'AUSENTE')}")
    """
    Endpoint para receber notificações de mensagens do WhatsApp Business API.
    A assinatura é validada pelo decorador @validar_assinatura_whatsapp().
    """
    try:
        # Obtém o JSON do corpo da requisição
        body = request.get_json(force=True, silent=True)

        if body is None:
            logger.error("[WEBHOOK] ❌ JSON inválido ou ausente")
            logger.error(f"[WEBHOOK] Raw data: {request.get_data()[:200]}")
            return jsonify({'error': 'Bad Request', 'message': 'JSON inválido ou ausente'}), 400

        print(f"[WEBHOOK] 📦 Dados recebidos: {body}")
        resposta = recebe_webhook(body)
        logger.info(f"[WEBHOOK] ✅ Processado com sucesso!")

        return resposta, 200

    except Exception as e:
        logger.critical(f"[WEBHOOK] ❌ ERRO: {e}")
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
        print(f"[LIDE] 📦 Dados recebidos: {body}")
        resposta = persistir_lide(body)
        print(f"[LIDE] ✅ Processado com sucesso!")
        return resposta
    except Exception as e:
        logger.critical(f"[LIDE] ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Erro ao processar webhook'}), 400
