import logging
import random
import time
from celery_app import celery_app
from whatsapp_orquestrador import recebe_webhook
from whatspp_enviar_introducao import enviar_audio, marcar_como_lida, enviar_status_gravando_audio
from database import atualizar_estado_pedido, salvar_mensagem_pedido

logger = logging.getLogger(__name__)

#TODO rever max_retries e countdown, para não ficar tentando para sempre em caso de erro persistente, e para não demorar muito para tentar novamente em caso de erro temporário
@celery_app.task(name="tasks.processar_webhook", bind=True, max_retries=0)
def processar_webhook(self, body):
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-WEBHOOK] 📦 Dados recebidos para processamento da mensagem webhook:  {body}")
        recebe_webhook(body)
        logger.info("[TASK-WEBHOOK] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[TASK] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.enviar_introducao", bind=True, max_retries=0)
def fluxo_enviar_introducao(self, pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-INTRODUCAO] 📦 Dados recebidos para introdução: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.info("[TASK-INTRODUCAO] 🎬 Iniciando fluxo de introdução...")
        #grava mensagem recebida
        pedido_id = pedido['id']
        mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        marcar_como_lida(message_id)
        #enviar estatus de gravando audio, para simular que o atendente está gravando um áudio, e manter por alguns segundos (10s)
        #delay = random.uniform(2.0, 5.0)
        #logger.info(f"[TASK-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar status...")
        #time.sleep(delay)
        #numero_destinatario = pedido.get("contact_phone")
        #enviar_status_gravando_audio(numero_destinatario)
        # Enviar áudio de introdução inicial
        #TODO depois pegar pro produto
        url_audio_inicial = "https://lneditor.com.br/static/audios/introducao-paes.ogg"
        delay = random.uniform(2.0, 5.0)
        logger.info(f"[TASK-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
        time.sleep(delay)
        message_id = enviar_audio(pedido, url_audio=url_audio_inicial)
        #gravar mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_audio_inicial
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        #enviar estatus de gravando audio, para simular que o atendente está gravando um áudio, e manter por alguns segundos (10s
        #enviar_status_gravando_audio(numero_destinatario)
        # Enviar áudio de introdução final
        delay = random.uniform(5.0, 8.0)
        time.sleep(delay)
        url_audio_explicativo = "https://lneditor.com.br/static/audios/introducao-explicativa-paes.ogg"
        message_id = enviar_audio(pedido, url_audio=url_audio_explicativo)
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_audio_explicativo
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        logger.info("[TASK-INTRODUCAO] ✅ atualizando estado do pedido como 'introducao_enviada' (2) no banco de dados...")
        atualizar_estado_pedido(pedido['id'], 2)
        logger.info("[TASK-INTRODUCAO] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[TASK-INTRODUCAO] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)
