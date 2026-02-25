import logging
import fitz  # pymupdf
from pathlib import Path
from openai import OpenAI

logger = logging.getLogger(__name__)
client = OpenAI()

# Cache do FAQ e do PDF — carregado uma vez na inicialização. Se quiser alterar o FAQ ou o PDF, basta editar os arquivos correspondentes e reiniciar a aplicação (docker compose restart worker)
_FAQ_PAES_SEM_GLUTEN = None
_PDF_PAES_SEM_GLUTEN = None

def carregar_faq() -> str:
    global _FAQ_PAES_SEM_GLUTEN
    if _FAQ_PAES_SEM_GLUTEN is None:
        caminho = Path(__file__).parent / "prompts" / "faq_paes_sem_gluten.txt"
        try:
            _FAQ_PAES_SEM_GLUTEN = caminho.read_text(encoding='utf-8')
            logger.info("[AGENTE] ✅ FAQ carregado com sucesso")
        except FileNotFoundError:
            logger.warning("[AGENTE] ⚠️ FAQ não encontrado, usando prompt sem contexto")
            _FAQ_PAES_SEM_GLUTEN = ""
    return _FAQ_PAES_SEM_GLUTEN

def responder_cliente(pergunta: str) -> str:
    """Mantida para compatibilidade com outros fluxos que ainda a usam."""
    return responder_cliente_com_historico(pergunta, historico=[])

def carregar_pdf() -> str:
    global _PDF_PAES_SEM_GLUTEN
    if _PDF_PAES_SEM_GLUTEN is None:
        caminho = "/static/arquivos/paes-sem-gluten.pdf"
        try:
            doc = fitz.open(caminho)
            _PDF_PAES_SEM_GLUTEN = ''.join([p.get_text() for p in doc])
            logger.info(f"[AGENTE] ✅ PDF carregado: {len(_PDF_PAES_SEM_GLUTEN)} caracteres")
        except Exception as e:
            logger.warning(f"[AGENTE] ⚠️ PDF não encontrado: {e}")
            _PDF_PAES_SEM_GLUTEN = ""
    return _PDF_PAES_SEM_GLUTEN

def responder_cliente_com_historico(pergunta: str, historico: list) -> str:
    faq = carregar_faq()
    pdf = carregar_pdf()

    system_prompt = f"""Você é a Luiza, uma vendedora atenciosa e cordial de e-books de receitas sem glúten.
Responda de forma sucinta no estilo WhatsApp. Use emojis moderadamente.
Nunca invente informações que não estejam no contexto abaixo.
Se não souber a resposta, diga que vai verificar e retornar em breve.
Não adicione explicações extras, responda apenas com a fala da Luiza.

=== FAQ E INFORMAÇÕES DO PRODUTO ===
{faq}
=== FIM DO FAQ ===

=== CONTEÚDO DO E-BOOK (use para responder dúvidas sobre receitas) ===
{pdf}
=== FIM DO E-BOOK ==="""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historico)
    messages.append({"role": "user", "content": pergunta})

    print("=== MENSAGENS PARA O MODELO ===")
    for msg in messages:
        print(f"{msg['role'].upper()}: {msg['content']}\n")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3,
        max_tokens=300
    )

    return response.choices[0].message.content
