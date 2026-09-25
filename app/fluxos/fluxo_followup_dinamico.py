import logging
from datetime import datetime
from database import (
    buscar_pedidos_followup, listar_acoes_fluxo, get_pedido,
    atualizar_estado_pedido_se, atualizar_pedido_com_data_followup,
)
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar, selecionar_variantes
from whatsapp import ChipForaDoArWhatsApp

logger = logging.getLogger(__name__)

_TAG = "FLUXO-FOLLOWUP-DIN"


def executar():
    agora = datetime.now()
    logger.info("=" * 120)
    logger.info(f"[{_TAG}] 🕐 Iniciando verificação de followup: {agora.strftime('%H:%M')}")

    pedidos = buscar_pedidos_followup(horas_sem_atualizacao=2)

    if not pedidos:
        logger.info(f"[{_TAG}] ℹ️ Nenhum pedido pendente de followup.")
        logger.info("=" * 120)
        return

    logger.info(f"[{_TAG}] 📋 {len(pedidos)} pedido(s) para followup.")

    for pedido in pedidos:
        try:
            pedido_id  = pedido['id']
            produto_id = pedido['produto_id']

            # A lista foi lida no início do lote e as ações têm delay: o cliente pode ter pago (ou mandado
            # comprovante) enquanto os pedidos anteriores eram processados. Não cobra quem já saiu do 3.
            atual = get_pedido(pedido_id)
            if not atual or atual['estado_id'] != 3:
                logger.info(f"[{_TAG}] ⏭️ Pedido #{pedido_id} saiu do estado 3 durante o lote; followup não enviado.")
                continue
            condicao_ativa = 'interesse_sim' if pedido.get('interesse_produto') else 'interesse_nao'

            logger.debug(f"[{_TAG}] 📱 Pedido #{pedido_id} → condicao='{condicao_ativa}'")

            todas_acoes = listar_acoes_fluxo(produto_id, 'followup')
            acoes = filtrar_e_ordenar(todas_acoes, ('sempre', condicao_ativa))
            acoes = selecionar_variantes(acoes)

            if not acoes:
                logger.warning(
                    f"[{_TAG}] ⚠️ Nenhuma ação configurada para 'followup' do produto {produto_id}. "
                    f"Pedido #{pedido_id} ignorado. Configure no admin em Fluxos > Followup."
                )
                continue

            logger.debug(f"[{_TAG}] 📋 {len(acoes)} ação(ões) para pedido #{pedido_id}.")

            # message_id_original é None no followup (sem mensagem recebida)
            # Não configure ações marcar_lida/digitando neste fluxo
            enviadas = 0
            for acao in acoes:
                # Cada ação tem delay: se o comprovante chegou durante o anterior, para de cobrar.
                if enviadas and (get_pedido(pedido_id) or {}).get('estado_id') != 3:
                    logger.info(
                        f"[{_TAG}] ⏭️ Pedido #{pedido_id} saiu do estado 3 após {enviadas}/{len(acoes)} ação(ões); "
                        f"restantes não enviadas."
                    )
                    break
                logger.debug(f"[{_TAG}] ▶ #{acao['ordem']} [{acao['acao']}] ({acao['condicao']})")
                try:
                    executar_acao(acao, pedido, message_id_original=None, pedido_id=pedido_id, tag=_TAG)
                except ChipForaDoArWhatsApp:
                    if enviadas == 0:
                        raise  # nada saiu: adia o pedido inteiro (tratado abaixo), segue elegível
                    # O chip caiu no meio da sequência. Repetir o followup depois reenviaria as ações que já
                    # saíram (spam para o cliente, risco de ban), então o followup é dado como concluído.
                    logger.error(
                        f"[{_TAG}] ⚠️ Chip caiu após {enviadas}/{len(acoes)} ação(ões) do followup do pedido "
                        f"#{pedido_id}; as restantes foram descartadas para não duplicar o que já foi enviado."
                    )
                    break
                enviadas += 1

            atualizar_pedido_com_data_followup(pedido_id)
            # Só avança se ainda estiver em 3: se pagou durante as ações, o 0 (ou o 13) não pode virar 4.
            if atualizar_estado_pedido_se(pedido_id, 3, 4):
                logger.debug(f"[{_TAG}] ✅ Followup concluído para pedido #{pedido_id} → estado 4.")
            else:
                logger.info(f"[{_TAG}] ⏭️ Pedido #{pedido_id} mudou de estado durante o followup; estado mantido.")

        except ChipForaDoArWhatsApp as e:
            # Chip do gateway caído ANTES de enviar qualquer ação: adia só este pedido (segue elegível na próxima
            # rodada) em vez de abortar o lote.
            logger.warning(f"[{_TAG}] ⏸️ {e}")
            continue
        except Exception as e:
            logger.error(f"[{_TAG}] ❌ Erro no pedido #{pedido['id']}: {e}")
            raise

    logger.info(f"[{_TAG}] ✅ Rotina de followup concluída.")
    logger.info("=" * 120)
