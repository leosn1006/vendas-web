import random
from datetime import datetime


def calcular_dv(chave43: str) -> int:
    """
    Calcula o dígito verificador (cDV) pelo módulo 11.
    Pesos: 2..9 ciclicamente da direita para a esquerda.
    Resto 0 ou 1 → cDV = 0.
    """
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(chave43)))
    resto = soma % 11
    return 0 if resto in (0, 1) else 11 - resto


def gerar_chave(
    c_uf: str,
    data_emissao: datetime,
    cnpj: str,
    mod: str,
    serie: str,
    n_nf: int,
    tp_emis: str = '1',
) -> tuple[str, str]:
    """
    Gera a chave de acesso (44 dígitos) e o cNF (8 dígitos aleatórios).

    Formato: cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nNF(9) tpEmis(1) cNF(8) cDV(1)

    Retorna (chave44, c_nf).
    """
    aamm  = data_emissao.strftime('%y%m')
    cnpj_digits = ''.join(filter(str.isdigit, cnpj)).zfill(14)
    mod_fmt  = mod.zfill(2)
    serie_fmt = serie.zfill(3)
    nnf_fmt  = str(n_nf).zfill(9)
    c_nf     = str(random.randint(10000000, 99999999))

    chave43 = f'{c_uf}{aamm}{cnpj_digits}{mod_fmt}{serie_fmt}{nnf_fmt}{tp_emis}{c_nf}'
    dv = calcular_dv(chave43)
    chave44 = chave43 + str(dv)
    return chave44, c_nf
