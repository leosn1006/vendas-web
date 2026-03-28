import sys
import os
from celery import Celery
from celery.schedules import crontab


# Garante que /app está no path para subpacotes como fluxos.*
sys.path.insert(0, '/app')

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "vendas",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"]  # era "app.tasks", agora só "tasks"
)

celery_app.conf.beat_schedule = {
    'followup-pagamento-dinamico': {
        'task': 'tasks.followup_pagamento_dinamico',
        'schedule': crontab(minute=0, hour='8-20'),  # todo hora cheia das 8h às 20h
    },
#parar um por enquanto, certificado de acesso com problemas
#    'upload-conversoes-google-ads': {
#        'task': 'tasks.processar_uploads_google_ads',
#        'schedule': crontab(minute=0),  # todo hora cheia
#    },
    'upload-gclids-google-sheets': {
        'task': 'tasks.processar_uploads_google_sheets',
        'schedule': crontab(minute=30, hour='22,0'),  # 22h30 e 00h30 (antes do upload do Google Ads às 01h-02h)
    },
    'verificar-pagamentos-bb-pay': {
        'task': 'tasks.verificar_pagamentos_pendentes',
        'schedule': crontab(minute='*/10'),  # a cada 10 minutos
    },
}

from celery.signals import worker_process_init

@worker_process_init.connect
def init_worker_logging(**kwargs):
    from logging_setup import setup_rotating_file_logging
    setup_rotating_file_logging("worker")


celery_app.conf.update(
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=86400,
    worker_hijack_root_logger=False,
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
