"""
Rotina de resiliência: verifica pedidos com cartão de crédito (Cielo) presos
em "aguardando autorização" (estado 1005) há mais de 5 minutos.
Chamada a cada 15 minutos pelo Celery Beat.
Toda regra de negócio está em web.checkout.reconciliar_cartao().
"""
import logging

logger = logging.getLogger(__name__)


def executar() -> None:
    import database as db
    from web.checkout import reconciliar_cartao

    pedidos = db.buscar_pedidos_aguardando_cartao_cielo()
    total = len(pedidos)
    confirmados = 0
    logger.info(f'[RESILIENCIA_CARTAO] {total} pedido(s) aguardando autorização Cielo')
    for pedido in pedidos:
        try:
            resultado = reconciliar_cartao(pedido['id'])
            if resultado.get('pago'):
                confirmados += 1
                logger.info(f'[RESILIENCIA_CARTAO] ✅ Pedido #{pedido["id"]} confirmado via sweep')
        except Exception as e:
            logger.error(f'[RESILIENCIA_CARTAO] ❌ Erro no pedido #{pedido["id"]}: {e}')
    logger.info(f'[RESILIENCIA_CARTAO] Resumo: {total} processado(s), {confirmados} confirmado(s)')
