import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "vendas",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"]  # era "app.tasks", agora só "tasks"
)

celery_app.conf.update(
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=86400,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_connection_retry_on_startup=True, # Tenta conectar ao Redis ao iniciar
    task_publish_retry=True,                 # Se o Redis oscilar no momento do .delay(), o Celery tenta reenviar
    task_publish_retry_policy={
        'max_retries': 3,
        'interval_start': 0.2,
        'interval_step': 0.2,
        'interval_max': 1,
    },
)
