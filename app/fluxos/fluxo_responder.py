import logging
import random
from whatsapp import enviar_mensagem, criar_notificacao_admin, exigir_numero_operacional
from database import (salvar_mensagem_pedido, buscar_historico_conversa, get_produto_by_id,
                      tem_notificacao_em_analise, contar_total_mensagens_pedido,
                      buscar_ultima_mensagem_recebida_por_pedido, get_pedido,
                      tem_notificacao_em_analise_por_motivo)
from agente_resposta_produto import (responder_cliente_com_historico_produto,
                                     ACAO_RESPONDER, ACAO_RISCO_VIDA, ACAO_PAGAMENTO_INFORMADO,
                                     MENSAGEM_RISCO_VIDA)
from fluxos._mensagem_sem_resposta import mensagem_sem_resposta, fala_em_risco_a_vida
from estados_pedido import ESTADO_COMPROVANTE_EM_ANALISE, pedido_esta_pago
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

# Texto que chega junto com o comprovante espera o fluxo do comprovante terminar (estado 13 → 0) para a IA já
# saber que o pedido está pago. Limite de tentativas porque a trava 13 não tem prazo (worker morto = 13 para sempre).
_ESPERA_COMPROVANTE_S = 20
_MAX_TENTATIVAS_ESPERA = 5  # até ~100 s; o comprovante leva 15–25 s de espera + download + IA + ações
# "Já paguei" espera este tempo antes de virar pagamento: se a imagem do comprovante vier logo depois, ela trava o
# pedido primeiro e tem prioridade (valor, banco e pagador lidos do arquivo).
_ESPERA_PAGAMENTO_INFORMADO_S = 30


def _reler_pedido(pedido: dict) -> dict:
    """O `pedido` da task é a foto do webhook (ex.: estado 13 e valor_pago 0 enquanto o comprovante é processado).
    Relê no banco; se falhar, segue com a foto."""
    try:
        atual = get_pedido(pedido['id'])
    except Exception as exc:
        logger.warning(f"[FLUXO-RESPONDER-MENSAGEM] ⚠️ Falha ao reler pedido #{pedido.get('id')}: {exc}")
        atual = None
    return {**pedido, **atual} if atual else pedido


def executar(pedido, mensagem_whatsapp, tentativa_espera=0):
    produto = None  # inicializado aqui para estar disponível no except mesmo se a atribuição abaixo falhar
    try:
        logger.info("=" * 120)
        logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 📦 Dados recebidos: \n Pedido: {pedido}")
        # ============================================================================================
        # extrai dados da mensagem primeiro — necessário para o early-exit, independente da config do produto.
        # De propósito NÃO marcamos como lida nem mostramos "digitando": quando a IA escala (ex.: estorno) e
        # ninguém respondeu ainda, os tiques azuis faziam a cliente achar que estávamos ignorando o pedido.
        pedido_id = pedido['id']
        mensagem_cliente = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        # ============================================================================================
        # estado atual do pedido (não a foto do webhook); comprovante em análise → espera ele terminar
        pedido = _reler_pedido(pedido)
        if pedido.get('estado_id') == ESTADO_COMPROVANTE_EM_ANALISE and tentativa_espera < _MAX_TENTATIVAS_ESPERA:
            logger.info(f"[FLUXO-RESPONDER-MENSAGEM] ⏳ Pedido #{pedido_id} com comprovante em análise — "
                        f"reagendando em {_ESPERA_COMPROVANTE_S}s (tentativa {tentativa_espera + 1})")
            celery_app.send_task(
                "tasks.responder_mensagem",
                args=[pedido, mensagem_whatsapp],
                kwargs={"tentativa_espera": tentativa_espera + 1},
                countdown=_ESPERA_COMPROVANTE_S,
            )
            return
        # ============================================================================================
        # risco à vida: responde com o CVV mesmo com o pedido em análise pelo admin (que silencia a IA abaixo) e
        # grava a notificação mesmo havendo outra aberta (senão ela some atrás de um estorno, por exemplo)
        em_analise = tem_notificacao_em_analise(pedido_id)
        if em_analise and fala_em_risco_a_vida(mensagem_cliente):
            salvar_mensagem_pedido(message_id, pedido_id, mensagem_cliente, tipo_mensagem='recebida')
            if tem_notificacao_em_analise_por_motivo(pedido_id, 'risco_vida'):
                # já alertado e CVV já enviado: não repete a cada mensagem (cada envio é cobrado)
                logger.warning(f"[FLUXO-RESPONDER-MENSAGEM] 🆘 Pedido #{pedido_id}: risco à vida já em análise, "
                               f"mensagem salva sem repetir o CVV")
                return
            criar_notificacao_admin(pedido_id, pedido.get('produto_id'), 'risco_vida',
                                    f"Risco à vida (pedido já em análise): '{mensagem_cliente[:200]}'",
                                    mesmo_em_analise=True)
            logger.warning(f"[FLUXO-RESPONDER-MENSAGEM] 🆘 Pedido #{pedido_id}: risco à vida com pedido em análise — CVV")
            _agendar_resposta(pedido, MENSAGEM_RISCO_VIDA, pedido_id)
            return
        # ============================================================================================
        # se pedido já está em análise pelo admin, salva a mensagem e silencia a IA
        # (não precisa carregar produto nem histórico)
        if em_analise:
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
        # mensagem que não pede resposta (emoji, "obrigada", "segue o comprovante"): só salva, sem IA e sem
        # gastar mensagem do WhatsApp
        if mensagem_sem_resposta(mensagem_cliente, pedido_pago=pedido_esta_pago(pedido)):
            salvar_mensagem_pedido(message_id, pedido_id, mensagem_cliente, tipo_mensagem='recebida')
            logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 🔕 Pedido #{pedido_id}: mensagem não pede resposta, silenciada")
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
        decisao = responder_cliente_com_historico_produto(mensagem_cliente, historico, produto, pedido)
        acao = decisao['acao']
        logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] 🤖 Decisão: {decisao}")
        # ============================================================================================
        if acao == ACAO_PAGAMENTO_INFORMADO:
            _registrar_pagamento_informado(pedido, message_id, decisao.get('valor'))
            return
        # escalar (estorno, insatisfação... ou falha da OpenAI) e silenciar: sem resposta. Ao escalar, o agente
        # já criou a notificação para o admin. Risco à vida é a exceção: escala E responde (mensagem fixa).
        if acao not in (ACAO_RESPONDER, ACAO_RISCO_VIDA) or not decisao.get('texto'):
            logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 🔕 Pedido #{pedido_id}: {acao}, sem resposta ao cliente.")
            return
        _agendar_resposta(pedido, decisao['texto'], pedido_id)
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


def _agendar_resposta(pedido, resposta_cliente, pedido_id):
    """Agenda o envio com delay humanizado (worker liberado durante a espera)."""
    delay = random.uniform(5.0, 8.0)
    logger.debug(f"[FLUXO-RESPONDER-MENSAGEM] ⏳ Enviando resposta em {delay:.1f}s via task...")
    celery_app.send_task(
        "tasks.enviar_resposta_cliente",
        args=[pedido, resposta_cliente, pedido_id],
        countdown=delay,
    )


def _registrar_pagamento_informado(pedido, message_id, valor):
    """A cliente disse que já pagou: agenda o fluxo do comprovante sem arquivo. Não trava aqui: a task espera
    _ESPERA_PAGAMENTO_INFORMADO_S, relê o pedido e só trava se nenhuma imagem de comprovante chegou antes."""
    logger.info(f"[FLUXO-RESPONDER-MENSAGEM] 💬 Pedido #{pedido['id']}: pagamento informado (valor {valor}), "
                f"agendando o fluxo do comprovante em {_ESPERA_PAGAMENTO_INFORMADO_S}s")
    celery_app.send_task("tasks.confirmar_pagamento_informado", args=[pedido, message_id, valor],
                         countdown=_ESPERA_PAGAMENTO_INFORMADO_S)


def enviar_resposta(pedido, resposta_cliente, pedido_id):
    # Chip do gateway caído: levanta ChipForaDoArWhatsApp (transiente) e a task reagenda a mesma resposta
    # já gerada, sem gastar outra chamada à IA e sem tentar enviar contra um chip desconectado.
    exigir_numero_operacional(pedido)
    message_id_resposta = enviar_mensagem(pedido, resposta_cliente)
    salvar_mensagem_pedido(message_id_resposta, pedido_id, resposta_cliente, tipo_mensagem='enviada')
    logger.info(f"[FLUXO-RESPONDER-MENSAGEM] ✅ Resposta enviada ao cliente | pedido #{pedido_id}")
