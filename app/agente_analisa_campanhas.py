import logging
from openai import OpenAI, RateLimitError, APIConnectionError, APITimeoutError

logger = logging.getLogger(__name__)
client = OpenAI()

_SYSTEM_PROMPT = """Você é um especialista em marketing digital para negócios brasileiros que vendem via WhatsApp.
O funil analisado tem estas etapas sequenciais:
1. Impressões — quantas pessoas viram o anúncio no YouTube
2. Cliques (CTR) — clicaram no criativo
3. Visitantes / Landing — chegaram à página preseller
4. WhatsApp / Engaj — enviaram mensagem no WhatsApp
5. Responderam / Resp — responderam se têm interesse ou não
6. Pagamentos / Conv — efetivamente pagaram

Métricas financeiras:
- ROAS = Receita / Investido (acima de 3× é excelente; abaixo de 1× é prejuízo)
- CPA = Investido / Pagamentos (custo por venda)
- CPM = Custo por mil impressões

Seu tom é direto, profissional e didático. Escreva em português brasileiro.
Organize a resposta em seções com emojis: Resumo, Análise por Campanha, Comparativo, Gargalos e Insights."""


def analisar(produto_nome: str, periodo: str, campanhas: list[dict]) -> str:
    """
    Recebe lista de campanhas com dados completos e retorna análise textual.
    Cada campanha é um dict com: campanha, impressoes, ctr, cliques, landing_pct,
    visitantes, engaj_pct, whatsapp, resp_pct, responderam, conv_pct, pagaram,
    valor_investido, cpm, receita, roas, cpa.
    """
    if not campanhas:
        return "Nenhuma campanha com dados completos para analisar no período."

    linhas = []
    for c in campanhas:
        cpm_str = ("R$ " + f"{c['cpm']:.2f}") if c.get('cpm') else '—'
        cpa_str = ("R$ " + f"{c['cpa']:.2f}") if c.get('cpa') else '—'
        linha = (
            f"Campanha: {c['campanha']}\n"
            f"  Impressões: {c.get('impressoes', 0):,} | CTR: {c.get('ctr') or '—'}%\n"
            f"  Cliques: {c.get('cliques', 0):,} | Landing: {c.get('landing_pct') or '—'}%\n"
            f"  Visitantes: {c.get('visitantes', 0):,} | Engaj: {c.get('engaj_pct') or '—'}%\n"
            f"  WhatsApp: {c.get('whatsapp', 0):,} | Resp: {c.get('resp_pct') or '—'}%\n"
            f"  Responderam: {c.get('responderam', 0):,} | Conv: {c.get('conv_pct') or '—'}%\n"
            f"  Pagamentos: {c.get('pagaram', 0):,}\n"
            f"  Investido: R$ {c.get('valor_investido', 0):.2f} | CPM: {cpm_str}\n"
            f"  Receita: R$ {c.get('receita', 0):.2f} | ROAS: {c.get('roas') or '—'} | CPA: {cpa_str}"
        )
        linhas.append(linha)

    dados_texto = "\n\n".join(linhas)

    user_message = (
        f"Produto: {produto_nome}\n"
        f"Período: {periodo}\n"
        f"Número de campanhas: {len(campanhas)}\n\n"
        f"=== DADOS DAS CAMPANHAS ===\n\n"
        f"{dados_texto}\n\n"
        f"Faça uma análise estratégica completa dessas campanhas. "
        f"Compare as campanhas entre si, identifique qual etapa do funil está sendo o maior gargalo "
        f"em cada uma, e dê sugestões práticas de melhoria."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=2000,
            temperature=0.4,
        )
        return response.choices[0].message.content or "O agente não retornou análise."
    except RateLimitError:
        logger.warning("[AGENTE_CAMPANHAS] Rate limit OpenAI")
        return "Limite de requisições da OpenAI atingido. Tente novamente em alguns instantes."
    except (APIConnectionError, APITimeoutError) as e:
        logger.error(f"[AGENTE_CAMPANHAS] Conexão OpenAI: {e}")
        return "Erro de conexão com a OpenAI. Verifique sua conexão e tente novamente."
    except Exception as e:
        logger.error(f"[AGENTE_CAMPANHAS] Erro inesperado: {e}")
        return f"Erro ao gerar análise: {e}"
