import logging
from celery_app import celery_app  # era "from app.celery_app"

logger = logging.getLogger(__name__)

@celery_app.task(name="tasks.tarefa_teste")
def tarefa_teste(mensagem: str):
    logger.info(f"[TESTE] Tarefa recebida: {mensagem}")
    print(f"[TESTE] Tarefa recebida: {mensagem}")
    return f"ok: {mensagem}"
