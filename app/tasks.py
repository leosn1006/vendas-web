import logging
import random
import time
from celery_app import celery_app
from whatsapp_orquestrador import recebe_webhook
from whatspp_enviar_introducao import enviar_audio, marcar_como_lida, enviar_status_gravando_audio

logger = logging.getLogger(__name__)

@celery_app.task(name="tasks.processar_webhook", bind=True, max_retries=3)
def processar_webhook(self, body):
    try:
        delay = random.uniform(3.0, 8.0)
        logger.info(f"[TASK] ⏳ Aguardando {delay:.1f}s antes de responder...")
        # time.sleep(delay)
        recebe_webhook(body)
        logger.info("[TASK] ✅ Mensagem processada com sucesso!")

    except Exception as exc:
        logger.error(f"[TASK] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        raise self.retry(exc=exc, countdown=30)

@celery_app.task(name="tasks.enviar_introducao", bind=True, max_retries=3)
def fluxo_enviar_introducao(self, pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 50)
        logger.info(f"[TASK-INTRODUCAO] 📦 Dados recebidos para introdução: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.info("[TASK-INTRODUCAO] 🎬 Iniciando fluxo de introdução...")

        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        marcar_como_lida(message_id)
        #enviar estatus de gravando audio, para simular que o atendente está gravando um áudio, e manter por alguns segundos (10s)
        delay = random.uniform(2.0, 5.0)
        logger.info(f"[TASK-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar status...")
        time.sleep(delay)
        numero_destinatario = pedido.get("contact_phone")
        enviar_status_gravando_audio(numero_destinatario)
        # Enviar áudio de introdução inicial
        #TODO depois pegar pro produto
        url_audio_inicial = "https://lneditor.com.br/static/audios/introducao-paes.ogg"
        delay = random.uniform(2.0, 5.0)
        enviar_audio(pedido, url_audio=url_audio_inicial)
        #enviar estatus de gravando audio, para simular que o atendente está gravando um áudio, e manter por alguns segundos (10s
        enviar_status_gravando_audio(numero_destinatario)
        # Enviar áudio de introdução final
        delay = random.uniform(5.0, 8.0)
        time.sleep(delay)
        url_audio_explicativo = "https://lneditor.com.br/static/audios/introducao-paes-explicativo.ogg"
        enviar_audio(pedido, url_audio=url_audio_explicativo)

        logger.info("[TASK-INTRODUCAO] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 50)

    except Exception as exc:
        logger.error(f"[TASK-INTRODUCAO] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        logger.info("=" * 50)
        raise self.retry(exc=exc, countdown=30)
