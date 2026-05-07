import logging
import random
from whatsapp import marcar_como_lida, enviar_mensagem, enviar_mensagem_digitando
from database import salvar_mensagem_pedido, buscar_historico_conversa, get_produto_by_id
from agente_resposta_produto import responder_cliente_com_historico_produto
from celery_app import celery_app

logger = logging.getLogger(__name__)


def _campos_produto_faltando(produto: dict | None) -> list[str]:
    campos_obrigatorios = ['prompt_vendas', 'faq', 'url_arquivo_produto']

    if not produto:
        return campos_obrigatorios

    return [
        campo for campo in campos_obrigatorios
        if not str(produto.get(campo) or '').strip()
    ]

def executar(pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 📦 Dados recebidos: \n Pedido: {pedido}")
        produto = get_produto_by_id(pedido.get('produto_id'))
        campos_faltando = _campos_produto_faltando(produto)
        if campos_faltando:
            raise ValueError(
                f"[FLUXO-RESPONDER-MENSAGEM] Configuração do produto {pedido.get('produto_id')} incompleta. "
                f"Campos obrigatórios ausentes: {', '.join(campos_faltando)}"
            )
        # ============================================================================================
        # grava mensagem recebida
        pedido_id = pedido['id']
        mensagem_cliente = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        # ============================================================================================
        # marcar mensagem como lida
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 📥 Marcando mensagem como lida...")
        try:
            marcar_como_lida(message_id, pedido.get('phone_number_id'))
        except Exception as exc_lida:
            logger.warning(f"[FLUXO-RESPONDER-MENSAGEM] ⚠️ Falha ao marcar como lida (não crítico): {exc_lida}")
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
        # None = IA decidiu escalar mas pedido já está em análise pelo admin
        if resposta_cliente is None:
            logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 🔕 Pedido #{pedido_id} em análise pelo admin. IA silenciada.")
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
        # ============================================================================================
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
