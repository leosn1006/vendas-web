import logging
import time
import random
from database import (
    salvar_mensagem_pedido,
    atualizar_estado_pedido,
    atualizar_pedido_com_interesse_produto,
    atualizar_pedido_com_data_envio_pedido,
    get_produto_by_id,
)
from whatsapp import enviar_audio, enviar_mensagem, enviar_mensagem_digitando, marcar_como_lida, enviar_documento
from agente_verifica_interesse import classificar_interesse_compra

logger = logging.getLogger(__name__)


def _campos_produto_faltando(produto: dict | None) -> list[str]:
    campos_obrigatorios = [
        'url_arquivo_produto',
        'caption_arquivo_produto',
        'nome_arquivo_produto',
        'url_audio_pedido_entregue',
        'mensagem_pedido_enviado_sem_interesse',
        'mensagem_para_pagamento',
        'chave_pix',
    ]

    if not produto:
        return campos_obrigatorios

    return [
        campo for campo in campos_obrigatorios
        if not str(produto.get(campo) or '').strip()
    ]

def executar(pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.debug(f"[FLUXO-PEDIDO] 📦 Dados recebidos para pedido: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.debug("[FLUXO-PEDIDO] 🎬 Iniciando fluxo de pedido...")
        produto = get_produto_by_id(pedido.get('produto_id'))

        campos_faltando = _campos_produto_faltando(produto)
        if campos_faltando:
            raise ValueError(
                f"[FLUXO-PEDIDO] Configuração do produto {pedido.get('produto_id')} incompleta. "
                f"Campos obrigatórios ausentes: {', '.join(campos_faltando)}"
            )

        url_documento = produto['url_arquivo_produto']
        caption_documento = produto['caption_arquivo_produto']
        filename_documento = produto['nome_arquivo_produto']
        url_audio_pedido_entregue = produto['url_audio_pedido_entregue']
        msg_pedido_enviado_sem_interesse = produto['mensagem_pedido_enviado_sem_interesse']
        mensagem_para_pagamento = produto['mensagem_para_pagamento']
        chave_pix = produto['chave_pix']
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
        mensagem_cliente = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        interesse_positivo = classificar_interesse_compra(mensagem_cliente)
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
            msg_pedido_inicial = "Queremos o seu melhor, então receba esse presente totalmente sem custo⬇"
            message_id_resposta = enviar_mensagem(pedido, msg_pedido_inicial)
            # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = msg_pedido_inicial
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        #envia pdf do produto
        logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando documento do produto para o cliente...")
        message_id_resposta = enviar_documento(
            pedido,
            url_documento=url_documento,
            caption=caption_documento,
            filename=filename_documento,
        )
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = f"Enviado documento do produto: {filename_documento}"
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        delay = random.uniform(10, 15)
        logger.debug(f"[FLUXO-PEDIDO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
        time.sleep(delay)

        if interesse_positivo_limpo == 'sim':
            # =======================================================================================
            logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando mensagem de pedido entregue")
            delay = random.uniform(2.0, 5.0)
            logger.debug(f"[FLUXO-PEDIDO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
            time.sleep(delay)
            message_id = enviar_audio(pedido, url_audio=url_audio_pedido_entregue)
            #gravar mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = "Enviado áudio de pedido entregue"
            salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        else:
            # ========================================================================================
            msg_pedido_entregue = msg_pedido_enviado_sem_interesse
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
        msg_contribuicao = mensagem_para_pagamento
        message_id_resposta = enviar_mensagem(pedido, msg_contribuicao  )
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = msg_contribuicao
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar dados do Pix para contribuição
        logger.debug(f"[FLUXO-PEDIDO] 🤖 Enviando mensagem de dados do Pix para o cliente...")
        msg_pix = chave_pix
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
        #atualiza data do envio do pedido no banco de dados, para controle e histórico
        logger.debug(f"[FLUXO-PEDIDO] ✅ Atualizando data do envio do pedido #{pedido['id']} no banco de dados...")
        atualizar_pedido_com_data_envio_pedido(pedido['id'])
        # ============================================================================================
        logger.info("[FLUXO-PEDIDO] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        raise Exception(f"[FLUXO-PEDIDO] ❌ Erro ao processar \n pedido: {pedido}, mensagem: {mensagem}, erro: \n {exc}")
