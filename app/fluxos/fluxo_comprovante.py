import logging
import time
import random
import json
from whatsapp import marcar_como_lida, enviar_mensagem, enviar_mensagem_digitando, enviar_documento
from whatsapp_upload import receber_comprovante
from database import (
    salvar_mensagem_pedido,
    atualizar_pedido_com_comprovante,
    atualizar_pedido_com_pagamento,
    get_produto_by_id,
)
from agente_valida_comprovante import validar_comprovante_com_ia

logger = logging.getLogger(__name__)


def _campos_produto_faltando(produto: dict | None) -> list[str]:
    campos_obrigatorios = [
        'mensagem_pagamento_confirmado',
        'url_arquivo_surpresa',
        'caption_arquivo_surpresa',
        'nome_arquivo_surpresa',
        'mensagem_comprovante_invalido',
        'pix_destinatario_esperado',
        'valor_minimo_pagamento',
    ]

    if not produto:
        return campos_obrigatorios

    return [
        campo for campo in campos_obrigatorios
        if not str(produto.get(campo) or '').strip()
    ]


def _to_float(valor, default=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return default

def executar(pedido, mensagem_whatsapp):
    try:
        logger.debug("=" * 120)
        logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 📦 Dados recebidos para responder mensagem: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.debug("[FLUXO-CONFERIR-COMPROVANTE] 🎬 Iniciando fluxo de conferir comprovante...")
        produto = get_produto_by_id(pedido.get('produto_id'))
        campos_faltando = _campos_produto_faltando(produto)
        if campos_faltando:
            raise ValueError(
                f"[FLUXO-CONFERIR-COMPROVANTE] Configuração do produto {pedido.get('produto_id')} incompleta. "
                f"Campos obrigatórios ausentes: {', '.join(campos_faltando)}"
            )

        mensagem_pagamento_confirmado = produto['mensagem_pagamento_confirmado']
        url_arquivo_surpresa = produto['url_arquivo_surpresa']
        caption_arquivo_surpresa = produto['caption_arquivo_surpresa']
        nome_arquivo_surpresa = produto['nome_arquivo_surpresa']
        mensagem_comprovante_invalido = produto['mensagem_comprovante_invalido']
        pix_destinatario_esperado = produto['pix_destinatario_esperado']
        valor_minimo_pagamento = _to_float(produto['valor_minimo_pagamento'], 0.0)

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
        tipo = dados['type'] # image/document
        filename = None
        if tipo == 'image':
            url = dados['image']['url']
            mime = dados['image']['mime_type']
            filename = 'imagem_comprovante'
        elif tipo == 'document':
            url = dados['document']['url']
            mime = dados['document']['mime_type']
            filename = dados['document'].get('filename') or 'documento_comprovante'
        else:
            raise ValueError(f"[FLUXO-CONFERIR-COMPROVANTE] Tipo de mídia não suportado: {tipo}")

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
        valor_pago = _to_float(resultado_validacao.get('valor'), 0.0)
        destinatario_extraido = str(resultado_validacao.get('destinatario') or '').strip().lower()
        destinatario_esperado = str(pix_destinatario_esperado).strip().lower()

        destinatario_correto = destinatario_esperado in destinatario_extraido
        valor_correto = valor_pago >= valor_minimo_pagamento
        comprovante_valido = destinatario_correto and valor_correto

        if comprovante_valido:
            # =======================================================================================
            #salvar no banco de dados que o pedido foi pago, para controle e histórico
            logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 📥 Atualizando pedido com pagamento no banco de dados...")
            atualizar_pedido_com_pagamento(
                pedido_id,
                valor_pago=valor_pago,
                nome_banco=resultado_validacao.get('nome_banco'),
                nome_pagador=resultado_validacao.get('nome_pagador'),
                data_pagamento=resultado_validacao.get('data_pagamento')
            )
            # =======================================================================================
            # enviar digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
            logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 🤖 Enviando digitando para o cliente...")
            enviar_mensagem_digitando(message_id)
            # =======================================================================================
            #envia mensagem de agradecimento e confirmação de pagamento
            logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 🤖 Enviando mensagem de confirmação de pagamento para o cliente...")
            message_id_resposta = enviar_mensagem(pedido, mensagem_pagamento_confirmado)
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem_pagamento_confirmado, tipo_mensagem='enviada')

            # enviar e-book surpresa
            delay = random.uniform(5.0, 8.0)
            logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] ⏳ Aguardando {delay:.1f}s antes de enviar arquivo surpresa...")
            time.sleep(delay)
            logger.debug(f"[FLUXO-CONFERIR-COMPROVANTE] 🤖 Enviando arquivo surpresa para o cliente...")
            message_id_resposta = enviar_documento(
                pedido,
                url_documento=url_arquivo_surpresa,
                caption=caption_arquivo_surpresa,
                filename=nome_arquivo_surpresa
            )
            salvar_mensagem_pedido(
                message_id_resposta,
                pedido_id,
                f"Enviado arquivo surpresa",
                tipo_mensagem='enviada'
            )
        else:
            logger.warning(
                "[FLUXO-CONFERIR-COMPROVANTE] ⚠️ Comprovante inválido. valor=%.2f (mín=%.2f), destinatário extraído='%s', esperado='%s'",
                valor_pago,
                valor_minimo_pagamento,
                destinatario_extraido,
                destinatario_esperado
            )
            enviar_mensagem_digitando(message_id)
            delay = random.uniform(3.0, 6.0)
            time.sleep(delay)
            message_id_resposta = enviar_mensagem(pedido, mensagem_comprovante_invalido)
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem_comprovante_invalido, tipo_mensagem='enviada')
        # ============================================================================================
        logger.info("[FLUXO-CONFERIR-COMPROVANTE] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[FLUXO-CONFERIR-COMPROVANTE] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc
