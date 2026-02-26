# worker para tratar as mensagens da fila Redis
import logging
from celery_app import shared_task

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
        logger.error(f"[TASK] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)


@shared_task(name="tasks.enviar_introducao", bind=True, max_retries=0)
def fluxo_enviar_introducao(self, pedido, mensagem_whatsapp):
    from fluxos.fluxo_introducao import executar
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-INTRODUCAO] 📦 Dados recebidos para introdução: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-INTRODUCAO] ✅ Mensagem processada com sucesso")
        logger.info("=" * 120)
    except Exception as exc:
        logger.error(f"[TASK-INTRODUCAO] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)

@shared_task(name="tasks.enviar_pedido", bind=True, max_retries=0)
def fluxo_enviar_pedido(self, pedido, mensagem_whatsapp):
    logger.info("=" * 120)
    logger.info(f"[TASK-PEDIDO] 📦 Dados recebidos para introdução: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
    from fluxos.fluxo_pedido import executar
    try:
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-PEDIDO] ✅ Mensagem processada com sucesso!")
    except Exception as exc:
        logger.error(f"[TASK-PEDIDO] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1} ")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)

@shared_task(name="tasks.responder_mensagem", bind=True, max_retries=0)
def fluxo_responder_mensagem(self, pedido, mensagem_whatsapp):
    logger.info("=" * 120)
    logger.info(f"[TASK-RESPONDER-MENSAGEM] 📦 Dados recebidos para responder mensagem: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
    from fluxos.fluxo_responder import executar
    try:
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-RESPONDER-MENSAGEM] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except Exception as exc:
        logger.error(f"[TASK-RESPONDER-MENSAGEM] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1} ")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)

@shared_task(name="tasks.conferir_comprovante", bind=True, max_retries=0)
def fluxo_conferir_comprovante(self, pedido, mensagem_whatsapp):
    logger.info("=" * 120)
    logger.info(f"[TASK-CONFERIR-COMPROVANTE] 📦 Dados recebidos para conferir comprovante: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
    from fluxos.fluxo_comprovante import executar
    try:
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-CONFERIR-COMPROVANTE] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except Exception as exc:
        logger.error(f"[TASK-CONFERIR-COMPROVANTE] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1} ")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
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
        logger.error(f"[TASK-TRANSCRIBIR-AUDIO] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1} ")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)

@shared_task(name="tasks.followup_pagamento", bind=True, max_retries=0)
def fluxo_followup_pagamento(self):
    from fluxos.fluxo_followup import executar
    try:
        executar()
        logger.info(f"[TASK-FOLLOWUP] ✅ rotina executada com sucesso!")
    except Exception as exc:
        logger.error(f"[TASK-FOLLOWUP] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()

@shared_task(bind=True, max_retries=0)
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
