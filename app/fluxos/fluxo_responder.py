import logging
import time
import random
from whatsapp import marcar_como_lida, enviar_mensagem, enviar_mensagem_digitando
from database import salvar_mensagem_pedido, buscar_historico_conversa
from agente_vendas_sem_gluten import responder_cliente_com_historico

logger = logging.getLogger(__name__)

def executar(pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 📦 Dados recebidos: \n Pedido: {pedido}")
        # ============================================================================================
        # grava mensagem recebida
        pedido_id = pedido['id']
        mensagem_cliente = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        salvar_mensagem_pedido(message_id, pedido_id, mensagem_cliente, tipo_mensagem='recebida')
        # ============================================================================================
        # marcar mensagem como lida
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 📥 Marcando mensagem como lida...")
        marcar_como_lida(message_id)
        # ============================================================================================
        # busca histórico da conversa para contextualizar o agente
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 📚 Buscando histórico do pedido #{pedido_id}...")
        historico = buscar_historico_conversa(pedido_id, limite=10)
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 📚 {len(historico)} mensagens no histórico")
        # ============================================================================================
        # gera resposta com histórico e FAQ
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 🤖 Gerando resposta com contexto...")
        resposta_cliente = responder_cliente_com_historico(mensagem_cliente, historico)
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 🤖 Resposta gerada: {resposta_cliente}")
        # ============================================================================================
        # envia digitando e delay humanizado
        enviar_mensagem_digitando(message_id)
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] ⏳ Aguardando {delay:.1f}s...")
        time.sleep(delay)
        # ============================================================================================
        # envia resposta e grava no banco
        message_id_resposta = enviar_mensagem(pedido, resposta_cliente)
        salvar_mensagem_pedido(message_id_resposta, pedido_id, resposta_cliente, tipo_mensagem='enviada')
        # ============================================================================================
        logger.info("[FLUXO-RESPONDER-MENSAGEM] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[FLUXO-RESPONDER-MENSAGEM] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc
