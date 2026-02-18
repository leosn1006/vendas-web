import logging
from app.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(name="tasks.tarefa_teste")
def tarefa_teste(mensagem: str):
    """
    Tarefa dummy — só para validar que o Celery e o Redis estão funcionando.
    Pode remover depois que o fluxo estiver confirmado.
    """
    logger.info(f"[TESTE] Tarefa recebida: {mensagem}")
    print(f"[TESTE] Tarefa recebida: {mensagem}")
    return f"ok: {mensagem}"
