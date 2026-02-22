import logging
import time
import random
from database import salvar_mensagem_pedido, atualizar_estado_pedido
from whatsapp import enviar_audio, enviar_imagem, enviar_mensagem, enviar_mensagem_digitando, marcar_como_lida


logger = logging.getLogger(__name__)

def executar(pedido, mensagem_whatsapp):
    try:
        logger.debug("[FLUXO-INTRODUCAO] 🎬 Iniciando fluxo de introdução...")
        # ============================================================================================
        #grava mensagem recebida
        pedido_id = pedido['id']
        mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        message_id_original = message_id
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        logger.debug(f"[FLUXO-INTRODUCAO] 📥 Marcando mensagem como lida no WhatsApp do cliente...")
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        marcar_como_lida(message_id)
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-INTRODUCAO] 🤖 Enviando status de digitando para o cliente...")
        enviar_mensagem_digitando(message_id)
        # ============================================================================================
        # Enviar áudio de introdução inicial, depois de um tempo de espera aleatório para simular o tempo que o atendente levaria para ler a mensagem e preparar a resposta. O áudio pode ser personalizado com base no produto ou campanha, ou pode ser um áudio genérico de boas-vindas e introdução.
        #TODO depois pegar pro produto
        delay = random.uniform(8, 10)
        logger.debug(f"[FLUXO-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
        time.sleep(delay)
        url_audio_inicial = "https://lneditor.com.br/static/audios/introducao-paes.ogg"
        message_id = enviar_audio(pedido, url_audio=url_audio_inicial)
        #gravar mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_audio_inicial
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-INTRODUCAO] 🤖 Enviando status de digitando 2 para o cliente...")
        enviar_mensagem_digitando(message_id_original)
        # ============================================================================================
        # Enviar áudio de introdução final
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio explicativo...")
        time.sleep(delay)
        url_audio_explicativo = "https://lneditor.com.br/static/audios/introducao-explicativa-paes.ogg"
        message_id = enviar_audio(pedido, url_audio=url_audio_explicativo)
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_audio_explicativo
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-INTRODUCAO] 🤖 Enviando status de digitando 3 para o cliente...")
        enviar_mensagem_digitando(message_id_original)
        # ============================================================================================
        #envia imagem complementar
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar imagem complementar...")
        time.sleep(delay)
        url_imagem_complementar = "https://lneditor.com.br/static/images/paes-foto-semanal.jpg"
        message_id = enviar_imagem(pedido, url_imagem_complementar)
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_imagem_complementar
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-INTRODUCAO] 🤖 Enviando status de digitando 4 para o cliente...")
        enviar_mensagem_digitando(message_id_original)
        # ============================================================================================
        # enviar mensagem de texto explicativa complementar, para reforçar a mensagem do áudio, e para ficar registrado no histórico do pedido o conteúdo da mensagem, para controle e para o caso de o cliente não ouvir o áudio
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem explicativa complementar...")
        time.sleep(delay)
        msg_explicativa = """*Esses são alguns pães que fiz na última semana 😋*
        Posso te enviar o livrinho agora?"""
        message_id_resposta = enviar_mensagem(pedido, msg_explicativa)
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = msg_explicativa
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # atualiza estado do pedido para 'introducao_enviada' (2) no banco de dados, para controlar o fluxo e histórico do pedido
        logger.debug("[FLUXO-INTRODUCAO] ✅ atualizando estado do pedido como 'introducao_enviada' (2) no banco de dados...")
        atualizar_estado_pedido(pedido['id'], 2)
        # ============================================================================================
        logger.debug("[FLUXO-INTRODUCAO] ✅ Mensagem processada com sucesso!")
        logger.debug("=" * 120)

    except Exception as exc:
        logger.error(f"[FLUXO-INTRODUCAO] ❌ Erro: {exc}")
        logger.debug("=" * 120)
        raise exc
