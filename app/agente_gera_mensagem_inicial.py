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
                {"role": "user", "content": f"""
                Você é um cliente que gostou da propaganda recebida nas redes sociais, clicou foi redirecionado para o site do produto e clicou em quero saber mais. Você foi redirecionado para o WhatsApp da loja, mas antes de enviar a mensagem para o vendedor, o sistema gera uma mensagem inicial para você.

                Gere uma mensagem.

                Diretriz para essa geração:
                 - A mensagem deve ser curtíssima, amigável e convidativa, incentivando o cliente a fazer perguntas sobre os produtos.
                 - Evite usar linguagem formal ou técnica. Seja acolhedor, prestativo e mais humanizado possível.
                 - O público alvo são mulheres geralmente maiores de 30 anos.
                 - Deve conter apenas menos um emoji relacionado a comida ou felicidade.
                 - Evite usar linguagem formal ou técnica. Seja acolhedor, prestativo e mais humanizado possível.
                 - O público alvo são mulheres geralmente maiores de 30 anos.

                 Exemplos de mensagens:
                 'Olá! Gostaria de saber mais sobre o produto? 😊';
                 'Oi! Me interessei no produto, pode me falar mais? 😋';
                 '🥗 Que legal, quero entender sobre o e-book?'
                 'Maravilha! Quero saber mais sobre o produto 😊'

                 {prompt_produto}

                """}
            ],
            temperature=0.5,  # Um pouco mais criativo
            max_tokens=100    # Limitar resposta (respostas curtas)
        )
        resposta = response.choices[0].message.content
        print(f"[AGENTE_GERA_MENSAGEM_INICIAL] ✅ Resposta gerada: {resposta[:50]}...")
        return resposta
    except Exception as e:
        logger.error(f"[AGENTE_GERA_MENSAGEM_INICIAL] ❌ Erro ao processar mensagem: {e}")
        import traceback
        traceback.print_exc()
        return "Maravilha! Quero saber mais sobre o produto 😊"
