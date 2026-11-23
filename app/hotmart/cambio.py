"""Valor da Hotmart (na moeda da cliente) → reais, para pedidos.valor_pago continuar sempre em reais.

Ordem: (1) já veio em BRL; (2) a conversão que a Hotmart mandou na nossa comissão (converted_value / value, quando a
comissão está na mesma moeda da compra); (3) cotação de referência: PTAX de venda do BCB (só 10 moedas: USD, EUR...)
ou, fora dela, a referência do BCE (MXN, INR; NGN não tem); (4) a última taxa gravada da mesma moeda;
(5) 'pendente' (valor 0 + ERROR no log). Quem chama nunca espera o câmbio para entregar.
"""
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

logger = logging.getLogger(__name__)

_CENTAVO = Decimal('0.01')


def taxa_para_brl(moeda: str | None, liquido, moeda_liquido: str | None, conversao: dict | None,
                  ptax: Callable[[str], dict | None], ultima_taxa: Callable[[str], Decimal | None]
                  ) -> tuple[Decimal | None, str]:
    """(reais por 1 unidade de `moeda`, fonte). Fonte: brl | hotmart | ptax | bce | ultima | pendente.
    Aviso sem preço (moeda vazia, ex.: um cancelamento) → (None, None): não sobrescreve a cotação já gravada."""
    if not moeda:
        return None, None
    if moeda == 'BRL':
        return Decimal('1'), 'brl'
    # A conversão da Hotmart vem na comissão: só serve se a comissão estiver na mesma moeda da compra.
    if conversao and moeda_liquido == moeda and liquido:
        try:
            if (conversao.get('converted_to_currency') or '').upper() == 'BRL':
                # A taxa que a Hotmart aplicou (reais por 1 unidade da moeda da comissão); sem ela, recalcula pelo
                # valor convertido (arredondado em centavos, por isso só como segunda opção).
                taxa = Decimal(str(conversao.get('conversion_rate') or 0))
                if taxa <= 0:
                    taxa = Decimal(str(conversao.get('converted_value'))) / Decimal(str(liquido))
                if taxa > 0:
                    return taxa.quantize(Decimal('0.000001')), 'hotmart'
        except Exception:
            pass
    cotacao = ptax(moeda)
    if cotacao and cotacao.get('valor'):
        return Decimal(str(cotacao['valor'])).quantize(Decimal('0.000001')), cotacao.get('fonte') or 'ptax'
    anterior = ultima_taxa(moeda)
    if anterior:
        return Decimal(str(anterior)), 'ultima'
    logger.error(f'[HOTMART] ❌ Sem cotação para {moeda}: valor em reais fica pendente')
    return None, 'pendente'


def em_reais(valor, taxa: Decimal | None) -> Decimal | None:
    if valor is None or taxa is None:
        return None
    return (Decimal(str(valor)) * taxa).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def liquido_em_reais(liquido, moeda_liquido: str | None, moeda: str | None, taxa: Decimal | None,
                     conversao: dict | None, ptax: Callable[[str], dict | None]) -> Decimal | None:
    """O nosso líquido em reais: já em BRL, a conversão da Hotmart, a taxa da compra (mesma moeda) ou a PTAX da moeda
    da comissão (ex.: comissão em USD numa compra em MXN)."""
    if liquido is None:
        return None
    if moeda_liquido in (None, 'BRL'):
        return Decimal(str(liquido)).quantize(_CENTAVO, rounding=ROUND_HALF_UP)
    if conversao and (conversao.get('converted_to_currency') or '').upper() == 'BRL':
        try:
            return Decimal(str(conversao.get('converted_value'))).quantize(_CENTAVO, rounding=ROUND_HALF_UP)
        except Exception:
            pass
    if moeda_liquido == moeda and taxa is not None:
        return em_reais(liquido, taxa)
    cotacao = ptax(moeda_liquido)
    if cotacao and cotacao.get('valor'):
        return em_reais(liquido, Decimal(str(cotacao['valor'])))
    return None
