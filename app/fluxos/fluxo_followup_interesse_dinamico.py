import logging
from datetime import datetime
from database import (
    buscar_pedidos_followup_interesse_1, buscar_pedidos_followup_interesse_2,
    listar_acoes_fluxo, marcar_followup_interesse_1, marcar_followup_interesse_2,
)
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar, selecionar_variantes
from whatsapp import ChipForaDoArWhatsApp

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
            acoes = selecionar_variantes(acoes)

            if not acoes:
                logger.warning(
                    f"[{_TAG}] ⚠️ Nenhuma ação configurada para '{nome_fluxo}' do produto {produto_id}. "
                    f"Pedido #{pedido_id} ignorado. Configure no admin em Fluxos."
                )
                continue

            # message_id_original=None: não há mensagem recebida neste fluxo.
            # Não configure ações marcar_lida/digitando no admin para estes fluxos.
            enviadas = 0
            for acao in acoes:
                logger.debug(f"[{_TAG}] ▶ #{acao['ordem']} [{acao['acao']}]")
                try:
                    executar_acao(acao, pedido, message_id_original=None, pedido_id=pedido_id, tag=_TAG)
                except ChipForaDoArWhatsApp:
                    if enviadas == 0:
                        raise  # nada saiu: adia o pedido (tratado abaixo), segue elegível
                    # Repetir depois reenviaria as ações que já saíram (spam, risco de ban): dá como concluído.
                    logger.error(
                        f"[{_TAG}] ⚠️ Chip caiu após {enviadas}/{len(acoes)} ação(ões) do {nome_fluxo} do pedido "
                        f"#{pedido_id}; as restantes foram descartadas para não duplicar o que já foi enviado."
                    )
                    break
                enviadas += 1

            marcar_fn(pedido_id)
            logger.debug(f"[{_TAG}] ✅ {nome_fluxo} concluído para pedido #{pedido_id}.")

        except ChipForaDoArWhatsApp as e:
            # Situação esperada (chip caído): aviso curto, sem traceback. O pedido sai da fila sozinho
            # quando passa da janela de 24h (JANELA_FOLLOWUP_HORAS nas buscas).
            logger.warning(f"[{_TAG}] ⏸️ {e}")
            continue
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
