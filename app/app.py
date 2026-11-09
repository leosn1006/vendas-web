from flask import Flask, request, jsonify, render_template, send_file, make_response
from whatsapp_seguranca import whatsapp_security, validar_assinatura_whatsapp
from lead_incluir import persistir_lead
from notificacoes import notificador, notificar_erro
from error_handlers import registrar_error_handlers
from celery_app import celery_app
from whatsapp_eventos_conta import EVENTOS_CONTA_OU_TELEFONE, classificar_webhook
from logging_setup import setup_rotating_file_logging
from flask_login import LoginManager
from admin import admin_bp
from admin.auth import init_login_manager
from web import web_bp
from apps import registrar as apps_registrar
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

# Apps das clientes (PWA em /app/<slug>/, ex.: App Fatias) — ver docs/APPS.md
apps_registrar(app)

# Produto Música (/musica/...: quiz, prévia, compra, presente) — ver docs/MUSICA.md
from musica import registrar as musica_registrar
musica_registrar(app)


@app.template_filter('brl')
def formatar_brl(valor):
    """Formata número no padrão monetário brasileiro: R$ 99.999.999,99."""
    valor = float(valor or 0)
    texto = f'{valor:,.2f}'
    texto = texto.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {texto}'


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

        # Decide a(s) fila(s) pelos tipos de evento presentes no payload: mensagens seguem
        # urgente (fluxo de venda); eventos de conta/número (qualidade, revisão, banimento) vão
        # pra fila normal. Varre TODOS os entry/changes (não só o primeiro) — a Meta pode
        # entregar mais de um por POST, e um payload misto (mensagem + evento) precisa acionar
        # as duas filas, senão um dos dois é perdido silenciosamente.
        fields = classificar_webhook(body)
        tem_evento_conta = bool(fields & EVENTOS_CONTA_OU_TELEFONE)
        tem_outro_campo = (not fields) or bool(fields - EVENTOS_CONTA_OU_TELEFONE)

        if tem_evento_conta:
            celery_app.send_task("tasks.processar_evento_conta_whatsapp", args=[body])
            logger.info(f"[WAP-WEBHOOK] ✅ Evento(s) de conta/telefone enfileirado(s) (fila normal): {fields & EVENTOS_CONTA_OU_TELEFONE}")
        if tem_outro_campo:
            celery_app.send_task("tasks.processar_webhook", args=[body])
            logger.info("[WAP-WEBHOOK] ✅ Mensagem enfileirada (fila urgente)!")

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

def _is_lbe_livros():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'lbe-livros.site' in host or 'lbelivros.com.br' in host

def _is_lb_livros():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'lb-livros.site' in host or 'lblivros.com.br' in host

def _is_brep_livros():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'breplivros.site' in host

def _is_leituraemais():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'leituraemais.site' in host

def _is_livrinhos():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'livrinhosdigitais.site' in host

def _is_vitrini():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'vitrinidaju.site' in host

def _is_livrosemais():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'livrosemais.site' in host

def _is_stracklivros():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'stracklivros.com.br' in host

