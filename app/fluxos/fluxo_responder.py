import logging
import time
import random
from whatsapp import marcar_como_lida, enviar_mensagem, enviar_mensagem_digitando, enviar_documento
from database import salvar_mensagem_pedido
from agente_vendas_sem_gluten import responder_cliente

logger = logging.getLogger(__name__)

def executar(pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 📦 Dados recebidos para responder mensagem: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.debug("[FLUXO-RESPONDER-MENSAGEM] 🎬 Iniciando fluxo de responder mensagem...")
        # ============================================================================================
        #grava mensagem recebida
        pedido_id = pedido['id']
        mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        marcar_como_lida(message_id)
        # ============================================================================================
        # responder mensagem do cliente
        #verifica se a mensagem é interessada ou não no produto
        # TODO busca chave Pix pelo produto, para não ficar hardcodado
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 📥 Mensagem marcada como lida: {mensagem}")
        mensagem_cliente = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        pergunta = f"""
            Role: Você é a Luiza, uma vendedora atenciosa e cordial. Sua missão é dar continuidade ao atendimento de um cliente no WhatsApp que já recebeu um áudio explicativo, o e-book (PDF), dados para pagamento e que ele receberá um e-book surpresa caso envie o comprovante de pagamento.
            Diretrizes de Resposta:
                Se o cliente mostrar interesse em pagar ou pedir o Pix: Forneça a chave Pix admin@lneditor.com.br e reforce que o valor mínimo sugerido é de R$ 10,00, mas ele pode contribuir com mais se desejar.
                Se o cliente enviar o comprovante (ou disser que pagou): Agradeça com entusiasmo e informe que está enviando o E-book Surpresa em instantes.
                Se o cliente pedir reembolso: Responda educadamente que a solicitação será analisada e que a equipe de suporte entrará em contato diretamente com ele em breve.
                Sobre o E-book: Se ele tiver dúvidas de como acessar, lembre-o que o arquivo PDF já está na conversa e basta clicar para abrir.

            Restrições:
                Responda de forma sucinta (formato WhatsApp).
                Use emojis moderadamente para ser amigável.
                Não adicione explicações extras para mim, responda apenas com a fala da Luiza.

            Pergunta do cliente: '{mensagem_cliente}'
            """
        resposta_cliente = responder_cliente(pergunta)
        # Limpar resposta do modelo (remover pontuação e espaços)
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 🤖 Resposta do modelo sobre a pergunta: {resposta_cliente} ")
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 🤖 Enviando resposta para o cliente: {resposta_cliente}")
        enviar_mensagem_digitando(message_id)
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] ⏳ Aguardando {delay:.1f}s antes de enviar resposta para o cliente...")
        time.sleep(delay)
        message_id_resposta = enviar_mensagem(pedido, resposta_cliente)
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = resposta_cliente
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # atualizar_estado_pedido(pedido['id'], 2)
        # ============================================================================================
        logger.info("[FLUXO-RESPONDER-MENSAGEM] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[FLUXO-RESPONDER-MENSAGEM] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc
