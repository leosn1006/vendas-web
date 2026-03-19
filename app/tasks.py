# worker para tratar as mensagens da fila Redis
import logging
from celery import shared_task
from logging_setup import setup_rotating_file_logging

setup_rotating_file_logging("worker")

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
        logger.error(f"[TASK-INTRODUCAO-DIN] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
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
        logger.error(f"[TASK-PEDIDO-DIN] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
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
        logger.error(f"[TASK-COMPROVANTE-DIN] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
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
