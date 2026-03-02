import logging
from datetime import datetime
from database import (
    buscar_pedidos_followup, listar_acoes_fluxo,
    atualizar_estado_pedido, atualizar_pedido_com_data_followup,
)
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar

logger = logging.getLogger(__name__)

_TAG = "FLUXO-FOLLOWUP-DIN"


def executar():
    agora = datetime.now()
    logger.info("=" * 120)
    logger.info(f"[{_TAG}] 🕐 Iniciando verificação de followup: {agora.strftime('%H:%M')}")

    pedidos = buscar_pedidos_followup(horas_sem_atualizacao=4)

    if not pedidos:
        logger.info(f"[{_TAG}] ℹ️ Nenhum pedido pendente de followup.")
        logger.info("=" * 120)
        return

    logger.info(f"[{_TAG}] 📋 {len(pedidos)} pedido(s) para followup.")

    for pedido in pedidos:
        try:
            pedido_id  = pedido['id']
            produto_id = pedido['produto_id']
            condicao_ativa = 'interesse_sim' if pedido.get('interesse_produto') else 'interesse_nao'

            logger.debug(f"[{_TAG}] 📱 Pedido #{pedido_id} → condicao='{condicao_ativa}'")

            todas_acoes = listar_acoes_fluxo(produto_id, 'followup')
            acoes = filtrar_e_ordenar(todas_acoes, ('sempre', condicao_ativa))

            if not acoes:
                logger.warning(
                    f"[{_TAG}] ⚠️ Nenhuma ação configurada para 'followup' do produto {produto_id}. "
                    f"Pedido #{pedido_id} ignorado. Configure no admin em Fluxos > Followup."
                )
                continue

            logger.debug(f"[{_TAG}] 📋 {len(acoes)} ação(ões) para pedido #{pedido_id}.")

            # message_id_original é None no followup (sem mensagem recebida)
            # Não configure ações marcar_lida/digitando neste fluxo
            for acao in acoes:
                logger.debug(f"[{_TAG}] ▶ #{acao['ordem']} [{acao['acao']}] ({acao['condicao']})")
                executar_acao(acao, pedido, message_id_original=None, pedido_id=pedido_id, tag=_TAG)

            atualizar_estado_pedido(pedido_id, 4)
            atualizar_pedido_com_data_followup(pedido_id)
            logger.debug(f"[{_TAG}] ✅ Followup concluído para pedido #{pedido_id} → estado 4.")

        except Exception as e:
            logger.error(f"[{_TAG}] ❌ Erro no pedido #{pedido['id']}: {e}")
            raise

    logger.info(f"[{_TAG}] ✅ Rotina de followup concluída.")
    logger.info("=" * 120)
