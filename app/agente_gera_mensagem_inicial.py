from openai import OpenAI
import logging
import random
from random import choice

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

                """}
            ],
            temperature=0.0,  # Um pouco mais criativo
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

    def gera_mensagem_inicial_randomicamente():
        dict_mensagens = [
            "Oi! Quero saber mais sobre o produto",
            "Me conta como funciona?",
            "Amei! Tem mais detalhes?",
            "Curti demais, pode explicar rapidinho?",
            "Fiquei interessada, me fala mais?",
            "Tem fotos e medidas? Queria ver mais?",
            "Esse produto é pra mim! Me conta?",
            "Me ajuda a entender melhor?",
            "Como é o material?",
            "Adorei a proposta! me fala mais?",
            "Quero entender os benefícios, pode me dizer?",
            "Tem promo rolando? Me avisa, por favor",
            "Esse produto é pra mim! Me conta mais?",
            "Eu quero saber mais sobre esse produto, me explica rapidinho?",
            "Mal posso esperar para saber mais, me conta tudo?",
            "Pode me mandar mais detalhes sobre esse produto? Estou super interessada!",
            "Estou interessada, mas queria entender melhor. Me explica rapidinho?",
            "Eu quero saber mais sobre esse produto, me explica rapidinho?",
            "Gostei! Como faço pra entender melhor?",
            "que bacana, me ecxplica melhor?"
        ]
        dict_emojis = [
           "😊", "😄", "😃", "😀", "😁", "🥰", "🤩", "😍", "🤗", "😂",
           "🤭", "😸", "😺", "😻", "😉", "😇", "🙌", "✨", "🎉", "🥳"
        ]

        dict_lugares = ["inicio", "final"]

        # Gerar mensagem aleatória com um emoji.
        mensagem = random.choice(list(dict_mensagens))
        emoji = random.choice(list(dict_emojis))
        lugar_emoji = random.choice(list(dict_lugares))
        if lugar_emoji == "inicio":
            mensagem_completa = f"{emoji} {mensagem}"
        else:
            mensagem_completa = f"{mensagem} {emoji}"
        return mensagem_completa
