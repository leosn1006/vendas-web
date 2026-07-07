from flask import Flask, request, jsonify, render_template, send_file, make_response
from whatsapp_seguranca import whatsapp_security, validar_assinatura_whatsapp
from lead_incluir import persistir_lead
from notificacoes import notificador, notificar_erro
from error_handlers import registrar_error_handlers
from celery_app import celery_app
from logging_setup import setup_rotating_file_logging
from flask_login import LoginManager
from admin import admin_bp
from admin.auth import init_login_manager
from web import web_bp
from database import busca_produtos_disponiveis_web
import os
import logging

setup_rotating_file_logging("app")

logger = logging.getLogger(__name__)

# Configurar Flask para procurar static na raiz do projeto
app = Flask(__name__,
            static_folder='../static',
            static_url_path='/static')

# Configurar JSON para não escapar caracteres Unicode (permite acentuação)
app.config['JSON_AS_ASCII'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'troque-em-producao')

# Registrar error handlers centralizados
registrar_error_handlers(app)

# Registra o Blueprint do admin
app.register_blueprint(admin_bp)
init_login_manager(app)

# Registra o Blueprint de web checkout
app.register_blueprint(web_bp)

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
    logger.info(f"[WEBHOOK] URL completa: {request.url}")
    logger.info(f"[WEBHOOK] Content-Type: {request.content_type}")
    logger.info(f"[WEBHOOK] X-Hub-Signature-256: {request.headers.get('X-Hub-Signature-256', 'AUSENTE')}")
    logger.info(f"[WEBHOOK] Headers: {dict(request.headers)}")

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

def _is_lssolucoes():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'lssolucoesdigitais.com.br' in host

def _is_lsdigitalsolucoes():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'lsdigitalsolucoes.com.br' in host

def _is_lsfb():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'lsfb-livros.com.br' in host

def _is_rc_livros():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'rc-livros.com.br' in host

def _is_lc_livros():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'lclivros.com.br' in host

def _is_ju_livros():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'ju-livros.com.br' in host

def _is_lsreceitas():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'lsreceitas.com.br' in host

@app.get("/")
def index():
    produtos = busca_produtos_disponiveis_web()
    if _is_lssolucoes():
        tmpl = 'portifolio-lssolucoes.html'
    elif _is_lsdigitalsolucoes():
        tmpl = 'portifolio-lssolucoes.html'
    elif _is_lsfb():
        tmpl = 'portifolio-lsfb.html'
    elif _is_rc_livros():
        tmpl = 'portifolio-rc.html'
    elif _is_lc_livros():
        tmpl = 'portifolio-lc.html'
    elif _is_ju_livros():
        tmpl = 'portifolio-ju.html'
    elif _is_lsreceitas():
        tmpl = 'portifolio-lsreceitas.html'
    else:
        tmpl = 'portifolio.html'
    return render_template(tmpl, produtos=produtos)

@app.get("/portifolio")
def portifolio():
    produtos = busca_produtos_disponiveis_web()
    if _is_lssolucoes():
        tmpl = 'portifolio-lssolucoes.html'
    elif _is_lsdigitalsolucoes():
        tmpl = 'portifolio-lssolucoes.html'
    elif _is_lsfb():
        tmpl = 'portifolio-lsfb.html'
    elif _is_rc_livros():
        tmpl = 'portifolio-rc.html'
    elif _is_lc_livros():
        tmpl = 'portifolio-lc.html'
    elif _is_ju_livros():
        tmpl = 'portifolio-ju.html'
    elif _is_lsreceitas():
        tmpl = 'portifolio-lsreceitas.html'
    else:
        tmpl = 'portifolio.html'
    return render_template(tmpl, produtos=produtos)

@app.get("/politica-privacidade")
def politica_privacidade():
    if _is_lssolucoes():
        tmpl = 'politica-privacidade-lssolucoes.html'
    elif _is_lsdigitalsolucoes():
        tmpl = 'politica-privacidade-lssolucoes.html'
    elif _is_lsfb():
        tmpl = 'politica-privacidade-lsfb.html'
    elif _is_rc_livros():
        tmpl = 'politica-privacidade-rc.html'
    elif _is_lc_livros():
        tmpl = 'politica-privacidade-lc.html'
    elif _is_ju_livros():
        tmpl = 'politica-privacidade-ju.html'
    elif _is_lsreceitas():
        tmpl = 'politica-privacidade-lsreceitas.html'
    else:
        tmpl = 'politica-privacidade.html'
    return render_template(tmpl)

