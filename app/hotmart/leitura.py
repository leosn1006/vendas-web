"""Lê o aviso da Hotmart (webhook 2.0.0) e devolve só o que usamos, num dict plano.

Campos conferidos com a página oficial "Eventos de pedidos" 2.0.0 do Hotmart Developers (21/11/2026). Ainda falta ver
um aviso real (em que moeda vem a nossa comissão, se vem a do MARKETPLACE): ele fica inteiro em
pagamento_hotmart_eventos.payload. Campo ausente vira None — nunca exceção.
"""
import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

_FUSO_BANCO = ZoneInfo('America/Sao_Paulo')   # o banco guarda datas no horário de Brasília


def _d(obj, *caminho):
    for chave in caminho:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(chave)
    return obj


def _dinheiro(campo) -> tuple[Decimal | None, str | None]:
    if not isinstance(campo, dict):
        return None, None
    try:
        valor = Decimal(str(campo.get('value'))) if campo.get('value') is not None else None
    except (InvalidOperation, ValueError):
        valor = None
    moeda = (campo.get('currency_value') or '').upper() or None
    return valor, moeda


def _de_milissegundos(ms) -> datetime.datetime | None:
    try:
        utc = datetime.datetime.fromtimestamp(int(ms) / 1000, tz=datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return utc.astimezone(_FUSO_BANCO).replace(tzinfo=None)


def _de_iso(texto) -> datetime.datetime | None:
    try:
        data = datetime.datetime.fromisoformat(str(texto).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return data.astimezone(_FUSO_BANCO).replace(tzinfo=None) if data.tzinfo else data


def _comissao(comissoes, fonte: str) -> dict | None:
    for c in comissoes if isinstance(comissoes, list) else []:
        if isinstance(c, dict) and (c.get('source') or '').upper() == fonte:
            return c
    return None


def ler(payload: dict) -> dict:
    data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
    compra = data.get('purchase') if isinstance(data.get('purchase'), dict) else {}

    valor, moeda = _dinheiro(compra.get('price'))
    valor_cheio, _ = _dinheiro(compra.get('full_price'))
    taxa = _comissao(data.get('commissions'), 'MARKETPLACE')
    nosso = _comissao(data.get('commissions'), 'PRODUCER')
    taxa_hotmart, moeda_taxa = _dinheiro({'value': (taxa or {}).get('value'),
                                          'currency_value': (taxa or {}).get('currency_value')})
    liquido, moeda_liquido = _dinheiro({'value': (nosso or {}).get('value'),
                                        'currency_value': (nosso or {}).get('currency_value')})
    conversao = (nosso or {}).get('currency_conversion')

    pais = (_d(compra, 'checkout_country', 'iso') or _d(data, 'buyer', 'address', 'country_iso') or '')[:2]
    return {
        'evento_id': str(payload.get('id') or '') or None,
        'evento': (payload.get('event') or '').upper() or None,
        'criado_ms': payload.get('creation_date'),
        'transacao': compra.get('transaction') or None,
        'status': (compra.get('status') or '').upper() or None,
        'xcod': (_d(compra, 'origin', 'xcod') or '').strip() or None,
        'oferta': _d(compra, 'offer', 'code') or _d(data, 'offer', 'code') or None,
        'produto_id_hotmart': _d(data, 'product', 'id'),
        'tipo_pagamento': (_d(compra, 'payment', 'type') or '').upper() or None,
        'pais': pais.upper() or None,
        'email': (_d(data, 'buyer', 'email') or '').strip() or None,
        'nome': (_d(data, 'buyer', 'name') or '').strip(),
        'valor': valor, 'moeda': moeda, 'valor_cheio': valor_cheio,
        'taxa_hotmart': taxa_hotmart, 'moeda_taxa': moeda_taxa,
        'liquido': liquido, 'moeda_liquido': moeda_liquido,
        'conversao': conversao if isinstance(conversao, dict) else None,
        # Doc oficial: numa compra com bump, a PRINCIPAL também vem com is_order_bump = true, com o
        # parent_purchase_transaction vazio ("a própria compra é a pai") — e no JSON de exemplo, igual à própria
        # transação. Só é bump de verdade quando a mãe é OUTRA transação.
        'order_bump': bool(_d(compra, 'order_bump', 'is_order_bump'))
        and (_d(compra, 'order_bump', 'parent_purchase_transaction') or compra.get('transaction'))
        != compra.get('transaction'),
        'transacao_principal': _d(compra, 'order_bump', 'parent_purchase_transaction') or None,
        'nota_fiscal_por': (compra.get('invoice_by') or '').upper()[:10] or None,   # HOTMART | SELLER
        'modelo_fiscal': (compra.get('business_model') or '').upper()[:1] or None,  # R | A | I
        'aprovado_em': _de_milissegundos(compra.get('approved_date')),
        'garantia_ate': _de_iso(_d(data, 'product', 'warranty_date')),
    }
