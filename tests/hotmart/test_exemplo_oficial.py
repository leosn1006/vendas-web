"""O JSON de exemplo do PURCHASE_APPROVED da documentação oficial (Hotmart Developers, "Eventos de pedidos" 2.0.0,
copiado em 21/11/2026; só tiramos as vírgulas sobrando, o PIX e os blocos de frete/FlexPay que não usamos)."""
import datetime
import json
import os
from decimal import Decimal

from hotmart import cambio, leitura

with open(os.path.join(os.path.dirname(__file__), 'exemplo_oficial_purchase_approved.json'), encoding='utf-8') as f:
    EXEMPLO = json.load(f)


def test_le_os_campos_do_exemplo_oficial():
    d = leitura.ler(EXEMPLO)
    assert (d['evento'], d['transacao'], d['xcod'], d['oferta']) == (
        'PURCHASE_APPROVED', 'HP02316330308193', 'xcod_example', 'n82b9jqz')
    assert (d['valor'], d['moeda'], d['valor_cheio']) == (Decimal('150.6'), 'BRL', Decimal('134.0'))
    assert (d['taxa_hotmart'], d['moeda_taxa']) == (Decimal('0.65'), 'BRL')
    assert (d['liquido'], d['moeda_liquido']) == (Decimal('3.1'), 'USD')
    assert d['conversao']['converted_value'] == 16.34
    assert (d['tipo_pagamento'], d['pais'], d['modelo_fiscal']) == ('PICPAY', 'BR', 'I')
    assert d['email'] == 'buyer@email.com' and d['nome'] == 'Buyer Name'
    assert d['garantia_ate'] == datetime.datetime(2017, 12, 26, 22, 0)   # 27/12 00:00 UTC = 26/12 22h em Brasília


def test_principal_com_a_mae_igual_a_ela_mesma_nao_e_bump():
    """No exemplo, is_order_bump = true e a mãe é a própria transação: é a compra principal."""
    assert leitura.ler(EXEMPLO)['order_bump'] is False


def test_liquido_em_dolar_usa_a_conversao_da_hotmart():
    d = leitura.ler(EXEMPLO)
    taxa, fonte = cambio.taxa_para_brl(d['moeda'], d['liquido'], d['moeda_liquido'], d['conversao'],
                                       lambda m: None, lambda m: None)
    assert (taxa, fonte) == (Decimal('1'), 'brl')
    assert cambio.liquido_em_reais(d['liquido'], d['moeda_liquido'], d['moeda'], taxa, d['conversao'],
                                   lambda m: None) == Decimal('16.34')


def test_compra_em_dolar_tira_a_taxa_da_conversao_da_hotmart():
    """Compra e comissão em USD (venda nos EUA): vale a conversion_rate da Hotmart; sem ela, 16,34 / 3,10."""
    conversao = EXEMPLO['data']['commissions'][1]['currency_conversion']
    taxa, fonte = cambio.taxa_para_brl('USD', Decimal('3.10'), 'USD', conversao, lambda m: None, lambda m: None)
    assert fonte == 'hotmart' and taxa == Decimal('5.271103')
    sem_taxa = {k: v for k, v in conversao.items() if k != 'conversion_rate'}
    taxa, _ = cambio.taxa_para_brl('USD', Decimal('3.10'), 'USD', sem_taxa, lambda m: None, lambda m: None)
    assert taxa == Decimal('5.270968')
