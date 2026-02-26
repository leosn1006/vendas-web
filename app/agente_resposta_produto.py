import logging
import fitz  # pymupdf
from pathlib import Path
import requests
from openai import OpenAI

logger = logging.getLogger(__name__)
client = OpenAI()

# Cache por fonte para evitar releitura em toda mensagem
_FAQ_CACHE: dict[str, str] = {}
_PDF_CACHE: dict[str, str] = {}


def _ler_texto_fonte(fonte: str) -> str:
    if fonte.startswith('http://') or fonte.startswith('https://'):
        response = requests.get(fonte, timeout=20)
        response.raise_for_status()
        response.encoding = response.encoding or 'utf-8'
        return response.text

    caminho = Path(fonte)
    if not caminho.is_absolute():
        caminho = Path(__file__).parent / fonte

    return caminho.read_text(encoding='utf-8')


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


def carregar_faq_produto(fonte_faq: str) -> str:
    if fonte_faq not in _FAQ_CACHE:
        try:
            _FAQ_CACHE[fonte_faq] = _ler_texto_fonte(fonte_faq)
            logger.info("[AGENTE] ✅ FAQ carregado para fonte: %s", fonte_faq)
        except Exception as e:
            logger.warning("[AGENTE] ⚠️ FAQ não encontrado para '%s': %s", fonte_faq, e)
            _FAQ_CACHE[fonte_faq] = ""
    return _FAQ_CACHE[fonte_faq]


def carregar_pdf_produto(fonte_pdf: str) -> str:
    if fonte_pdf not in _PDF_CACHE:
        try:
            _PDF_CACHE[fonte_pdf] = _ler_pdf_fonte(fonte_pdf)
            logger.info("[AGENTE] ✅ PDF carregado para fonte '%s': %s caracteres", fonte_pdf, len(_PDF_CACHE[fonte_pdf]))
        except Exception as e:
            logger.warning("[AGENTE] ⚠️ PDF não encontrado para '%s': %s", fonte_pdf, e)
            _PDF_CACHE[fonte_pdf] = ""
    return _PDF_CACHE[fonte_pdf]


def responder_cliente_produto(pergunta: str, historico: list, prompt_vendas: str) -> str:
    """Gera resposta de WhatsApp usando prompt específico do produto."""
    mensagens = [
        {"role": "system", "content": prompt_vendas}
    ]
    mensagens.extend(historico or [])
    mensagens.append({"role": "user", "content": pergunta})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=mensagens,
        temperature=0.3,
        max_tokens=300,
    )

    resposta = (response.choices[0].message.content or "").strip()
    if not resposta:
        logger.warning("[AGENTE-RESPOSTA-PRODUTO] Resposta vazia da OpenAI. Retornando mensagem de contingência.")
        return "Perfeito! Vou verificar direitinho e já te respondo 🙏"

    return resposta


def responder_cliente(pergunta: str) -> str:
    """Mantida para compatibilidade com outros fluxos que ainda a usam."""
    return responder_cliente_com_historico(pergunta, historico=[])


def responder_cliente_com_historico_produto(pergunta: str, historico: list, produto: dict) -> str:
    prompt_vendas = str(produto.get('prompt_vendas') or '').strip()
    fonte_faq = str(produto.get('url_faq_produto') or '').strip()
    fonte_pdf = str(produto.get('url_arquivo_produto') or '').strip()

    if not prompt_vendas:
        raise ValueError("[AGENTE] prompt_vendas não configurado para o produto")
    if not fonte_faq:
        raise ValueError("[AGENTE] url_faq_produto não configurado para o produto")
    if not fonte_pdf:
        raise ValueError("[AGENTE] url_arquivo_produto não configurado para o produto")

    faq = carregar_faq_produto(fonte_faq)
    pdf = carregar_pdf_produto(fonte_pdf)

    system_prompt = f"""{prompt_vendas}

=== FAQ E INFORMAÇÕES DO PRODUTO ===
{faq}
=== FIM DO FAQ ===

=== CONTEÚDO DO PRODUTO (use para responder dúvidas específicas) ===
{pdf}
=== FIM DO CONTEÚDO ==="""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historico)
    messages.append({"role": "user", "content": pergunta})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3,
        max_tokens=300
    )

    return response.choices[0].message.content


def responder_cliente_com_historico(pergunta: str, historico: list) -> str:
    """Mantida para compatibilidade legado (produto padrão)."""
    produto_padrao = {
        'prompt_vendas': (
            "Você é a Luiza, uma vendedora atenciosa e cordial de e-books de receitas sem glúten. "
            "Responda de forma sucinta no estilo WhatsApp. Use emojis moderadamente. "
            "Nunca invente informações. Se não souber, diga que vai verificar e retornar em breve."
        ),
        'url_faq_produto': 'prompts/faq_paes_sem_gluten.txt',
        'url_arquivo_produto': '/static/arquivos/paes-sem-gluten.pdf',
    }
    return responder_cliente_com_historico_produto(pergunta, historico, produto_padrao)
