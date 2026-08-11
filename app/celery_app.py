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
        'schedule': crontab(minute='*/30', hour='7-22'),  # a cada 30min das 7h às 22h30
        'options': {'queue': 'baixa'},
    },
    'followup-interesse-dinamico': {
        'task': 'tasks.followup_interesse_dinamico',
        'schedule': crontab(minute='*/5', hour='7-22'),  # a cada 5min das 7h às 22h55
        'options': {'queue': 'normal'},
    },
    'followup-pagamento-web': {
        'task': 'tasks.followup_pagamento_web',
        'schedule': crontab(minute='5,35'),  # a cada 30min, nos minutos :05 e :35
        'options': {'queue': 'baixa'},
    },
#parar um por enquanto, certificado de acesso com problemas
#    'upload-conversoes-google-ads': {
#        'task': 'tasks.processar_uploads_google_ads',
#        'schedule': crontab(minute=0),  # todo hora cheia
#        'options': {'queue': 'baixa'},
#    },
    'upload-gclids-google-sheets': {
        'task': 'tasks.processar_uploads_google_sheets',
        'schedule': crontab(minute=30, hour='22,0'),  # 22h30 e 00h30 (antes do upload do Google Ads às 01h-02h)
        'options': {'queue': 'baixa'},
    },
    'verificar-pagamentos-bb-pay': {
        'task': 'tasks.verificar_pagamentos_pendentes',
        'schedule': crontab(minute='*/10'),  # a cada 10 minutos
        'options': {'queue': 'baixa'},
    },
    'processar-pagamentos-pix': {
        'task': 'tasks.processar_pagamentos_pix',
        'schedule': crontab(minute=15, hour='5-23,0'),  # de hora em hora às :15 (5h15 a 00h15)
        'options': {'queue': 'baixa'},
    },
    'processar-pagamentos-pix-fechamento': {
        'task': 'tasks.processar_pagamentos_pix_fechamento',
        'schedule': crontab(minute=5, hour=0),  # 00h05 — captura PIX de 23:15–23:59 do dia anterior
        'options': {'queue': 'baixa'},
    },
    # NF-e — LBE LIVROS LTDA (config_id=2)
    # Habilitar quando conta corrente LBE estiver configurada e PIX fluindo pela LBE
    # 'reprocessar-nfe-pendentes-lbe': {
    #     'task': 'tasks.reprocessar_nfe_pendentes',
    #     'schedule': crontab(minute='*/30'),
    #     'kwargs': {'config_id': 2, 'limite': 50},
    #     'options': {'queue': 'baixa'},
    # },
    'orcamento-sheets-horario': {
        'task': 'tasks.processar_orcamento_sheets',
        'schedule': crontab(minute=10),  # toda hora no :10 — hoje sempre; ontem também entre 00h–04h
        'options': {'queue': 'baixa'},
    },
    'qualidade-whatsapp-horario': {
        'task': 'tasks.verificar_qualidade_whatsapp',
        'schedule': crontab(minute=20),  # toda hora no :20
        'options': {'queue': 'baixa'},
    },
}

from celery.signals import worker_process_init

@worker_process_init.connect
def init_worker_logging(**kwargs):
    from logging_setup import setup_rotating_file_logging
    worker_name = os.getenv("WORKER_NAME", "worker")
    setup_rotating_file_logging(worker_name)


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
    task_routes={
        # URGENTE — fluxos de vendas diretos
        "tasks.processar_webhook":                  {"queue": "urgente"},
        "tasks.enviar_introducao_dinamico":         {"queue": "urgente"},
        "tasks.enviar_pedido_dinamico":             {"queue": "urgente"},
        "tasks.conferir_comprovante_dinamico":      {"queue": "urgente"},
        "tasks.transcrever_audio":                  {"queue": "urgente"},
        # NORMAL — conversas e entrega
        "tasks.responder_mensagem":                 {"queue": "normal"},
        "tasks.enviar_resposta_cliente":            {"queue": "normal"},
        "tasks.enviar_confirmacao_web":             {"queue": "normal"},
        "tasks.enviar_email_entrega":               {"queue": "normal"},
        "tasks.followup_interesse_dinamico":             {"queue": "normal"},
        "tasks.processar_evento_conta_whatsapp":         {"queue": "normal"},
        # BAIXA — background/agendados
        "tasks.followup_pagamento_dinamico":             {"queue": "baixa"},
        "tasks.followup_pagamento_web":                  {"queue": "baixa"},
        "tasks.processar_uploads_google_ads":            {"queue": "baixa"},
        "tasks.processar_uploads_google_sheets":         {"queue": "baixa"},
        "tasks.processar_pagamentos_pix":                {"queue": "baixa"},
        "tasks.processar_pagamentos_pix_fechamento":     {"queue": "baixa"},
        "tasks.verificar_pagamentos_pendentes":          {"queue": "baixa"},
        "tasks.processar_orcamento_sheets":              {"queue": "baixa"},
        "tasks.verificar_qualidade_whatsapp":            {"queue": "baixa"},
        "tasks.verificar_qualidade_whatsapp_produto":     {"queue": "normal"},
        # NF-e
        "tasks.emitir_nfe":                              {"queue": "normal"},
        "tasks.reprocessar_nfe_pendentes":               {"queue": "baixa"},
    },
)
