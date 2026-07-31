import logging
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from openai import OpenAI, RateLimitError, AuthenticationError, APIConnectionError, APITimeoutError

logger = logging.getLogger(__name__)
client = OpenAI()

# 1. Definir a estrutura de saída esperada utilizando Pydantic para Structured Outputs (OpenAI)
class TriagemResponse(BaseModel):
    decisao: Literal["BLOQUEAR", "HUMANO", "REACAO", "IGNORAR", "RESPONDER"] = Field(
        description="A decisão de ação para a última mensagem do cliente."
    )
    emoji_reacao: Optional[Literal["👍🏼", "🙏🏼"]] = Field(
        default=None,
        description="Se a decisão for REACAO, qual emoji de reação enviar. Caso contrário, nulo (null)."
    )
    motivo: str = Field(
        description="Breve justificativa técnica em português do porquê tomou essa decisão."
    )

def triar_conversa_whatsapp(historico_mensagens: List[dict], produto_entregue: bool) -> TriagemResponse:
    """
    Analisa as últimas mensagens trocadas com o cliente no WhatsApp para tomar uma decisão automatizada,
    visando reduzir custos com sessões pagas e otimizar o fluxo de atendimento.

    Args:
        historico_mensagens: Lista de dicionários no formato [{"role": "user"|"assistant", "content": "..."}]
        produto_entregue: True se o e-book (e bônus, quando houver) já foram enviados ao cliente nesta
            conversa. Em produção corresponde a `pedido['estado_id'] >= 3` ("Produto enviado"). Passar
            esse fato explicitamente evita que a IA precise adivinhar pelo texto se o ciclo de entrega
            já terminou — foi o que causou confusão entre IGNORAR e REACAO na validação inicial.
    """
    SYSTEM_PROMPT = (
        "Você é o Agente de Triagem e Classificação de Conversas do WhatsApp da nossa empresa de vendas de e-books.\n"
        "Sua única função é analisar o histórico das mensagens de uma conversa (últimas 10 mensagens) e decidir o que o sistema deve fazer com a última mensagem recebida do cliente (user).\n\n"
        f"CONTEXTO CONHECIDO: produto_entregue={produto_entregue} "
        f"({'o e-book já foi enviado ao cliente nesta conversa' if produto_entregue else 'o e-book ainda NÃO foi enviado ao cliente nesta conversa'}).\n\n"
        "Você deve classificar a conversa em uma das 5 categorias de decisão:\n\n"
        "1. BLOQUEAR\n"
        "Use se o cliente demonstrar claro desinteresse, rejeição ao produto ou irritação com o fluxo. O robô deve parar imediatamente para evitar denúncias de spam.\n"
        "Exemplos: 'Não', 'Nao', 'Não quero', 'Agora não', 'Isso é pressão', 'Chatice ficar cobrando', 'não pedi nada'.\n\n"
        "2. HUMANO\n"
        "Use se o cliente precisar de ajuda manual, suporte de pagamento, ou se houver problemas de acesso ou tecnologia que o robô de vendas não consiga resolver sozinho.\n"
        "Exemplos: 'não consigo abrir meu aplicativo do banco', 'minha conta foi bloqueada', 'já paguei e está cobrando de novo', ou idosos com extrema dificuldade que precisam de depósito na Caixa/Lotérica.\n\n"
        "3. REACAO\n"
        "Use para interações simples de agradecimento ou cortesias rápidas no meio da conversa (produto_entregue=False, "
        "ou o cliente ainda está no meio do processo de fechamento/pagamento), onde uma reação de emoji é suficiente "
        "para manter a simpatia sem estender a conversa e sem abrir uma nova janela de mensagem paga.\n"
        "Exemplos: 'Obrigada', 'De nada', 'Gratidão', 'Legal', ou emojis soltos.\n"
        "- Regra de emoji:\n"
        "  * Se a mensagem contiver termos de bênção ('Deus', 'Amém', 'fé', 'abençoe'), use '🙏🏼'.\n"
        "  * Para agradecimentos gerais, confirmações simples ou joinhas, use '👍🏼'.\n\n"
        "4. IGNORAR\n"
        "Use SOMENTE quando produto_entregue=True e a mensagem marca o encerramento absoluto da conversa por parte "
        "do cliente (agradecimento ou benção final pós-entrega). Qualquer resposta (ou mesmo uma reação) seria "
        "redundante, forçada ou causaria custos desnecessários. Se produto_entregue=False, NUNCA use IGNORAR — "
        "use REACAO no lugar.\n"
        "Exemplos (com produto_entregue=True): 'Muito obrigado!', 'Gratidão por tudo..boa sorte p nós !!🙌', 'Fique com Deus'.\n\n"
        "5. RESPONDER\n"
        "Use se o cliente estiver engajado, tiver dúvidas legítimas de culinária, preço, ingredientes ou se o fluxo de vendas normal precisar continuar de forma ativa.\n"
        "Exemplos: 'Qual o valor?', 'Tem pudim sem ovo?', 'Por quanto posso vender?', 'Quero sim, manda'."
    )

    try:
        # Chamada da API utilizando Structured Outputs garantidos por Pydantic
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *historico_mensagens
            ],
            response_format=TriagemResponse,
            temperature=0.0 # Temperatura zero garante consistência lógica máxima
        )
        return completion.choices[0].message.parsed
    except (RateLimitError, AuthenticationError, APIConnectionError, APITimeoutError) as exc:
        # Fallback de segurança para produção (caso ocorra erro de cota ou rede)
        logger.error(f"[TRIAGEM] ❌ Erro OpenAI ({type(exc).__name__}): {exc}")
        return TriagemResponse(
            decisao="HUMANO",
            emoji_reacao=None,
            motivo=f"Erro crítico na chamada da API OpenAI ({type(exc).__name__}). Encaminhado para o humano por segurança."
        )


