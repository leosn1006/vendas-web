import logging
from datetime import datetime
from database import buscar_pedidos_followup
from whatsapp import enviar_mensagem, atualizar_estado_pedido

logger = logging.getLogger(__name__)

def executar():
    agora = datetime.now()
    logger.debug(f"[FLUXO-FOLLOWUP] 🕐 Iniciando verificação de followup: {agora.strftime('%H:%M')}")

    # Busca pedidos estado=3 com data_ultima_atualizacao > 4h
    pedidos = buscar_pedidos_followup(estado_id=3, horas_sem_atualizacao=4)

    if not pedidos:
        logger.debug("[FLUXO-FOLLOWUP] ℹ️ Nenhum pedido pendente de followup.")
        return

    logger.debug(f"[FLUXO-FOLLOWUP] 📋 {len(pedidos)} pedido(s) para followup.")

    for pedido in pedidos:
        try:
            logger.debug(f"[FLUXO-FOLLOWUP] 📱 Enviando followup para pedido #{pedido['id']}")
            msg = "Oi! Vi que você ainda não realizou o pagamento. Posso te ajudar com alguma dúvida? 😊"
            enviar_mensagem(pedido, msg)
            logger.debug(f"[FLUXO-FOLLOWUP] ✅ Followup enviado para pedido #{pedido['id']}")
            # Atualiza estado do pedido para 'followup_enviado' (3)
            logger.debug("[FLUXO-FOLLOWUP] ✅ atualizando estado do pedido como 'followup_enviado' (3) no banco de dados...")
            atualizar_estado_pedido(pedido['id'], 3)
        except Exception as e:
            # Loga o erro mas continua para os outros pedidos
            raise Exception(f"[FLUXO-FOLLOWUP] ❌ Erro no pedido #{pedido['id']}: {e}")
