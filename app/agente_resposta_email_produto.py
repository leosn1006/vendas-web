import json
import logging
from html import escape as _escapar_html
from openai import OpenAI, RateLimitError, AuthenticationError, APIConnectionError, APITimeoutError

from agente_resposta_produto import (
    _TOOL_NOTIFICAR_ADMIN,
    _INSTRUCOES_ESCALAMENTO,
    _notificar_se_necessario,
    _ler_pdf_fonte,
)

logger = logging.getLogger(__name__)
client = OpenAI()

_INSTRUCOES_TOM_EMAIL = (
    "\n\n## FORMATO DA RESPOSTA\n"
    "Você está respondendo a um e-mail de um cliente, não uma mensagem de chat/WhatsApp.\n"
    "Use tom formal e profissional, cordial mas sem intimidade excessiva. Evite emojis — no "
    "máximo um, só se fizer sentido, nunca em sequência.\n"
    "Responda em HTML simples: parágrafos com <p>, destaque com <strong>, links com <a href>, "
    "listas com <ul>/<li> quando ajudar a organizar a resposta. NÃO inclua <html>, <head> ou "
    "<body> — apenas o fragmento de corpo, que será inserido dentro do template de e-mail da marca."
)


def _garantir_html(texto: str) -> str:
    """Rede de segurança: o modelo às vezes ignora a instrução de responder em HTML (visto em
    teste real — respostas curtas tendem a sair em texto puro com \\n\\n). Sem isso, a quebra de
    linha simplesmente some no e-mail final (HTML ignora \\n fora de tag)."""
    if '<' in texto and '>' in texto:
        return texto  # já parece HTML — não mexe
    paragrafos = [p.strip() for p in texto.split('\n\n') if p.strip()]
    return ''.join(
        f'<p>{_escapar_html(p).replace(chr(10), "<br>")}</p>'
        for p in paragrafos
    )


def responder_cliente_email_com_historico_produto(
    pergunta: str, historico: list, produto: dict, pedido: dict = None
) -> str:
    prompt_vendas = str(produto.get('prompt_vendas_email') or produto.get('prompt_vendas') or '').strip()
    faq          = str(produto.get('faq') or '').strip()
    fonte_pdf    = str(produto.get('url_arquivo_produto') or '').strip()

    if not prompt_vendas:
        raise ValueError("[AGENTE-EMAIL] prompt_vendas_email/prompt_vendas não configurado para o produto")

    pdf = ''
    if fonte_pdf:
        try:
            pdf = _ler_pdf_fonte(fonte_pdf)
            logger.info("[AGENTE-EMAIL] ✅ PDF carregado: %s chars de '%s'", len(pdf), fonte_pdf)
        except Exception as e:
            logger.warning("[AGENTE-EMAIL] ⚠️ PDF não carregado '%s': %s", fonte_pdf, e)

    system_prompt = prompt_vendas
    if faq:
        system_prompt += f"\n\n=== FAQ E INFORMAÇÕES DO PRODUTO ===\n{faq}\n=== FIM DO FAQ ==="
    if pdf:
        system_prompt += f"\n\n=== CONTEÚDO DO PRODUTO ===\n{pdf}\n=== FIM DO CONTEÚDO ==="
    system_prompt += _INSTRUCOES_TOM_EMAIL
    system_prompt += _INSTRUCOES_ESCALAMENTO

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historico)
    messages.append({"role": "user", "content": pergunta})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=600,
            tools=[_TOOL_NOTIFICAR_ADMIN],
            tool_choice="auto",
        )
    except (RateLimitError, AuthenticationError, APIConnectionError, APITimeoutError) as exc:
        logger.error(f"[AGENTE-EMAIL] ❌ Erro OpenAI ({type(exc).__name__}): {exc}")
        _notificar_se_necessario(pedido, produto, 'pergunta_sem_resposta',
                                 f"Falha na API OpenAI ({type(exc).__name__}). Cliente não recebeu resposta por e-mail.")
        return None

    choice = response.choices[0]

    if choice.finish_reason == 'tool_calls':
        tool_call = choice.message.tool_calls[0]
        args   = json.loads(tool_call.function.arguments)
        motivo = args.get('motivo', 'pergunta_sem_resposta')
        resumo = args.get('resumo', '')
        logger.info(f"[AGENTE-EMAIL] 🔧 Tool chamada: notificar_admin | motivo={motivo} | resumo={resumo[:80]}")
        _notificar_se_necessario(
            pedido, produto, motivo,
            (f"Agente de e-mail escalou. Motivo: {motivo}. "
             f"Cliente: {pedido.get('contact_name')} ({pedido.get('email')}). Resumo: {resumo}")
            if pedido else f"Agente de e-mail escalou. Motivo: {motivo}. Resumo: {resumo}",
        )
        return None

    resposta = (choice.message.content or "").strip()
    if not resposta:
        logger.warning("[AGENTE-EMAIL] Resposta vazia da OpenAI.")
        _notificar_se_necessario(
            pedido, produto, 'pergunta_sem_resposta',
            (f"Agente de e-mail retornou resposta vazia. Cliente: {pedido.get('contact_name')} ({pedido.get('email')})")
            if pedido else "Agente de e-mail retornou resposta vazia.",
        )
        return None

    return _garantir_html(resposta)
