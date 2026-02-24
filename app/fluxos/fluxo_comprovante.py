import logging
import time
import random
import json
from whatsapp import marcar_como_lida, enviar_mensagem, enviar_mensagem_digitando, enviar_documento
from whatsapp_upload import receber_comprovante
from database import salvar_mensagem_pedido, atualizar_pedido_com_comprovante, atualizar_pedido_com_pagamento
from agente_valida_comprovante import validar_comprovante_com_ia

logger = logging.getLogger(__name__)

def executar(pedido, mensagem_whatsapp):
    try:
        logger.debug("=" * 120)
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 📦 Dados recebidos para responder mensagem: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.debug("[FLUXO-CONFERIR-COMPROVANTE] 🎬 Iniciando fluxo de conferir comprovante...")
        # ============================================================================================
        #grava mensagem recebida
        pedido_id = pedido['id']
        # mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        # salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 📥 Marcando mensagem como lida no WhatsApp do cliente...")
        marcar_como_lida(message_id)
        # ============================================================================================
        # recuperar comprovante e persistir
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 📥 Recebendo comprovante enviado pelo cliente...")
        dados = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]
        tipo = dados['type'] # image
        if tipo == 'image':
            url = dados['image']['url']
            mime = dados['image']['mime_type']
            filename = None
        else:
            url = dados['document']['url']
            mime = dados['document']['mime_type']
            filename = dados['document']['filename']

        path_comprovante = receber_comprovante(tipo, url, mime, filename, pedido_id)
        # ============================================================================================
        # Salvar caminho do comprovante no banco de dados, associado ao pedido, para histórico e controle
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 📥 Atualizando pedido com caminho do comprovante no banco de dados...")
        atualizar_pedido_com_comprovante(pedido_id, path_comprovante)
        # ============================================================================================
        #salvar mensagem do comprovante recebido no banco de dados, associada ao pedido, para histórico e controle
        mensagem = f"Comprovante recebido: {filename}"
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        # validar comprovante com IA
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 📥 Validando comprovante com IA...")
        resultado_validacao_json = validar_comprovante_com_ia(path_comprovante)
        resultado_validacao = json.loads(resultado_validacao_json)
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 📥 Resultado da validação: {resultado_validacao}")
        #if resultado_validacao['valor'] > 0.0:
        # and resultado_validacao['destinatario_correto']:
        # =======================================================================================
        #salvar no banco de dados que o pedido foi pago, para controle e histórico
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 📥 Atualizando pedido com pagamento no banco de dados...")
        atualizar_pedido_com_pagamento(pedido_id, valor_pago=resultado_validacao['valor'], nome_banco=resultado_validacao['nome_banco'], nome_pagador=resultado_validacao['nome_pagador'], data_pagamento=resultado_validacao['data_pagamento'])
        # =======================================================================================
        # enviar digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 🤖 Enviando digitando para o cliente...")
        enviar_mensagem_digitando(message_id)
        # =======================================================================================
        #envia mensagem de agradecimento e confirmação de pagamento, e entrega do e-book surpresa, para o cliente
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 🤖 Enviando mensagem de agradecimento e confirmação de pagamento para o cliente...")
        enviar_mensagem(pedido, "Obrigado pelo envio do comprovante e sua honestidade 🙏🏼! Estamos confirmando o pagamento e em breve você receberá seu e-book surpresa! 🎁")
        # enviar mensagem de confirmação de pagamento e entrega do e-book surpresa
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem de confirmação de pagamento para o cliente...")
        time.sleep(delay)
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 🤖 Enviando mensagem de confirmação de pagamento para o cliente...")
        url_surpresa = "https://lneditor.com.br/static/arquivos/bolos-sem-gluten.pdf"
        caption = "Sua surpresa chegou! 🎁"
        filename = "BOLOS SEM GLUTEN-RECEITAS-SURPRESA.pdf"
        enviar_documento(pedido, url_documento=url_surpresa, caption=caption, filename=filename)
        #else:
        #    # enviar digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        #    logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 🤖 Enviando digitando para o cliente...")
        #    enviar_mensagem_digitando(message_id)
        #    # =======================================================================================
        #    # enviar mensagem de comprovante inválido, e solicitar que envie um comprovante válido para receber o e-book surpresa
        #    delay = random.uniform(5.0, 8.0)
        #    logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem de comprovante inválido para o cliente...")
        #    time.sleep(delay)
        #    logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 🤖 Enviando mensagem de comprovante inválido para o cliente...")
        #    msg_comprovante_invalido = "O comprovante enviado não é válido. Por favor, verifique se o pagamento foi realizado corretamente, se o valor é igual ou superior a R$10,00 e se a chave Pix é correta "
        #    message_id_resposta = enviar_mensagem(pedido, msg_comprovante_invalido)
        #    # ============================================================================================
        #    # salva mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        #    mensagem = msg_comprovante_invalido
        #    salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        logger.info("[FLUXO-CONFERIR-COMPROVANTE] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[FLUXO-CONFERIR-COMPROVANTE] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc
