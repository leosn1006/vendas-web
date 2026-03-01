import logging
import random
from whatsapp import marcar_como_lida
from whatsapp_upload import receber_audio
from agente_transcricao import transcrever_audio
from celery_app import celery_app

logger = logging.getLogger(__name__)

def executar(pedido, mensagem_whatsapp):
    try:
        logger.debug("=" * 120)
        logger.debug(f"[FLUXO-TRANSCREVER] 📦 Dados recebidos para responder mensagem: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.debug("[FLUXO-TRANSCREVER] 🎬 Iniciando fluxo de transcrever...")
        # ============================================================================================
        pedido_id = pedido['id']
        estado_pedido = pedido['estado_id']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        #logger.debug(f"[FLUXO-TRANSCREVER] 📥 Marcando mensagem como lida no WhatsApp do cliente...")
        #marcar_como_lida(message_id)
        # ============================================================================================
        # recuperar audio e só transcreve audio se for do tipo áudio, para evitar erros de transcrição de outros tipos de mídia
        logger.debug(f"[FLUXO-TRANSCREVER] 📥 Recebendo áudio enviado pelo cliente...")
        dados = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]
        tipo = dados['type'] # image
        if tipo == 'audio':
            id_audio = dados['audio']['id']
            mime = dados['audio']['mime_type']
        else:
            raise ValueError(f"[FLUXO-TRANSCREVER] ❌ Tipo de mensagem não suportado para transcrição: {tipo}")

        path_audio = receber_audio(tipo, id_audio, mime, pedido_id)
        texto_transcricao = transcrever_audio(path_audio)

        # Adiciona o texto transcrito no objeto mensagem_whatsapp para os fluxos subsequentes
        mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text'] = {
            'body': texto_transcricao
        }
        logger.debug(f"[FLUXO-TRANSCREVER] ✅ Texto transcrito adicionado ao body da mensagem: {texto_transcricao[:50]}...")

        _MOCK_TELEFONES = {'556181163324', '556181477119'}
        _usar_dinamico = pedido.get('contact_phone') in _MOCK_TELEFONES

        tempo_espera = random.uniform(5, 10)
        if estado_pedido == 1:
            task = "tasks.enviar_introducao_dinamico" if _usar_dinamico else "tasks.enviar_introducao"
            celery_app.send_task(task, args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
            logger.debug(f"[FLUXO-TRANSCREVER] ✅ Enviado ao fluxo de introdução ({'dinâmico' if _usar_dinamico else 'padrão'})!")
        elif estado_pedido == 2:
            task = "tasks.enviar_pedido_dinamico" if _usar_dinamico else "tasks.enviar_pedido"
            celery_app.send_task(task, args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
            logger.debug(f"[FLUXO-TRANSCREVER] ✅ Enviado ao fluxo de pedido ({'dinâmico' if _usar_dinamico else 'padrão'})!")
        else:
            celery_app.send_task("tasks.responder_mensagem", args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
            logger.debug("[FLUXO-TRANSCREVER] ✅ Mensagem processada com sucesso e enviada ao fluxo de responder mensagem!")

    except Exception as exc:
        raise Exception(f"[FLUXO-TRANSCREVER] ❌ Erro: {exc}")
