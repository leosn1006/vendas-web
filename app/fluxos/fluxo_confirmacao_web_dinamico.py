import logging
from database import get_pedido, listar_acoes_fluxo, marcar_ebook_enviado
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar, selecionar_variantes

logger = logging.getLogger(__name__)

_TAG = "FLUXO-CONFIRMACAO-WEB"


def executar(pedido_id: int):
    """
    Envia o ebook via WhatsApp após pagamento confirmado no checkout web.

    Lê as ações configuradas em acoes_fluxo_produto (fluxo='confirmacao_web')
    e executa cada uma usando o mesmo engine dos outros fluxos dinâmicos.
    Não altera o estado do pedido (já está em 1000).
    Não usa marcar_lida pois não há mensagem de entrada.
    Ao final, preenche data_envio_ebook no banco.
    """
    pedido = get_pedido(pedido_id)
    if not pedido:
        logger.error(f"[{_TAG}] ❌ Pedido #{pedido_id} não encontrado.")
        return

    produto_id = pedido['produto_id']

    logger.info("=" * 120)
    logger.info(f"[{_TAG}] 🛒 Iniciando entrega web para pedido #{pedido_id} "
                f"(produto {produto_id}, WhatsApp: {pedido.get('contact_phone')})")

    todas_acoes = listar_acoes_fluxo(produto_id, 'confirmacao_web')
    acoes = filtrar_e_ordenar(todas_acoes, ('sempre',))
    acoes = selecionar_variantes(acoes)

    if not acoes:
        logger.warning(
            f"[{_TAG}] ⚠️ Nenhuma ação configurada para 'confirmacao_web' do produto {produto_id}. "
            f"Pedido #{pedido_id} sem entrega. Configure no admin em Fluxos > Confirmação Web."
        )
        logger.info("=" * 120)
        return

    logger.debug(f"[{_TAG}] 📋 {len(acoes)} ação(ões) para pedido #{pedido_id}.")

    for acao in acoes:
        logger.debug(f"[{_TAG}] ▶ #{acao['ordem']} [{acao['acao']}]")
        executar_acao(acao, pedido, message_id_original=None, pedido_id=pedido_id, tag=_TAG)

    marcar_ebook_enviado(pedido_id)
    logger.info(f"[{_TAG}] ✅ Entrega concluída para pedido #{pedido_id}.")
    logger.info("=" * 120)
