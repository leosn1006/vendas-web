"""
Cálculo de parcelamento com juros ByMerchant (o lojista, não a Cielo/emissor,
é quem embute o juro no valor cobrado — Payment.Interest sempre 'ByMerchant').
Módulo puro, sem I/O: usado tanto para popular o <select> do checkout quanto
para recalcular o valor real no servidor antes de chamar a Cielo.
"""


def calcular_total(valor_original: float, parcelas: int, parcelas_sem_juros: int,
                    taxa_juros_mensal: float) -> float:
    """Tabela Price. Sem juros se dentro do nº de parcelas livres ou taxa=0%."""
    # taxa_juros_mensal chega como decimal.Decimal quando vem direto de uma linha do banco
    # (coluna DECIMAL) — cast pra float aqui pra nunca misturar tipo com valor_original.
    taxa_juros_mensal = float(taxa_juros_mensal)
    if parcelas <= 1 or parcelas <= parcelas_sem_juros or taxa_juros_mensal <= 0:
        return round(valor_original, 2)
    i = taxa_juros_mensal / 100
    fator = (i * (1 + i) ** parcelas) / ((1 + i) ** parcelas - 1)  # fator de recuperação de capital = parcela/valor_original
    valor_parcela = valor_original * fator
    return round(valor_parcela * parcelas, 2)


def parcelas_maximas_efetivas(valor_original: float, max_parcelas: int) -> int:
    """min(teto de MDR configurado, valor_original // 5 — mínimo Cielo por parcela)."""
    teto_valor_minimo = max(1, int(valor_original // 5))
    return max(1, min(int(max_parcelas), teto_valor_minimo))


def gerar_opcoes_parcelamento(valor_original: float, config_cartao: dict) -> list[dict]:
    """[{parcelas, valor_parcela, valor_total, sem_juros}] para 1..parcelas_maximas_efetivas."""
    max_efetivo = parcelas_maximas_efetivas(valor_original, config_cartao['max_parcelas'])
    parcelas_sem_juros = config_cartao['parcelas_sem_juros']
    taxa = config_cartao['taxa_juros_mensal']

    opcoes = []
    for n in range(1, max_efetivo + 1):
        total = calcular_total(valor_original, n, parcelas_sem_juros, taxa)
        opcoes.append({
            'parcelas': n,
            'valor_parcela': round(total / n, 2),
            'valor_total': total,
            'sem_juros': n <= 1 or n <= parcelas_sem_juros,
        })
    return opcoes
