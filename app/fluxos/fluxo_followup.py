import logging
from datetime import datetime
from database import buscar_pedidos_followup, atualizar_estado_pedido, atualizar_pedido_com_data_followup
from whatsapp import enviar_mensagem

logger = logging.getLogger(__name__)

def executar():
    agora = datetime.now()
    logger.debug(f"[FLUXO-FOLLOWUP] 🕐 Iniciando verificação de followup: {agora.strftime('%H:%M')}")

    # Busca pedidos estado=3 com data_ultima_atualizacao > 4h
    pedidos = buscar_pedidos_followup(horas_sem_atualizacao=4)

    if not pedidos:
        logger.debug("[FLUXO-FOLLOWUP] ℹ️ Nenhum pedido pendente de followup.")
        return

    logger.debug(f"[FLUXO-FOLLOWUP] 📋 {len(pedidos)} pedido(s) para followup.")

    for pedido in pedidos:
        try:
            logger.debug(f"[FLUXO-FOLLOWUP] 📱 Enviando followup para pedido #{pedido['id']}")
            msg = "Oi! Sei que o dia a dia é bem corrido, mas o nosso sistema ainda não identificou o seu pagamento. \n \n Será que você consegue ajudar nosso projeto com apenas R$10,00? Posso te ajudar com alguma dúvida? 😊"
            enviar_mensagem(pedido, msg)
            logger.debug(f"[FLUXO-FOLLOWUP] ✅ Followup enviado para pedido #{pedido['id']}")
            # Atualiza estado do pedido para 'followup_enviado' (4)
            logger.debug("[FLUXO-FOLLOWUP] ✅ atualizando estado do pedido como 'followup_enviado' (4) no banco de dados...")
            atualizar_estado_pedido(pedido['id'], 4)  # estado 4 = followup_enviado
            # Atualiza data do followup no banco de dados, para controle e histórico
            logger.debug(f"[FLUXO-FOLLOWUP] ✅ Atualizando data do followup para o pedido #{pedido['id']}...")
            atualizar_pedido_com_data_followup(pedido['id'])
            logger.debug(f"[FLUXO-FOLLOWUP] ✅ Estado do pedido #{pedido['id']} atualizado para 'followup_enviado' (4)!")
        except Exception as e:
            # Loga o erro mas continua para os outros pedidos
            raise Exception(f"[FLUXO-FOLLOWUP] ❌ Erro no pedido #{pedido['id']}: {e}")