@app.get("/termos-de-uso")
def termos_de_uso():
    if _is_lssolucoes():
        tmpl = 'termos-de-uso-lssolucoes.html'
    elif _is_lsdigitalsolucoes():
        tmpl = 'termos-de-uso-lssolucoes.html'
    elif _is_lsfb():
        tmpl = 'termos-de-uso-lsfb.html'
    elif _is_rc_livros():
        tmpl = 'termos-de-uso-rc.html'
    elif _is_lc_livros():
        tmpl = 'termos-de-uso-lc.html'
    elif _is_ju_livros():
        tmpl = 'termos-de-uso-ju.html'
    elif _is_lsreceitas():
        tmpl = 'termos-de-uso-lsreceitas.html'
    else:
        tmpl = 'termos-de-uso.html'
    return render_template(tmpl)

@app.get("/contato")
def contato():
    if _is_lssolucoes():
        tmpl = 'contato-lssolucoes.html'
    elif _is_lsdigitalsolucoes():
        tmpl = 'contato-lssolucoes.html'
    elif _is_lsfb():
        tmpl = 'contato-lsfb.html'
    elif _is_rc_livros():
        tmpl = 'contato-rc.html'
    elif _is_lc_livros():
        tmpl = 'contato-lc.html'
    elif _is_ju_livros():
        tmpl = 'contato-ju.html'
    elif _is_lsreceitas():
        tmpl = 'contato-lsreceitas.html'
    else:
        tmpl = 'contato.html'
    return render_template(tmpl)

@app.get("/lanche")
def lanche():
    return render_template('lanche.html')

@app.get("/paes-sem-gluten")
def paes_sem_gluten():
    return render_template('paes-sem-gluten-3.html')

@app.get("/paes-sem-gluten-temp")
def paes_sem_gluten_temp():
    return render_template('paes-sem-gluten-2-temp.html')

@app.get("/pascoa-lucrativa")
def pascoa_lucrativa():
    return render_template('pascoa-lucrativa.html')

@app.get("/pudim")
def pudim():
    return render_template('pudim.html')

@app.get("/pudim-temp")
def pudim_temp():
    return render_template('pudim-temp.html')

@app.get("/pudim-e")
def pudim_e():
    from web.checkout import rastrear_visita_funil, COOKIE_MAX_AGE_FUNIL
    produto_id = 8
    pedido_id = rastrear_visita_funil(request, produto_id, estado_novo=1004)
    resp = make_response(render_template('pudim-e.html'))
    resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp

@app.get("/pudim-e2")
def pudim_e2():
    from web.checkout import rastrear_visita_funil, COOKIE_MAX_AGE_FUNIL
    produto_id = 8
    pedido_id = rastrear_visita_funil(request, produto_id, estado_novo=1004)
    resp = make_response(render_template('pudim-e2.html'))
    resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp

@app.get("/pudim-e3")
def pudim_e3():
    from web.checkout import rastrear_visita_funil, COOKIE_MAX_AGE_FUNIL
    produto_id = 8
    pedido_id = rastrear_visita_funil(request, produto_id, estado_novo=1004)
    resp = make_response(render_template('pudim-e3.html'))
    resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp

@app.get("/tempero")
def tempero():
    return render_template('tempero.html')

@app.get("/fatia")
def fatia():
    return render_template('fatia.html')

@app.get("/sobremesas")
def sobremesas():
    return render_template('sobremesa.html')

@app.get("/sem-acucar")
def sem_acucar():
    return render_template('sem-acucar.html')

@app.get("/viver-bem")
def dicas_quimio():
    return render_template('dicas-quimio.html')

@app.get("/bem-estar")
def bem_estar():
    return render_template('bem-estar2.html')


@app.post("/api/v1/webhook/gravar-lide")
def gravar_lide():
    try:
        # Obtém o JSON do corpo da requisição
        body = request.get_json(force=True, silent=True)
        resposta = persistir_lead(body)
        logger.info(f"[LEAD] ✅ Processado com sucesso!")
        return resposta
    except Exception as e:
        logger.critical(f"[LIDE] ❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Erro ao processar webhook'}), 400
