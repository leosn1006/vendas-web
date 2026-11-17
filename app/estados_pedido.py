"""
Estados de pagamento do pedido usados pelo WhatsApp (responder, agente de IA e fluxo do comprovante).
Módulo neutro (sem dependências) para a regra ficar num lugar só.
"""

# Trava do orquestrador enquanto um comprovante é processado (imagem, documento ou "já paguei" por texto).
ESTADO_COMPROVANTE_EM_ANALISE = 13

# Pedido do WhatsApp que já recebeu o link e ainda não pagou (3 = aguardando, 4 = follow-up enviado). Só nesses
# estados "já paguei" por texto vira pagamento. Pedidos do site (100x, ex.: contribuição 1008/1009) também chegam
# ao responder e não podem ir para o estado 0 do WhatsApp.
ESTADOS_AGUARDANDO_PAGAMENTO = (3, 4)

ESTADO_PAGO_WHATSAPP = 0
ESTADO_PAGO_WEB = 1000


def valor_pago(pedido: dict | None) -> float:
    try:
        return float((pedido or {}).get('valor_pago') or 0)
    except (TypeError, ValueError):
        return 0.0


def pedido_esta_pago(pedido: dict | None) -> bool:
    if not pedido:
        return False
    # mesma convenção do checkout (estado_id in (0, 1000)) + valor_pago, que cobre o pago que está em outro estado
    return pedido.get('estado_id') in (ESTADO_PAGO_WHATSAPP, ESTADO_PAGO_WEB) or valor_pago(pedido) > 0


def pode_informar_pagamento(pedido: dict | None) -> bool:
    """"Já paguei" por texto só vira pagamento em pedido do WhatsApp aguardando pagamento."""
    return (bool(pedido) and not pedido_esta_pago(pedido)
            and pedido.get('fluxo_inicial') != 'web'
            and pedido.get('estado_id') in ESTADOS_AGUARDANDO_PAGAMENTO)
