"""
Este arquivo mostra como integrar o sistema de notificações no app.py atual.
Copie e adapte as partes necessárias.

IMPORTANTE: As notificações são SIMPLES e diretas.
Exemplo do que você receberá no WhatsApp:
  "⚠️ Erro no sistema
   ValueError em webhook_receive às 14:32:18
   Acesse o sistema para verificar os logs."

Todos os detalhes técnicos ficam nos logs do servidor.
"""

from flask import Flask, send_file, request, jsonify, render_template
from webhook_whatsApp import recebe_webhook
from seguranca import whatsapp_security

# ============ ADICIONAR ESTAS IMPORTAÇÕES ============
from notificacoes import notificador, notificar_erro
from excecoes import ErroNotificavel
from datetime import datetime
# ====================================================

import os

app = Flask(__name__,
            static_folder='../static',
            static_url_path='/static')


# ============ ADICIONAR ESTE HANDLER GLOBAL ============
@app.errorhandler(Exception)
def handle_exception(e):
    """
    Captura TODOS os erros não tratados da aplicação.
    Envia notificação simples para o WhatsApp do admin.
    """
    # Coleta apenas o endpoint para contexto mínimo
    contexto = {}
    try:
        if request and request.endpoint:
            contexto['Endpoint'] = request.endpoint
    except:
        pass

    # Notifica o erro (mensagem será simples e genérica)
    notificador.notificar_erro(e, contexto_adicional=contexto)

    # Loga detalhes completos no servidor
    print(f"[ERRO GLOBAL] {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()

    # Retorna resposta apropriada ao cliente


# Rota GET para verificação inicial do webhook (WhatsApp envia challenge)
@app.get("/api/v1/webhook-whatsapp")
def webhook_verify():
    print("Verificando webhook do WhatsApp...")
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if whatsapp_security.validate_webhook_verification(mode, token):
        print('Webhook verificado com sucesso!')
        return challenge, 200
    else:
        print('Falha na verificação do webhook')
        return jsonify({'error': 'Forbidden', 'message': 'Token de verificação inválido'}), 403


# ============ ADICIONAR O DECORATOR AQUI ============
@app.post("/api/v1/webhook-whatsapp")
@notificar_erro()  # <- Notifica qualquer erro nesta rota crítica
# ====================================================
def webhook_receive():
    print("=" * 80)
    print(f"[WEBHOOK] Requisição recebida de: {request.remote_addr}")
    print(f"[WEBHOOK] Content-Type: {request.content_type}")
    print(f"[WEBHOOK] X-Hub-Signature-256: {request.headers.get('X-Hub-Signature-256', 'AUSENTE')}")

    # Valida a assinatura do WhatsApp
    if not whatsapp_security.validate_signature():
        print('[WEBHOOK] ❌ Assinatura INVÁLIDA!')
        print(f"[WEBHOOK] App Secret usado: {whatsapp_security.app_secret[:10]}***")
        return jsonify({'error': 'Unauthorized', 'message': 'Assinatura inválida'}), 401

    print("[WEBHOOK] ✅ Assinatura VÁLIDA!")

    try:
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


# Rotas normais (não precisam do decorator, handler global já cobre)
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


# ============ OPCIONAL: Rota para testar notificações ============
@app.get("/admin/testar-notificacao")
def testar_notificacao():
    """Rota para testar se as notificações estão funcionando."""
    try:
        mensagem = (
            "🧪 *TESTE DE NOTIFICAÇÃO*\n\n"
            "O sistema de alertas está funcionando!\n"
            f"Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        )
        sucesso = notificador.enviar_notificacao(mensagem, forcar=True)

        if sucesso:
            return jsonify({'status': 'ok', 'message': 'Notificação enviada com sucesso!'})
        else:
            return jsonify({'status': 'error', 'message': 'Falha ao enviar notificação'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
# ==================================================================


"""
RESUMO DO QUE ADICIONAR NO app.py:

1. Importar no topo:
   from notificacoes import notificador, notificar_erro
   from excecoes import ErroNotificavel

2. Adicionar handler global (após criar o app):
   @app.errorhandler(Exception)
   def handle_exception(e):
       ...
   # Este handler envia notificação SIMPLES no WhatsApp e loga detalhes no servidor

3. Adicionar decorator nas rotas críticas:
   @app.post("/api/v1/webhook-whatsapp")
   @notificar_erro()
   def webhook_receive():
       ...

4. Configurar .env:
   ADMIN_WHATSAPP_NUMBER=5511999999999

5. Testar:
   docker compose exec app python scripts/exemplo_notificacoes.py

LEMBRE-SE:
- WhatsApp = notificação simples (apenas tipo do erro e hora)
- Logs do servidor = detalhes completos (traceback, contexto, query SQL, etc)
"""
