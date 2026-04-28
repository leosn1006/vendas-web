import logging
import random

logger = logging.getLogger(__name__)

_EMOJIS = ["✨"]

_MENSAGENS_FALLBACK = [
    "Olá, tenho interesse nas receitas",
    "Oi, tenho interesse nas receitas",
    "Olá, quero receber as receitas",
    "Oi, quero receber as receitas",
    "Olá, pode me enviar as receitas?",
    "Oi, pode me enviar as receitas?",
    "Olá, gostaria de saber mais sobre as receitas",
    "Oi, gostaria de saber mais sobre as receitas",
]


def gera_mensagem_inicial_randomicamente(produto_id=1):
    from database import listar_mensagens_sugeridas

    try:
        rows = listar_mensagens_sugeridas(produto_id)
        mensagens = [r['mensagem'] for r in rows] if rows else _MENSAGENS_FALLBACK
    except Exception as e:
        logger.error(f"[AGENTE] ⚠️ Erro ao buscar mensagens do BD, usando fallback: {e}")
        mensagens = _MENSAGENS_FALLBACK

    mensagem = random.choice(mensagens)
    # Vamos retirar o emoji por enquanto, para focar na mensagem
    # emoji = random.choice(_EMOJIS)

    #if random.choice(["inicio", "final"]) == "inicio":
    #    return f"{emoji} {mensagem}", emoji
    #return f"{mensagem} {emoji}", emoji
    return mensagem
