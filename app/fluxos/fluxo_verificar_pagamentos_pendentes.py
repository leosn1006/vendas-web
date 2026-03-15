"""
Rotina de resiliência: verifica pagamentos BB Pay pendentes (estado 1002).
Chamada a cada 10 minutos pelo Celery Beat.
Toda regra de negócio está em web.checkout.verificar_pagamento().
"""
import logging

logger = logging.getLogger(__name__)


def executar() -> None:
    import database as db
    from web.checkout import verificar_pagamento

    pedidos = db.buscar_pedidos_aguardando_bb_pay()
    total = len(pedidos)
    confirmados = 0
    logger.info(f'[RESILIENCIA_PGTO] {total} pedido(s) aguardando BB Pay')
    for pedido in pedidos:
        txid = str(pedido['numero_solicitacao_bb'])
        try:
            resultado = verificar_pagamento(txid)
            if resultado.get('pago'):
                confirmados += 1
                logger.info(f'[RESILIENCIA_PGTO] ✅ Pedido #{pedido["id"]} confirmado via sweep')
        except Exception as e:
            logger.error(f'[RESILIENCIA_PGTO] ❌ Erro no pedido #{pedido["id"]}: {e}')
    logger.info(f'[RESILIENCIA_PGTO] Resumo: {total} processado(s), {confirmados} confirmado(s)')
