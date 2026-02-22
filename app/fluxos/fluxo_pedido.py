import logging
import time
import random
from database import salvar_mensagem_pedido, atualizar_estado_pedido, atualizar_pedido_com_interesse_produto
from whatsapp import enviar_audio, enviar_mensagem, enviar_mensagem_digitando, marcar_como_lida, enviar_documento
from agente_vendas_sem_gluten import responder_cliente

logger = logging.getLogger(__name__)

def executar(pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.debug(f"[FLUXO-PEDIDO] 📦 Dados recebidos para pedido: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.debug("[FLUXO-PEDIDO] 🎬 Iniciando fluxo de pedido...")
        # ============================================================================================
        #grava mensagem recebida
        logger.debug(f"[FLUXO-PEDIDO] 📥 Gravando mensagem recebida no banco de dados...")
        pedido_id = pedido['id']
        mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        logger.debug(f"[FLUXO-PEDIDO] 📥 Marcando mensagem como lida no WhatsApp do cliente...")
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        marcar_como_lida(message_id)
        # ============================================================================================
        #verifica se a mensagem é interessada ou não no produto
        logger.debug(f"[FLUXO-PEDIDO] 📥 Mensagem marcada como lida: {mensagem}")
        mensagem_cliente = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        pergunta = f"""Você acabou de enviar no WhatsApp do cliente um audio com a descrição do produto e ela te respondeu a mensagem '{mensagem_cliente}'
        Pela mensagem dele, o cliente está demonstrando interesse no produto? Responda apenas com 'sim' ou 'não'.
            """
        interesse_positivo = responder_cliente(pergunta)
        # Limpar resposta do modelo (remover pontuação e espaços)
        interesse_positivo_limpo = interesse_positivo.strip().rstrip('.!?').lower()
        logger.debug(f"[FLUXO-PEDIDO] 🤖 Feedback do modelo sobre interesse do cliente: {interesse_positivo} (limpo: {interesse_positivo_limpo})")
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando status de digitando para o cliente...")
        enviar_mensagem_digitando(message_id)
        # ============================================================================================
        # envia mensagem do produto
        delay   = random.uniform(9.0, 12.0)
        logger.debug(f"[FLUXO-PEDIDO] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem do produto...")
        time.sleep(delay)
        if interesse_positivo_limpo == 'sim':
            # ========================================================================================
            # atualiar interesse_produto como True no banco de dados, para controle e histórico do pedido
            logger.debug(f"[FLUXO-PEDIDO] ✅ Atualizando interesse_produto como True no banco de dados...")
            atualizar_pedido_com_interesse_produto(pedido_id, True)
            # ========================================================================================
            logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando mensagem do produto para o cliente...")
            msg_pedido_inicial = "Suas receitinhas estão aqui, é só clicar abaixo ⬇"
            message_id_resposta = enviar_mensagem(pedido, msg_pedido_inicial)
            # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = msg_pedido_inicial
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        else:
               # ========================================================================================
            # atualiar interesse_produto como False no banco de dados, para controle e histórico do pedido
            logger.debug(f"[FLUXO-PEDIDO] ✅ Atualizando interesse_produto como False no banco de dados...")
            atualizar_pedido_com_interesse_produto(pedido_id, False)
            # ========================================================================================
            logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando mensagem do produto para o cliente...")
            msg_pedido_inicial = "Queremos o seu melhor, então receba esse presente totalmente sem custo, é só clicar abaixo que é seu ⬇"
            message_id_resposta = enviar_mensagem(pedido, msg_pedido_inicial)
            # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = msg_pedido_inicial
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        #envia pdf do produto
        logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando documento do produto para o cliente...")
        url_documento = "https://lneditor.com.br/static/arquivos/paes-sem-gluten.pdf"
        message_id_resposta = enviar_documento(pedido, url_documento=url_documento)
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_documento
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        delay = random.uniform(10, 15)
        logger.debug(f"[FLUXO-PEDIDO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
        time.sleep(delay)

        if interesse_positivo_limpo == 'sim':
            # =======================================================================================
            logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando mensagem de pedido entregue")
            url_audio_pedido_entregue = "https://lneditor.com.br/static/audios/paes-pedido-entregue.ogg"
            delay = random.uniform(2.0, 5.0)
            logger.debug(f"[FLUXO-PEDIDO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
            time.sleep(delay)
            message_id = enviar_audio(pedido, url_audio=url_audio_pedido_entregue)
            #gravar mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = url_audio_pedido_entregue
            salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        else:
            # ========================================================================================
            msg_pedido_entregue = "Se você gostou do presente, você pode nos ajudar ajudar com R$10,00 ou mais. Essa ajuda iré permitir que outras pessoas conheçam essas receitas sem glutén e possam ter uma vida mais gostosa e saudável também ❤️ Para contribuir, vou mandar os dados do Pix ⬇"
            message_id_resposta = enviar_mensagem(pedido, msg_pedido_entregue)
            # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = msg_pedido_entregue
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar dados do Pix para contribuição
        delay = random.uniform(5, 9)
        logger.info(f"[FLUXO-PEDIDO] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem de dados do Pix para contribuição...")
        time.sleep(delay)
        logger.info(f"[FLUXO-PEDIDO] 🤖 Enviando mensagem de dados do Pix para o cliente...")
        msg_contribuicao = """
            *Informações do PIX*:

        - 💸 *Valor*: R$10, 12, 15, 20
        - 📱 *Chave Pix* (e-mail): admin@lneditor.com.br
        - 👤 *Nome*: Leonardo Santos Negreiros

        Para facilitar, vou te enviar a chave Pix separada, assim é só copiar e colar:
        """
        message_id_resposta = enviar_mensagem(pedido, msg_contribuicao  )
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = msg_contribuicao
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar dados do Pix para contribuição
        logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando mensagem de dados do Pix para o cliente...")
        msg_pix = "admin@lneditor.com.br"
        message_id_resposta = enviar_mensagem(pedido, msg_pix)
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = msg_pix
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar mensagem da surpresa se enviar comprovante
        logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando mensagem de surpresa para o cliente...")
        msg_surpresa = "🎁 *Surpresinha especial* para quem realizar o pagamento e enviar o comprovante!"
        message_id_resposta = enviar_mensagem(pedido, msg_surpresa)
        mensagem = msg_surpresa
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        #atualiza estado do pedido para 'pedido_enviado' (3) no banco de dados, para controlar o fluxo e histórico do pedido
        logger.debug("[FLUXO-PEDIDO] ✅ atualizando estado do pedido como 'pedido_enviado' (3) no banco de dados...")
        atualizar_estado_pedido(pedido_id, 3)
        # ============================================================================================
        logger.info("[FLUXO-PEDIDO] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[FLUXO-PEDIDO] ❌ Erro: {exc}" )
        logger.info("=" * 120)
        raise exc