def _is_barreiroslivros():
    host = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return 'barreiroslivros.com.br' in host

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
    elif _is_lbe_livros():
        tmpl = 'portifolio-lbe.html'
    elif _is_lb_livros():
        tmpl = 'portifolio-lb.html'
    elif _is_brep_livros():
        tmpl = 'portifolio-brep.html'
    elif _is_leituraemais():
        tmpl = 'portifolio-leituraemais.html'
    elif _is_livrinhos():
        tmpl = 'portifolio-livrinhos.html'
    elif _is_vitrini():
        tmpl = 'portifolio-vitrini.html'
    elif _is_livrosemais():
        tmpl = 'portifolio-livrosemais.html'
    elif _is_stracklivros():
        tmpl = 'portifolio-stracklivros.html'
    elif _is_barreiroslivros():
        tmpl = 'portifolio-barreiroslivros.html'
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
    elif _is_lbe_livros():
        tmpl = 'portifolio-lbe.html'
    elif _is_lb_livros():
        tmpl = 'portifolio-lb.html'
    elif _is_brep_livros():
        tmpl = 'portifolio-brep.html'
    elif _is_leituraemais():
        tmpl = 'portifolio-leituraemais.html'
    elif _is_livrinhos():
        tmpl = 'portifolio-livrinhos.html'
    elif _is_vitrini():
        tmpl = 'portifolio-vitrini.html'
    elif _is_livrosemais():
        tmpl = 'portifolio-livrosemais.html'
    elif _is_stracklivros():
        tmpl = 'portifolio-stracklivros.html'
    elif _is_barreiroslivros():
        tmpl = 'portifolio-barreiroslivros.html'
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
    elif _is_lbe_livros():
        tmpl = 'politica-privacidade-lbe.html'
    elif _is_lb_livros():
        tmpl = 'politica-privacidade-lb.html'
    elif _is_brep_livros():
        tmpl = 'politica-privacidade-brep.html'
    elif _is_leituraemais():
        tmpl = 'politica-privacidade-leituraemais.html'
    elif _is_livrinhos():
        tmpl = 'politica-privacidade-livrinhos.html'
    elif _is_vitrini():
        tmpl = 'politica-privacidade-vitrini.html'
    elif _is_livrosemais():
        tmpl = 'politica-privacidade-livrosemais.html'
    elif _is_barreiroslivros():
        tmpl = 'politica-privacidade-barreiroslivros.html'
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
    elif _is_lbe_livros():
        tmpl = 'termos-de-uso-lbe.html'
    elif _is_lb_livros():
        tmpl = 'termos-de-uso-lb.html'
    elif _is_brep_livros():
        tmpl = 'termos-de-uso-brep.html'
    elif _is_leituraemais():
        tmpl = 'termos-de-uso-leituraemais.html'
    elif _is_livrinhos():
        tmpl = 'termos-de-uso-livrinhos.html'
    elif _is_vitrini():
        tmpl = 'termos-de-uso-vitrini.html'
    elif _is_livrosemais():
        tmpl = 'termos-de-uso-livrosemais.html'
    elif _is_barreiroslivros():
        tmpl = 'termos-de-uso-barreiroslivros.html'
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
    elif _is_lbe_livros():
        tmpl = 'contato-lbe.html'
    elif _is_lb_livros():
        tmpl = 'contato-lb.html'
    elif _is_brep_livros():
        tmpl = 'contato-brep.html'
    elif _is_leituraemais():
        tmpl = 'contato-leituraemais.html'
    elif _is_livrinhos():
        tmpl = 'contato-livrinhos.html'
    elif _is_vitrini():
        tmpl = 'contato-vitrini.html'
    elif _is_livrosemais():
        tmpl = 'contato-livrosemais.html'
    elif _is_barreiroslivros():
        tmpl = 'contato-barreiroslivros.html'
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
    # A/B da contribuição no site (docs/CONTRIBUICAO_WEB.md): o braço sorteado decide se "Quero receber" vai pro
    # WhatsApp ou abre a entrega no site. Sem configuração ou com erro, contribuicao=None e a landing é a de sempre.
    from web.contribuicao import contexto_landing, gravar_cookie_braco
    contribuicao = contexto_landing(request, 11)
    resp = make_response(render_template('tempero.html', contribuicao=contribuicao))
    gravar_cookie_braco(resp, 11, contribuicao)
    return resp

@app.get("/tempero-e")
def tempero_e():
    from web.checkout import rastrear_visita_funil, COOKIE_MAX_AGE_FUNIL
    produto_id = 11
    pedido_id = rastrear_visita_funil(request, produto_id, estado_novo=1004)
    resp = make_response(render_template('tempero-e.html'))
    resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp

@app.get("/fatia")
def fatia():
    return render_template('fatia.html')

def _planos_app_fatia(produto_basico_id):
    """(preço do Básico, Plano Guiado, desconto do popup) para a landing do Fatia.

    Básico = plano padrão do produto. Guiado = o plano com o App Fatias à venda no site (de vitrine, não
    renovação; o mais caro), de preferência do próprio produto (ex.: /pay/12?plano=completo). O popup
    ("última tentativa" ao clicar no Básico) aparece quando esse plano tem desconto de oferta: leva para
    ele com o token da oferta no link (web/oferta.py). Sem plano com app: (preço, None, None) e a landing
    mostra só o Básico."""
    preco_basico, guiado, desconto = 10.0, None, None
    try:
        from database import listar_planos_com_app, get_plano_venda
        from web.oferta import oferta_do_plano
        from web.links import link_checkout
        basico = get_plano_venda(produto_basico_id)
        if basico:
            preco_basico = float(basico['preco_promocional'])
        ofertas = [p for p in listar_planos_com_app('fatia', renovacao=False, so_venda_web=True) if p['vitrine']]
        ofertas = [p for p in ofertas if p['produto_id'] == produto_basico_id] or ofertas  # ordem: preço
        if ofertas:
            guiado = dict(ofertas[-1])
            guiado['href'] = link_checkout(guiado['produto_id'], guiado)
            desconto = oferta_do_plano(guiado, float(guiado['preco_promocional']))
    except Exception as e:
        logger.error(f"[FATIA-E] Erro ao buscar os planos do app: {e}")
    return preco_basico, guiado, desconto


def _landing_fatia(template):
    """Landing dos anúncios do Fatia (produto 12) com o Básico e o plano com o App Fatias (+ popup de desconto).
    Duas versões em teste A/B pelo Google Ads (Analytics Web → "Teste A/B das landings"): /fatia-e (quiz,
    fatia2-e.html) e /fatia1-e (site anterior, fatia-e.html). Mesmo funil, mesmo checkout, mesmo cookie."""
    from web.checkout import rastrear_visita_funil, COOKIE_MAX_AGE_FUNIL
    from web.links import link_checkout
    from apps import app_config
    produto_id = 12
    pedido_id = rastrear_visita_funil(request, produto_id, estado_novo=1004)
    preco_basico, guiado, desconto = _planos_app_fatia(produto_id)
    cfg = app_config('fatia')
    if not (cfg and cfg.publico):  # app em piloto: a landing dos anúncios fica só com o Básico
        guiado = desconto = None
    resp = make_response(render_template(template, guiado=guiado, desconto=desconto, preco_basico=preco_basico,
                                         basico_href=link_checkout(produto_id)))
    resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp


@app.get("/fatia-e")
def fatia_e():
    return _landing_fatia('fatia2-e.html')


@app.get("/fatia1-e")
def fatia1_e():
    return _landing_fatia('fatia-e.html')


@app.get("/fatia-e-piloto")
def fatia_e_piloto():
    """Piloto do App Fatias (homologação): a mesma landing com Básico + Plano Guiado, enquanto o app
    não é público. Fora do funil (não cria pedido rascunho nem conta no Analytics Web) e fora dos
    buscadores."""
    from web.links import link_checkout
    preco_basico, guiado, desconto = _planos_app_fatia(12)
    resp = make_response(render_template('fatia2-e.html', guiado=guiado, desconto=desconto,
                                         preco_basico=preco_basico, basico_href=link_checkout(12), piloto=True))
    resp.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return resp

@app.get("/orquidea-e")
def orquidea_e():
    from web.checkout import rastrear_visita_funil, COOKIE_MAX_AGE_FUNIL
    produto_id = 14
    pedido_id = rastrear_visita_funil(request, produto_id, estado_novo=1004)
    resp = make_response(render_template('orquidea-e.html'))
    resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp

@app.get("/airfryer-e")
def airfryer_e():
    from web.checkout import rastrear_visita_funil, COOKIE_MAX_AGE_FUNIL
    produto_id = 15
    pedido_id = rastrear_visita_funil(request, produto_id, estado_novo=1004)
    resp = make_response(render_template('airfryer-e.html'))
    resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp

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
