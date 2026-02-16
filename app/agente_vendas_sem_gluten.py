from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

client = OpenAI()

#conectar ao llm
def responder_cliente(pergunta):
    try:
        response = client.chat.completions.create(
            # model="gpt-5.2"
            model="gpt-4o-mini",  # Modelo válido da OpenAI (rápido e barato)
            messages=[
                {"role": "system", "content": "Voce é a Luiza uma vendedora de ebooks de receita para celiacos no whatsapp. Semrpe responda com educação e respostas  prestativa e curta. Se a pergunta for sobre o produto, responda com as informações do produto. Se a pergunta for sobre preço, responda é de graça, mas que o cliente pode ajudar com algum valor simbólico ajudar a LN Editora a construir novos conteúdos de qualidade. Se a pergunta for sobre formas de pagamento, responda que será pix na chave Pix CNPJ 64.980.953/0001-46. Se a pergunta for sobre entrega, responda que a gente confia tanto na qualidade dos produtos que a entrega ocorre antes do pagamento com envio do ebook pelo whatsapp. Se a pergunta for sobre devolução, responda que o ebbok já é do cliente e que se por a caso ele não gostar, a gente devolve o dinheiro, mas ele pode ficar com o ebook. Se a pergunta for sobre suporte, responda com as informações de contato para suporte. Se a pergunta for sobre qualquer outro assunto, responda de forma educada e prestativa. "},
                {"role": "user", "content": pergunta}
            ],
            temperature=0.7,  # Um pouco mais criativo
            max_tokens=300    # Limitar resposta (respostas curtas)
        )
        resposta = response.choices[0].message.content
        logger.info(f"[AGENTE_VENDAS] ✅ Resposta gerada: {resposta[:50]}...")
        return resposta
    except Exception as e:
        logger.error(f"[AGENTE_VENDAS] ❌ Erro ao processar mensagem: {e}")
        import traceback
        traceback.print_exc()
        return "Desculpe, estou com dificuldades técnicas no momento. Por favor, tente novamente em alguns instantes. 🙏"
