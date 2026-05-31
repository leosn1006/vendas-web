import logging
import random
from whatsapp import marcar_como_lida, enviar_mensagem, enviar_mensagem_digitando, criar_notificacao_admin
from database import (salvar_mensagem_pedido, buscar_historico_conversa, get_produto_by_id,
                      tem_notificacao_em_analise, contar_total_mensagens_pedido,
                      buscar_ultima_mensagem_recebida_por_pedido)
from agente_resposta_produto import responder_cliente_com_historico_produto
from celery_app import celery_app

logger = logging.getLogger(__name__)


def _campos_produto_faltando(produto: dict | None) -> list[str]:
    # faq e url_arquivo_produto são opcionais no agente — apenas prompt_vendas é obrigatório
    campos_obrigatorios = ['prompt_vendas']

    if not produto:
        return campos_obrigatorios

    return [
        campo for campo in campos_obrigatorios
        if not str(produto.get(campo) or '').strip()
    ]

def executar(pedido, mensagem_whatsapp):
    produto = None  # inicializado aqui para estar disponível no except mesmo se a atribuição abaixo falhar
    try:
        logger.info("=" * 120)
        logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 📦 Dados recebidos: \n Pedido: {pedido}")
        # ============================================================================================
        # extrai dados da mensagem primeiro — necessário para marcar como lida e para o early-exit,
        # independente da config do produto
        pedido_id = pedido['id']
        mensagem_cliente = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        # ============================================================================================
        # marcar mensagem como lida imediatamente, independente de validações posteriores
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 📥 Marcando mensagem como lida...")
        try:
            marcar_como_lida(message_id, pedido.get('phone_number_id'))
        except Exception as exc_lida:
            logger.warning(f"[FLUXO-RESPONDER-MENSAGEM] ⚠️ Falha ao marcar como lida (não crítico): {exc_lida}")
        # ============================================================================================
        # se pedido já está em análise pelo admin, salva a mensagem e silencia a IA
        # (não precisa carregar produto nem histórico)
        if tem_notificacao_em_analise(pedido_id):
            salvar_mensagem_pedido(message_id, pedido_id, mensagem_cliente, tipo_mensagem='recebida')
            logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 🔕 Pedido #{pedido_id} em análise pelo admin. Mensagem salva, IA silenciada.")
            return
        # ============================================================================================
        # limite de mensagens por pedido
        total_msgs = contar_total_mensagens_pedido(pedido_id)
        if total_msgs >= 40:
            salvar_mensagem_pedido(message_id, pedido_id, mensagem_cliente, tipo_mensagem='recebida')
            criar_notificacao_admin(pedido_id, pedido.get('produto_id'), 'loop_excesso_msg',
                                    f"Pedido com {total_msgs} mensagens — limite atingido")
            logger.warning(f"[FLUXO-RESPONDER-MENSAGEM] 🛑 Pedido #{pedido_id} com {total_msgs} msgs — silenciando")
            return
        # ============================================================================================
        # texto repetido (autoresponder)
        if len(mensagem_cliente) > 10:
            ultima = buscar_ultima_mensagem_recebida_por_pedido(pedido_id, minutos=10)
            if ultima and mensagem_cliente.strip() == ultima.strip():
                salvar_mensagem_pedido(message_id, pedido_id, mensagem_cliente, tipo_mensagem='recebida')
                criar_notificacao_admin(pedido_id, pedido.get('produto_id'), 'loop_repetidas_msg',
                                        f"Loop de texto: '{mensagem_cliente[:200]}'")
                logger.warning(f"[FLUXO-RESPONDER-MENSAGEM] ⚠️ Loop texto — pedido #{pedido_id}")
                return
        # ============================================================================================
        # carrega e valida config do produto — só necessário a partir daqui, quando a IA vai responder
        produto = get_produto_by_id(pedido.get('produto_id'))
        campos_faltando = _campos_produto_faltando(produto)
        if campos_faltando:
            raise ValueError(
                f"[FLUXO-RESPONDER-MENSAGEM] Configuração do produto {pedido.get('produto_id')} incompleta. "
                f"Campos obrigatórios ausentes: {', '.join(campos_faltando)}"
            )
        # ============================================================================================
        # busca histórico ANTES de salvar a mensagem atual para evitar duplicação no contexto do agente
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 📚 Buscando histórico do pedido #{pedido_id}...")
        historico = buscar_historico_conversa(pedido_id, limite=10)
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 📚 {len(historico)} mensagens no histórico")
        # ============================================================================================
        # salva a mensagem atual após buscar o histórico
        salvar_mensagem_pedido(message_id, pedido_id, mensagem_cliente, tipo_mensagem='recebida')
        # ============================================================================================
        # gera resposta com histórico e contexto completo do produto (prompt + FAQ + PDF)
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 🤖 Gerando resposta com contexto completo do produto...")
        resposta_cliente = responder_cliente_com_historico_produto(mensagem_cliente, historico, produto, pedido)
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 🤖 Resposta gerada: {resposta_cliente}")
        # ============================================================================================
        # None = IA escalou via tool call (estorno, insatisfação etc.), API OpenAI falhou, ou retornou vazio.
        # Em todos os casos o agente já criou a notificação para o admin em agente_resposta_produto.py.
        if resposta_cliente is None:
            logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 🔕 Pedido #{pedido_id}: IA escalou ou falhou. Admin notificado, sem resposta ao cliente.")
            return
        # ============================================================================================
        # envia digitando e agenda envio da resposta com delay humanizado (worker liberado durante a espera)
        try:
            enviar_mensagem_digitando(message_id, pedido.get('phone_number_id'))
        except Exception as exc_digitando:
            logger.warning(f"[FLUXO-RESPONDER-MENSAGEM] ⚠️ Falha ao enviar digitando (não crítico): {exc_digitando}")
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] ⏳ Enviando resposta em {delay:.1f}s via task...")
        celery_app.send_task(
            "tasks.enviar_resposta_cliente",
            args=[pedido, resposta_cliente, pedido_id],
            countdown=delay,
        )
        logger.info("[FLUXO-RESPONDER-MENSAGEM] ✅ Resposta gerada e agendada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[FLUXO-RESPONDER-MENSAGEM] ❌ Erro: {exc}")
        try:
            from whatsapp import notificar_admin_via_template
            nome_produto = produto.get('nome', 'Desconhecido') if produto else 'Desconhecido'
            notificar_admin_via_template(
                pedido,
                nome_produto,
                f"Erro ao responder cliente. {type(exc).__name__}: {str(exc)[:300]}"
            )
        except Exception as exc_notif:
            logger.warning(f"[FLUXO-RESPONDER-MENSAGEM] ⚠️ Falha ao notificar admin: {exc_notif}")
        logger.info("=" * 120)
        raise exc


def enviar_resposta(pedido, resposta_cliente, pedido_id):
    message_id_resposta = enviar_mensagem(pedido, resposta_cliente)
    salvar_mensagem_pedido(message_id_resposta, pedido_id, resposta_cliente, tipo_mensagem='enviada')
    logger.info(f"[FLUXO-RESPONDER-MENSAGEM] ✅ Resposta enviada ao cliente | pedido #{pedido_id}")
