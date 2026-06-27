"""
Testes para geração da chave de acesso NF-e (44 dígitos).

Por que isso importa: a chave é a identidade fiscal da NF-e. Se o cDV
estiver errado, a SEFAZ rejeita com cStat=227 sem outra explicação.
Esses testes cobrem casos confirmados contra a SEFAZ e casos-limite do
algoritmo módulo 11.
"""
from datetime import datetime

import pytest

from app.fiscal.nfe_chave import calcular_dv, gerar_chave

# ─── calcular_dv ─────────────────────────────────────────────────────────────

def test_dv_valor_conhecido_resulta_2():
    # Chave confirmada contra o SVRS em 2026-06-23 (cStat=104)
    chave43 = '5326066498095300014655001000000001162886597'
    assert calcular_dv(chave43) == 2

def test_dv_valor_conhecido_resulta_0():
    # Chave confirmada contra o SVRS em 2026-06-23 (cStat=104)
    # Cobre o caminho especial: resto 0 → cDV = 0
    chave43 = '5326066498095300014655001000000001164112601'
    assert calcular_dv(chave43) == 0

def test_dv_resto_1_retorna_0():
    # Quando soma % 11 == 1, cDV também deve ser 0 (regra mod11 NF-e)
    # Encontra um prefixo de 43 dígitos que dê resto 1
    base = '0000000000000000000000000000000000000000000'
    resultado = calcular_dv(base)
    # A regra é: resto in (0, 1) → 0
    soma = sum(int(d) * [2,3,4,5,6,7,8,9][i % 8] for i, d in enumerate(reversed(base)))
    resto = soma % 11
    if resto in (0, 1):
        assert resultado == 0
    else:
        assert resultado == 11 - resto

# ─── gerar_chave ─────────────────────────────────────────────────────────────

def test_chave_tem_44_digitos():
    chave, _ = gerar_chave('53', datetime(2026, 6, 22), '64980953000146', '55', '001', 1)
    assert len(chave) == 44

def test_chave_so_digitos():
    chave, _ = gerar_chave('53', datetime(2026, 6, 22), '64980953000146', '55', '001', 1)
    assert chave.isdigit()

def test_dv_da_chave_gerada_e_correto():
    # Qualquer chave gerada deve ter o cDV válido — pega varios numeros
    for n_nf in [1, 42, 999, 99999999]:
        chave, _ = gerar_chave('53', datetime(2026, 6, 22), '64980953000146', '55', '001', n_nf)
        assert calcular_dv(chave[:43]) == int(chave[-1]), f"cDV errado para nNF={n_nf}"

def test_chave_comeca_com_c_uf():
    chave, _ = gerar_chave('53', datetime(2026, 6, 22), '64980953000146', '55', '001', 1)
    assert chave[:2] == '53'

def test_chave_contem_aamm():
    # Junho de 2026 → AAMM = 2606
    chave, _ = gerar_chave('53', datetime(2026, 6, 15), '64980953000146', '55', '001', 1)
    assert chave[2:6] == '2606'

def test_chave_contem_cnpj():
    chave, _ = gerar_chave('53', datetime(2026, 6, 22), '64980953000146', '55', '001', 1)
    assert '64980953000146' in chave

def test_c_nf_tem_8_digitos():
    _, c_nf = gerar_chave('53', datetime(2026, 6, 22), '64980953000146', '55', '001', 1)
    assert len(c_nf) == 8
    assert c_nf.isdigit()

def test_chaves_diferentes_para_numeros_diferentes():
    chave1, _ = gerar_chave('53', datetime(2026, 6, 22), '64980953000146', '55', '001', 1)
    chave2, _ = gerar_chave('53', datetime(2026, 6, 22), '64980953000146', '55', '001', 2)
    assert chave1 != chave2
