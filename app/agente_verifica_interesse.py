import logging
from openai import OpenAI

logger = logging.getLogger(__name__)
client = OpenAI()


def classificar_interesse_compra(mensagem_cliente: str) -> str:
    """
    Classifica a intenção de compra retornando apenas 'sim' ou 'não'.
    Agente enxuto para reduzir tokens e custo.
    """
    system_prompt = (
        "Você classifica intenção de compra em WhatsApp. "
        "Responda com apenas uma palavra: sim ou não. "
        "'sim' quando houver interesse, curiosidade, pergunta de compra ou aceite. "
        "'não' quando houver recusa, desinteresse, objeção forte ou adiamento. "
        "Se a mensagem for ambígua, curta ou incerta (ex.: ok, joia, emoji), responda 'sim'."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "quero sim, me manda"},
            {"role": "assistant", "content": "sim"},
            {"role": "user", "content": "quanto custa?"},
            {"role": "assistant", "content": "sim"},
            {"role": "user", "content": "vou pensar e te aviso depois"},
            {"role": "assistant", "content": "não"},
            {"role": "user", "content": "não tenho interesse agora"},
            {"role": "assistant", "content": "não"},
            {"role": "user", "content": "pode mandar o material"},
            {"role": "assistant", "content": "sim"},
            {"role": "user", "content": "👍"},
            {"role": "assistant", "content": "sim"},
            {"role": "user", "content": "ok"},
            {"role": "assistant", "content": "sim"},
            {"role": "user", "content": mensagem_cliente or ""},
        ],
        temperature=0,
        max_tokens=3,
    )

    conteudo = (response.choices[0].message.content or "").strip().lower()
    conteudo = conteudo.rstrip('.!?')

    if conteudo.startswith('sim'):
        return 'sim'
    if conteudo.startswith('não') or conteudo.startswith('nao'):
        return 'não'

    logger.warning("[AGENTE-INTERESSE] Resposta inesperada do modelo: %s. Aplicando fallback para 'sim'.", conteudo)
    return 'sim'
