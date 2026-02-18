import logging
import random
import time
from celery_app import celery_app
from whatsapp_orquestrador import recebe_webhook

logger = logging.getLogger(__name__)

@celery_app.task(name="tasks.processar_webhook", bind=True, max_retries=3)
def processar_webhook(self, body):
    try:
        delay = random.uniform(3.0, 8.0)
        logger.info(f"[TASK] ⏳ Aguardando {delay:.1f}s antes de responder...")
        time.sleep(delay)

        recebe_webhook(body)
        logger.info("[TASK] ✅ Mensagem processada com sucesso!")

    except Exception as exc:
        logger.error(f"[TASK] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        raise self.retry(exc=exc, countdown=30)
