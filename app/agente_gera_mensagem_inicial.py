from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

client = OpenAI()

#conectar ao llm
def gera_mensagem_inicial(produto):
    prompt_produto = ""
    prompt_nome_produto = ""
    prompt_publico_alvo = ""
    if produto == 1:
        prompt_publico_alvo = "mulheres geralmente maiores de 30 anos"
        prompt_nome_produto = "e-book de receitas sem glúten"
        prompt_produto = "O produto é um e-book de receitas sem glúten com 50 receitas deliciosas e fáceis de preparar."

    try:
        response = client.chat.completions.create(
            # model="gpt-5.2"
            model="gpt-4o-mini",  # Modelo válido da OpenAI (rápido e barato)
            messages=[
                {"role": "system", "content": f"""
                Você é um gerador de mensagens iniciais para clientes interessados em e-books da empresa LN Editor.

                Diretriz para geração de mensagens:
                 - A mensagem deve ser curta, amigável e convidativa, incentivando o cliente a fazer perguntas sobre os produtos.
                 - Evite usar linguagem formal ou técnica. Seja acolhedor, prestativo e mais humanizado possível.
                 - O público alvo são mulheres geralmente maiores de 30 anos.
                 - Gere mensagens diferentes a cada vez, mas sempre seguindo a mesma linha de mensagens curtas, amigáveis e convidativas, incentivando o cliente a fazer perguntas sobre os produtos. Evite usar linguagem formal ou técnica. Seja acolhedor, prestativo e mais humanizado possível. O público alvo são mulheres geralmente maiores de 30 anos.

                 Exemplos de mensagens:
                 'Olá! Gostaria de saber mais sobre o produto? 😊';
                 'Oi! Me interessei no produto, pode me falar mais? 😋';
                 '🥗 Que legal, quero entender sobre o e-book?'
                 'Maravilha! Quero saber mais sobre o produto 😊'

                 {prompt_produto}

                """},
                {"role": "user", "content": f"gere uma mensagem inicial para eu fornecer ao site de vendas do {prompt_nome_produto}. Essa mensagem deve ser a primeira mensagem que o cliente recebe quando entra em contato pelo whatsapp, então ela deve ser curta, amigável e convidativa, incentivando o cliente a fazer perguntas sobre os produtos. Evite usar linguagem formal ou técnica. Seja acolhedor, prestativo e mais humanizado possível. O público alvo são {prompt_publico_alvo}."}
            ],
            temperature=1.0,  # Um pouco mais criativo
            max_tokens=300    # Limitar resposta (respostas curtas)
        )
        resposta = response.choices[0].message.content
        print(f"[AGENTE_GERA_MENSAGEM_INICIAL] ✅ Resposta gerada: {resposta[:50]}...")
        return resposta
    except Exception as e:
        logger.error(f"[AGENTE_GERA_MENSAGEM_INICIAL] ❌ Erro ao processar mensagem: {e}")
        import traceback
        traceback.print_exc()
        return "Maravilha! Quero saber mais sobre o produto 😊"