def avaliar_casos(casos: List[dict]) -> None:
    """Roda a triagem sobre uma lista de casos de teste e imprime o resultado de cada um."""
    for caso in casos:
        resultado = triar_conversa_whatsapp(caso["historico"], caso["produto_entregue"])
        print(f"\n--- {caso['nome']} (produto_entregue={caso['produto_entregue']}) ---")
        for msg in caso["historico"]:
            print(f"  {msg['role']}: {msg['content']}")
        print(f"  => decisao={resultado.decisao} | emoji={resultado.emoji_reacao} | motivo={resultado.motivo}")


# --- Casos de teste para validação manual ---
CASOS_TESTE = [
    {
        "nome": "IGNORAR — pedido 216128 (fechamento após entrega concluída)",
        "produto_entregue": True,
        "historico": [
            {"role": "assistant", "content": "Suas receitinhas estão aqui! Aproveite muito! 🍮💛"},
            {"role": "user", "content": "Muito, obrigada. Deus abençoe!"},
            {"role": "assistant", "content": "De nada! Fico muito feliz... Deus te abençoe! 🙏✨"},
            {"role": "user", "content": "Assim que puder farei mais um Pix p você 🙏🏼"},
            {"role": "assistant", "content": "Fico muito grata, meu bem!..."},
            {"role": "user", "content": "🙏🏼"},
        ],
    },
    {
        "nome": "REACAO — cortesia curta antes do fechamento (produto ainda não entregue)",
        "produto_entregue": False,
        "historico": [
            {"role": "assistant", "content": "Perfeito! Você pode fazer o Pix na chave abaixo pra garantir seu acesso."},
            {"role": "user", "content": "Joinha, já vou fazer"},
        ],
    },
    {
        "nome": "REACAO — mesma bênção do caso IGNORAR, mas ANTES da entrega (teste de regressão)",
        "produto_entregue": False,
        "historico": [
            {"role": "assistant", "content": "Vou te enviar o e-book assim que confirmar o Pix, tudo bem?"},
            {"role": "user", "content": "Muito, obrigada. Deus abençoe!"},
        ],
    },
    {
        "nome": "BLOQUEAR — desinteresse/pressão de venda",
        "produto_entregue": False,
        "historico": [
            {"role": "assistant", "content": "Oi! Vi que você se interessou pelo nosso e-book, posso te ajudar?"},
            {"role": "user", "content": "Não quero mais, para de mandar mensagem"},
        ],
    },
    {
        "nome": "HUMANO — dificuldade técnica de pagamento",
        "produto_entregue": False,
        "historico": [
            {"role": "assistant", "content": "Você pode pagar via Pix escaneando o QR code que te enviei."},
            {"role": "user", "content": "não consigo abrir meu aplicativo do banco pra pagar"},
        ],
    },
    {
        "nome": "RESPONDER — dúvida legítima de produto",
        "produto_entregue": False,
        "historico": [
            {"role": "user", "content": "Tem pudim sem ovo?"},
        ],
    },
]

if __name__ == "__main__":
    # Nota: para rodar de verdade, configure a variável de ambiente OPENAI_API_KEY.
    avaliar_casos(CASOS_TESTE)
