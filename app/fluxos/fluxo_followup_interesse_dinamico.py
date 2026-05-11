import logging
from datetime import datetime
from database import (
    buscar_pedidos_followup_interesse_1, buscar_pedidos_followup_interesse_2,
    listar_acoes_fluxo, marcar_followup_interesse_1, marcar_followup_interesse_2,
)
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar

logger = logging.getLogger(__name__)

_TAG = "FLUXO-FOLLOWUP-INT"


def _executar_rodada(pedidos, nome_fluxo, marcar_fn):
    if not pedidos:
        logger.info(f"[{_TAG}] ℹ️ Nenhum pedido para {nome_fluxo}.")
        return

    logger.info(f"[{_TAG}] 📋 {len(pedidos)} pedido(s) para {nome_fluxo}.")

    for pedido in pedidos:
        try:
            pedido_id  = pedido['id']
            produto_id = pedido['produto_id']

            todas_acoes = listar_acoes_fluxo(produto_id, nome_fluxo)
            acoes = filtrar_e_ordenar(todas_acoes, ('sempre',))

            if not acoes:
                logger.warning(
                    f"[{_TAG}] ⚠️ Nenhuma ação configurada para '{nome_fluxo}' do produto {produto_id}. "
                    f"Pedido #{pedido_id} ignorado. Configure no admin em Fluxos."
                )
                continue

            # message_id_original=None: não há mensagem recebida neste fluxo.
            # Não configure ações marcar_lida/digitando no admin para estes fluxos.
            for acao in acoes:
                logger.debug(f"[{_TAG}] ▶ #{acao['ordem']} [{acao['acao']}]")
                executar_acao(acao, pedido, message_id_original=None, pedido_id=pedido_id, tag=_TAG)

            marcar_fn(pedido_id)
            logger.debug(f"[{_TAG}] ✅ {nome_fluxo} concluído para pedido #{pedido_id}.")

        except Exception as e:
            logger.error(f"[{_TAG}] ❌ Erro no pedido #{pedido['id']}: {e}", exc_info=True)
            continue


def executar():
    agora = datetime.now()
    logger.info("=" * 120)
    logger.info(f"[{_TAG}] 🕐 Iniciando followup de interesse: {agora.strftime('%H:%M')}")

    _executar_rodada(
        buscar_pedidos_followup_interesse_1(),
        'followup_interesse_1',
        marcar_followup_interesse_1,
    )
    _executar_rodada(
        buscar_pedidos_followup_interesse_2(),
        'followup_interesse_2',
        marcar_followup_interesse_2,
    )

    logger.info(f"[{_TAG}] ✅ Rotina de followup de interesse concluída.")
    logger.info("=" * 120)
