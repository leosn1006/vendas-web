import logging
from database import (
    listar_acoes_fluxo, salvar_mensagem_pedido, atualizar_estado_pedido,
    atualizar_pedido_com_interesse_produto, atualizar_pedido_com_data_envio_pedido,
)
from agente_verifica_interesse import classificar_interesse_compra
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar, selecionar_variantes

logger = logging.getLogger(__name__)

_TAG = "FLUXO-PEDIDO-DIN"


def executar(pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[{_TAG}] 🎬 Iniciando fluxo dinâmico de pedido para pedido #{pedido.get('id')}")

        produto_id   = pedido['produto_id']
        pedido_id    = pedido['id']
        dados_msg    = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]
        message_id   = dados_msg['id']
        mensagem_txt = dados_msg.get('text', {}).get('body', '') or ''

        # Grava mensagem recebida
        salvar_mensagem_pedido(message_id, pedido_id, mensagem_txt, tipo_mensagem='recebida')

        # ── Classifica interesse do cliente (IA) ──────────────────────────────
        logger.debug(f"[{_TAG}] 🤖 Classificando interesse do cliente...")
        interesse_raw   = classificar_interesse_compra(mensagem_txt)
        interesse       = interesse_raw.strip().rstrip('.!?').lower() == 'sim'
        condicao_ativa  = 'interesse_sim' if interesse else 'interesse_nao'
        logger.debug(f"[{_TAG}] 🤖 Interesse: {interesse} → condicao='{condicao_ativa}' (IA: '{interesse_raw}')")

        # Persiste interesse no pedido
        atualizar_pedido_com_interesse_produto(pedido_id, interesse)

        # ── Monta sequência de execução ──────────────────────────────────────
        # Inclui ações 'sempre' + as ações da condição de interesse aplicável.
        # filtrar_e_ordenar devolve a lista ordenada por 'ordem'.
        todas_acoes = listar_acoes_fluxo(produto_id, 'pedido')
        acoes = filtrar_e_ordenar(todas_acoes, ('sempre', condicao_ativa))
        acoes = selecionar_variantes(acoes)

        if not acoes:
            raise ValueError(
                f"[{_TAG}] ❌ Nenhuma ação configurada para o fluxo 'pedido' "
                f"do produto {produto_id}. Configure no admin em Fluxos > Pedido."
            )

        logger.debug(f"[{_TAG}] 📋 {len(acoes)} ação(ões) na sequência ({condicao_ativa}).")

        # ── Executa cada ação em ordem ────────────────────────────────────────
        for acao in acoes:
            logger.debug(f"[{_TAG}] ▶ #{acao['ordem']} [{acao['acao']}] ({acao['condicao']})")
            executar_acao(acao, pedido, message_id, pedido_id, tag=_TAG)

        # ── Finaliza o pedido ─────────────────────────────────────────────────
        atualizar_estado_pedido(pedido_id, 3)
        atualizar_pedido_com_data_envio_pedido(pedido_id)
        logger.info(f"[{_TAG}] ✅ Fluxo concluído. Estado do pedido #{pedido_id} → 3.")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[{_TAG}] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc
