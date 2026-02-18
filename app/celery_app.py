import os
from celery import Celery

# Lê a mesma variável de ambiente que definimos no docker-compose
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "vendas",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"]  # onde as tasks vão ficar
)

celery_app.conf.update(
    # Fuso horário consistente com o docker-compose
    timezone="America/Sao_Paulo",
    enable_utc=True,

    # Serialização
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Resultado das tasks expira em 24h (não acumula lixo no Redis)
    result_expires=86400,

    # Worker não pega mais tarefas do que consegue processar
    worker_prefetch_multiplier=1,

    # Confirma a tarefa só depois de executar (evita perda se o worker cair)
    task_acks_late=True,
)
