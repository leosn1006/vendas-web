import logging
import fitz  # pymupdf
from pathlib import Path
import requests
from openai import OpenAI

logger = logging.getLogger(__name__)
client = OpenAI()


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


def responder_cliente_com_historico_produto(pergunta: str, historico: list, produto: dict) -> str:
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

    logger.info("[AGENTE] 📋 Contexto montado — prompt: %d chars | faq: %d chars | pdf: %d chars",
                len(prompt_vendas), len(faq), len(pdf))

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historico)
    messages.append({"role": "user", "content": pergunta})

    print("=== MENSAGENS ENVIADAS AO MODELO ===")
    for msg in messages:
        print(f"{msg['role'].upper()}: {msg['content'][:500]}{'...' if len(msg['content']) > 500 else ''}")
    print("=== FIM DAS MENSAGENS ===")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3,
        max_tokens=300
    )

    resposta = (response.choices[0].message.content or "").strip()
    if not resposta:
        logger.warning("[AGENTE] Resposta vazia da OpenAI. Retornando mensagem de contingência.")
        return "Perfeito! Vou verificar direitinho e já te respondo 🙏"

    return resposta


def responder_cliente(pergunta: str) -> str:
    """Mantida para compatibilidade com outros fluxos que ainda a usam."""
    return responder_cliente_com_historico(pergunta, historico=[])


def responder_cliente_com_historico(pergunta: str, historico: list) -> str:
    """Mantida para compatibilidade legado (produto padrão)."""
    produto_padrao = {
        'prompt_vendas': (
            "Você é a Luiza, uma vendedora atenciosa e cordial de e-books de receitas sem glúten. "
            "Responda de forma sucinta no estilo WhatsApp. Use emojis moderadamente. "
            "Nunca invente informações. Se não souber, diga que vai verificar e retornar em breve."
        ),
        'faq': '',
        'url_arquivo_produto': '/static/arquivos/paes-sem-gluten.pdf',
    }
    return responder_cliente_com_historico_produto(pergunta, historico, produto_padrao)
