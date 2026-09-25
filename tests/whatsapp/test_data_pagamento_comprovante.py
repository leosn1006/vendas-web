"""
Data de pagamento lida do comprovante pela IA.

Bug em produção: a IA lê comprovantes brasileiros (dd/mm) e às vezes devolve o dia e o mês invertidos
(11/05 -> 2026-11-05). O código só exigia data POSTERIOR ao contato, então a data futura passava:
51 pedidos com data_pagamento entre out e dez/2026. Os casos abaixo são pedidos reais.
"""
from datetime import datetime

import pytest

from fluxos.fluxo_comprovante_dinamico import _resolver_data_pagamento, _trocar_dia_e_mes

AGORA = datetime(2026, 9, 24, 20, 0, 0)


def resolver(ia, contato):
    return _resolver_data_pagamento(ia, contato, agora=AGORA)


# ─── dia e mês invertidos (casos reais de produção) ──────────────────────────

@pytest.mark.parametrize('pedido,contato,ia,esperado', [
    (34013,  '2026-05-11 02:03:25', '2026-11-05 02:10:26', datetime(2026, 5, 11, 2, 10, 26)),   # 7 min após o contato
    (5844,   '2026-04-10 15:37:09', '2026-10-04 16:10:13', datetime(2026, 4, 10, 16, 10, 13)),
    (175289, '2026-07-12 04:30:28', '2026-12-07 08:46:00', datetime(2026, 7, 12, 8, 46, 0)),
    (321095, '2026-09-12 10:16:35', '2026-12-09 10:24:18', datetime(2026, 9, 12, 10, 24, 18)),
    (310555, '2026-09-08 21:59:47', '2026-10-09 09:03:31', datetime(2026, 9, 10, 9, 3, 31)),
])
def test_data_futura_com_dia_e_mes_invertidos_e_corrigida(pedido, contato, ia, esperado):
    assert resolver(ia, contato) == esperado


def test_data_futura_que_nao_e_troca_usa_agora():
    """Pedido 267554: dia 26 não pode ser mês. Sem troca possível, não inventa data: usa o momento atual."""
    assert resolver('2026-10-26 14:38:48', '2026-08-22 11:03:35') == AGORA


def test_pix_agendado_para_o_futuro_usa_agora():
    """Pedido 285502: 30/09 com hoje 24/09 (dia > 12: não é troca). O flow marca como pago 'agora'."""
    assert resolver('2026-09-30 15:25:59', '2026-08-30 16:09:40') == AGORA


def test_troca_que_cairia_antes_do_contato_nao_e_aceita():
    """A trocada (2026-05-11) seria anterior ao contato (20/09): implausível, então usa agora."""
    assert resolver('2026-11-05 10:00:00', '2026-09-20 09:00:00') == AGORA


def test_data_futura_sem_referencia_de_contato_tambem_e_tratada():
    """Antes, sem data_contato_site o valor da IA era usado como veio, mesmo no futuro."""
    assert resolver('2026-11-05 10:00:00', None) == datetime(2026, 5, 11, 10, 0, 0)
    assert resolver('2026-10-26 10:00:00', None) == AGORA


# ─── comportamento que NÃO pode mudar ────────────────────────────────────────

def test_data_normal_no_passado_e_depois_do_contato_e_mantida():
    assert resolver('2026-09-23 10:53:13', '2026-09-23 09:00:00') == datetime(2026, 9, 23, 10, 53, 13)


def test_data_so_com_dia_e_aceita():
    assert resolver('2026-09-24', '2026-09-23 09:00:00') == datetime(2026, 9, 24, 0, 0, 0)


def test_data_anterior_ao_contato_usa_agora():
    assert resolver('2026-09-01 10:00:00', '2026-09-23 09:00:00') == AGORA


@pytest.mark.parametrize('ia', [None, '', 'ontem', '24/09/2026', '2026-13-45'])
def test_data_ausente_ou_invalida_usa_agora(ia):
    assert resolver(ia, '2026-09-23 09:00:00') == AGORA


def test_relogio_do_servidor_ligeiramente_atrasado_nao_vira_futuro():
    """Comprovante 3 min 'à frente' do relógio do servidor é normal, não pode acionar a troca."""
    assert resolver('2026-09-24 20:03:00', '2026-09-24 19:00:00') == datetime(2026, 9, 24, 20, 3, 0)


def test_contato_como_datetime_tambem_funciona():
    assert resolver('2026-11-05 02:10:26', datetime(2026, 5, 11, 2, 3, 25)) == datetime(2026, 5, 11, 2, 10, 26)


# ─── auxiliar ────────────────────────────────────────────────────────────────

def test_trocar_dia_e_mes():
    assert _trocar_dia_e_mes(datetime(2026, 11, 5, 2, 10, 26)) == datetime(2026, 5, 11, 2, 10, 26)
    assert _trocar_dia_e_mes(datetime(2026, 12, 12)) == datetime(2026, 12, 12)  # simétrica: dia == mês
    assert _trocar_dia_e_mes(datetime(2026, 10, 26)) is None                    # dia 26 não é mês
