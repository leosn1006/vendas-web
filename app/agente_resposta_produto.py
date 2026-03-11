import json
import logging
import fitz  # pymupdf
from pathlib import Path
import requests
from openai import OpenAI

logger = logging.getLogger(__name__)
client = OpenAI()

_TOOL_NOTIFICAR_ADMIN = {
    "type": "function",
    "function": {
        "name": "notificar_admin",
        "description": (
            "Use quando não conseguir resolver: pedido de estorno, reembolso, devolução de valor, "
            "ou qualquer pergunta que não está coberta pelo FAQ e contexto do produto. "
            "NÃO use para perguntas normais sobre o produto que você sabe responder."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "enum": ["estorno", "pergunta_sem_resposta"],
                    "description": "Categoria do problema"
                },
                "resumo": {
                    "type": "string",
                    "description": "Resumo curto do que o cliente disse/pediu"
                }
            },
            "required": ["motivo", "resumo"]
        }
    }
}

_INSTRUCOES_ESCALAMENTO = (
    "\n\n## ESCALAMENTO\n"
    "Use a ferramenta notificar_admin APENAS se o cliente pedir estorno, reembolso ou devolução.\n"
    "Para qualquer dúvida sobre o produto, conteúdo ou receitas, responda com base no contexto fornecido.\n"
    "Se o conteúdo não estiver no material, diga claramente que não está incluso.\n"
    "Após acionar a ferramenta, responda: \"Vou verificar e te retorno em breve 🙏\""
)


def _ler_pdf_fonte(fonte: str) -> str:
    if fonte.startswith('http://') or fonte.startswith('https://'):
        response = requests.get(fonte, timeout=30)
        response.raise_for_status()
        doc = fitz.open(stream=response.content, filetype='pdf')
    else:
        caminho = Path(fonte)
        if not caminho.is_absolute():
            caminho = Path(__file__).parent / fonte
        doc = fitz.open(str(caminho))

    try:
        return ''.join([pagina.get_text() for pagina in doc])
    finally:
        doc.close()


def responder_cliente_com_historico_produto(
    pergunta: str, historico: list, produto: dict, pedido: dict = None
) -> str:
    prompt_vendas = str(produto.get('prompt_vendas') or '').strip()
    faq          = str(produto.get('faq') or '').strip()
    fonte_pdf    = str(produto.get('url_arquivo_produto') or '').strip()

    if not prompt_vendas:
        raise ValueError("[AGENTE] prompt_vendas não configurado para o produto")

    pdf = ''
    if fonte_pdf:
        try:
            pdf = _ler_pdf_fonte(fonte_pdf)
            logger.info("[AGENTE] ✅ PDF carregado: %s chars de '%s'", len(pdf), fonte_pdf)
        except Exception as e:
            logger.warning("[AGENTE] ⚠️ PDF não carregado '%s': %s", fonte_pdf, e)

    system_prompt = prompt_vendas
    if faq:
        system_prompt += f"\n\n=== FAQ E INFORMAÇÕES DO PRODUTO ===\n{faq}\n=== FIM DO FAQ ==="
    if pdf:
        system_prompt += f"\n\n=== CONTEÚDO DO PRODUTO ===\n{pdf}\n=== FIM DO CONTEÚDO ==="
    system_prompt += _INSTRUCOES_ESCALAMENTO

    #logger.info("[AGENTE] 📋 Contexto montado — prompt: %d chars | faq: %d chars | pdf: %d chars",
    #            len(prompt_vendas), len(faq), len(pdf))
    #logger.info("[AGENTE] 🔍 PROMPT_VENDAS:\n%s", prompt_vendas[:500])
    #logger.info("[AGENTE] 🔍 FAQ (%d chars):\n%s", len(faq), faq[:500] if faq else '(vazio)')
    #logger.info("[AGENTE] 🔍 PDF fonte: '%s' | %d chars carregados", fonte_pdf or '(não configurado)', len(pdf))
    #logger.info("[AGENTE] 🔍 PDF preview:\n%s", pdf[:500] if pdf else '(vazio)')

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historico)
    messages.append({"role": "user", "content": pergunta})

#    print("=== MENSAGENS ENVIADAS AO MODELO ===")
#    for msg in messages:
#        print(f"{msg['role'].upper()}: {msg['content'][:500]}{'...' if len(msg['content']) > 500 else ''}")
#    print("=== FIM DAS MENSAGENS ===")g

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3,
        max_tokens=300,
        tools=[_TOOL_NOTIFICAR_ADMIN],
        tool_choice="auto",
    )

    choice = response.choices[0]

    if choice.finish_reason == 'tool_calls':
        tool_call = choice.message.tool_calls[0]
        args   = json.loads(tool_call.function.arguments)
        motivo = args.get('motivo', 'pergunta_sem_resposta')
        resumo = args.get('resumo', '')
        logger.info(f"[AGENTE] 🔧 Tool chamada: notificar_admin | motivo={motivo} | resumo={resumo[:80]}")

        if pedido:
            from whatsapp import notificar_admin_pedido
            notificar_admin_pedido(pedido, (
                f"🤖 *Agente escalou* — Pedido #{pedido.get('id')}\n\n"
                f"Cliente: #{pedido.get('id')} — {pedido.get('contact_name')} ({pedido.get('contact_phone')})\n"
                f"Motivo: *{motivo}*\n"
                f"Resumo: {resumo}"
            ))
            logger.info(f"[AGENTE] 📲 Admin notificado — motivo: {motivo}")

        return "Vou verificar com nossa equipe e te retorno em breve 🙏"

    resposta = (choice.message.content or "").strip()
    if not resposta:
        logger.warning("[AGENTE] Resposta vazia da OpenAI. Retornando mensagem de contingência.")
        return "Perfeito! Vou verificar direitinho e já te respondo 🙏"

    return resposta
