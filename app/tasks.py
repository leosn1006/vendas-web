# worker para tratar as mensagens da fila Redis
import logging
from celery import shared_task
from whatsapp import notificar_admin_erro_sistema

logger = logging.getLogger(__name__)

#TODO rever max_retries e countdown, para não ficar tentando para sempre em caso de erro persistente, e para não demorar muito para tentar novamente em caso de erro temporário
@shared_task(name="tasks.processar_webhook", bind=True, max_retries=0)
def processar_webhook(self, body):
    logger.info("=" * 120)
    logger.info(f"[TASK-WEBHOOK] 📦 Dados recebidos para processamento da mensagem webhook:  {body}")
    from whatsapp_orquestrador import recebe_webhook
    try:
        # ============================================================================================
        #processa a mensagem do webhook, que pode ser uma mensagem nova do cliente, ou uma resposta do cliente a uma mensagem enviada, ou outras interações. O processamento envolve extrair os dados relevantes da mensagem, identificar o pedido associado (se houver), determinar o fluxo de atendimento adequado (introdução, envio de produto, etc) e enfileirar a tarefa correspondente para cada fluxo.
        recebe_webhook(body)
        logger.info("[TASK-WEBHOOK] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except Exception as exc:
        telefone = body.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('contacts', [{}])[0].get('wa_id', '?')
        logger.exception(f"[TASK-WEBHOOK] ❌ tel: {telefone} | body: {str(body)[:500]} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-WEBHOOK | tel: {telefone} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)



@shared_task(name="tasks.enviar_introducao_dinamico", bind=True, max_retries=0)
def fluxo_enviar_introducao_dinamico(self, pedido, mensagem_whatsapp):
    from fluxos.fluxo_introducao_dinamico import executar
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-INTRODUCAO-DIN] 📦 Dados recebidos: \n Pedido: {pedido}")
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-INTRODUCAO-DIN] ✅ Mensagem processada com sucesso")
        logger.info("=" * 120)
    except Exception as exc:
        msg_txt = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0].get('text', {}).get('body', '(sem texto)')
        logger.exception(f"[TASK-INTRODUCAO-DIN] ❌ pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | msg: {str(msg_txt)[:500]} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-INTRODUCAO-DIN | pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(name="tasks.enviar_pedido_dinamico", bind=True, max_retries=0)
def fluxo_enviar_pedido_dinamico(self, pedido, mensagem_whatsapp):
    from fluxos.fluxo_pedido_dinamico import executar
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-PEDIDO-DIN] 📦 Dados recebidos: \n Pedido: {pedido}")
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-PEDIDO-DIN] ✅ Mensagem processada com sucesso")
        logger.info("=" * 120)
    except Exception as exc:
        msg_txt = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0].get('text', {}).get('body', '(sem texto)')
        logger.exception(f"[TASK-PEDIDO-DIN] ❌ pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | msg: {str(msg_txt)[:500]} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-PEDIDO-DIN | pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)



@shared_task(name="tasks.responder_mensagem", bind=True, max_retries=2)
def fluxo_responder_mensagem(self, pedido, mensagem_whatsapp):
    logger.info("=" * 120)
    logger.info(f"[TASK-RESPONDER-MENSAGEM] 📦 Dados recebidos para responder mensagem: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
    from fluxos.fluxo_responder import executar
    from whatsapp import ErroTransienteWhatsApp
    try:
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-RESPONDER-MENSAGEM] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except ErroTransienteWhatsApp as exc:
        msg_txt = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0].get('text', {}).get('body', '(sem texto)')
        logger.warning(f"[TASK-RESPONDER-MENSAGEM] ⚠️ Erro transiente, reagendando | pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        raise self.retry(exc=exc, countdown=60)
    except Exception as exc:
        msg_txt = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0].get('text', {}).get('body', '(sem texto)')
        logger.exception(f"[TASK-RESPONDER-MENSAGEM] ❌ pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | msg: {str(msg_txt)[:500]} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-RESPONDER-MENSAGEM | pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise

@shared_task(name="tasks.conferir_comprovante_dinamico", bind=True, max_retries=0)
def fluxo_conferir_comprovante_dinamico(self, pedido, mensagem_whatsapp):
    logger.info("=" * 120)
    logger.info(f"[TASK-COMPROVANTE-DIN] 📦 Dados recebidos: \n Pedido: {pedido}")
    from fluxos.fluxo_comprovante_dinamico import executar
    try:
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-COMPROVANTE-DIN] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except Exception as exc:
        msg_txt = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0].get('text', {}).get('body', '(sem texto)')
        logger.exception(f"[TASK-COMPROVANTE-DIN] ❌ pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | msg: {str(msg_txt)[:500]} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-COMPROVANTE-DIN | pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(name="tasks.transcrever_audio", bind=True, max_retries=0)
def fluxo_transcrever_audio(self, pedido, mensagem_whatsapp):
    logger.info("=" * 120)
    logger.info(f"[TASK-TRANSCRIBIR-AUDIO] 📦 Dados recebidos para transcrever áudio: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
    from fluxos.fluxo_transcrever import executar
    try:
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-TRANSCRIBIR-AUDIO] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except Exception as exc:
        msg = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0]
        audio_id = msg.get('audio', {}).get('id', '?')
        logger.exception(f"[TASK-TRANSCRIBIR-AUDIO] ❌ pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | audio_id: {audio_id} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-TRANSCRIBIR-AUDIO | pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(name="tasks.followup_pagamento_dinamico", bind=True, max_retries=0)
def fluxo_followup_pagamento_dinamico(self):
    from fluxos.fluxo_followup_dinamico import executar
    try:
        executar()
        logger.info(f"[TASK-FOLLOWUP-DIN] ✅ rotina executada com sucesso!")
    except Exception as exc:
        logger.error(f"[TASK-FOLLOWUP-DIN] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()

@shared_task(name="tasks.enviar_confirmacao_web", bind=True, max_retries=2)
def fluxo_enviar_confirmacao_web(self, pedido_id: int):
    logger.info("=" * 120)
    logger.info(f"[TASK-CONFIRMACAO-WEB] 🛒 Iniciando entrega web para pedido #{pedido_id}")
    from fluxos.fluxo_confirmacao_web_dinamico import executar
    try:
        executar(pedido_id)
        logger.info(f"[TASK-CONFIRMACAO-WEB] ✅ Entrega concluída para pedido #{pedido_id}")
        logger.info("=" * 120)
    except Exception as exc:
        logger.error(f"[TASK-CONFIRMACAO-WEB] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=1)
def processar_uploads_google_ads(self):
    from google.ads.googleads.client import GoogleAdsClient
    try:
        logger.info(f"[TASK-GOOGLE-ADS] 📦 Iniciando processamento de uploads para Google Ads...")
        from fluxos.fluxo_upload_google_ads import executar
        executar()
        logger.info(f"[TASK-GOOGLE-ADS] ✅ rotina executada com sucesso!")

    except Exception as exc:
        logger.error(f"[TASK-GOOGLE-ADS] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1} ")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        # Se a API cair ou houver erro de rede, tenta novamente em 10 min
        raise self.retry(exc=exc, countdown=600)

@shared_task(bind=True, max_retries=1)
def processar_uploads_google_sheets(self):
    try:
        logger.info("[TASK-GOOGLE-SHEETS] 📦 Iniciando exportação para Google Sheets...")
        from fluxos.fluxo_upload_google_ads import exportar_para_google_sheets
        exportar_para_google_sheets()
        logger.info("[TASK-GOOGLE-SHEETS] ✅ Rotina executada com sucesso!")
    except Exception as exc:
        logger.error(f"[TASK-GOOGLE-SHEETS] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()
        raise self.retry(exc=exc, countdown=600)


@shared_task(bind=True, max_retries=0)
def processar_pagamentos_pix(self):
    try:
        logger.info('[TASK-PIX-BB] Iniciando coleta de PIX recebidos')
        from fluxos.fluxo_pix_bb import executar
        executar()
        logger.info('[TASK-PIX-BB] ✅ Concluído')
    except Exception as exc:
        logger.error(f'[TASK-PIX-BB] ❌ Erro: {exc}')
        import traceback
        traceback.print_exc()


@shared_task(bind=True, max_retries=0)
def processar_pagamentos_pix_fechamento(self):
    """Busca PIX de ontem para cobrir o gap 23:15–23:59 não capturado na última execução do dia."""
    try:
        from datetime import datetime, timezone, timedelta
        from fluxos.fluxo_pix_bb import executar
        _SP_TZ = timezone(timedelta(hours=-3))
        ontem = (datetime.now(_SP_TZ) - timedelta(days=1)).strftime('%d/%m/%Y')
        logger.info(f'[TASK-PIX-BB-FECHAMENTO] Buscando PIX de ontem ({ontem})')
        executar(ontem)
        logger.info('[TASK-PIX-BB-FECHAMENTO] ✅ Concluído')
    except Exception as exc:
        logger.error(f'[TASK-PIX-BB-FECHAMENTO] ❌ Erro: {exc}')
        import traceback
        traceback.print_exc()


@shared_task(bind=True, max_retries=0)
def verificar_pagamentos_pendentes(self):
    try:
        logger.info('[TASK-RESILIENCIA-PGTO] Iniciando sweep de pagamentos BB Pay pendentes')
        from fluxos.fluxo_verificar_pagamentos_pendentes import executar
        executar()
        logger.info('[TASK-RESILIENCIA-PGTO] ✅ Sweep concluído')
    except Exception as exc:
        logger.error(f'[TASK-RESILIENCIA-PGTO] ❌ Erro: {exc}')
        import traceback
        traceback.print_exc()


@shared_task(bind=True, max_retries=1)
def enviar_email_entrega(self, pedido_id: int):
    logger.info("=" * 120)
    logger.info(f"[TASK-EMAIL] 📧 Iniciando entrega por e-mail para pedido #{pedido_id}")
    from fluxos.entrega_pedido_email import executar
    try:
        executar(pedido_id)
        logger.info(f"[TASK-EMAIL] ✅ E-mail entregue para pedido #{pedido_id}")
        logger.info("=" * 120)
    except Exception as exc:
        logger.error(f"[TASK-EMAIL] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=60)
