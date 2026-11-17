import json
import logging
import re
from datetime import datetime
import fitz  # pymupdf
from pathlib import Path
import requests
from openai import OpenAI, RateLimitError, AuthenticationError, APIConnectionError, APITimeoutError

from estados_pedido import (ESTADO_COMPROVANTE_EM_ANALISE, pedido_esta_pago, pode_informar_pagamento,
                            valor_pago as _valor_pago)

logger = logging.getLogger(__name__)
client = OpenAI()

_TOOL_NOTIFICAR_ADMIN = {
    "type": "function",
    "function": {
        "name": "notificar_admin",
        "description": (
            "Chama um humano. Use APENAS quando: a cliente pede estorno, reembolso ou devolução do dinheiro com "
            "essas palavras; está irritada ou acha que é golpe; ou fala em se matar, se machucar ou em violência "
            "(motivo 'risco_vida'). Enviar comprovante, dizer quanto pagou, repetir a chave Pix ou dizer que já "
            "pagou NÃO é estorno nem ajuda com pagamento: nesses casos não use esta ferramenta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "enum": ["estorno", "insatisfacao", "ajuda_pagamento", "pergunta_sem_resposta", "risco_vida"],
                    "description": (
                        "Categoria do problema: "
                        "'estorno' = cliente pede devolução ou reembolso do dinheiro; "
                        "'insatisfacao' = cliente irritado, reclamação, acha que é golpe; "
                        "'ajuda_pagamento' = cliente tentou pagar e o Pix não funciona de jeito nenhum; "
                        "'pergunta_sem_resposta' = dúvida não coberta pelo FAQ ou contexto; "
                        "'risco_vida' = fala em suicídio, em se machucar, em violência ou em desespero grave"
                    )
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

_TOOL_NAO_RESPONDER = {
    "type": "function",
    "function": {
        "name": "nao_responder",
        "description": (
            "Não envia nada à cliente. Use quando a mensagem não pede resposta: agradecimento, bênção, emoji, "
            "'ok', despedida, aviso de que enviou o comprovante, ou comentário sobre o pagamento já feito."
        ),
        "parameters": {"type": "object", "properties": {}},
    }
}

_TOOL_PAGAMENTO_INFORMADO = {
    "type": "function",
    "function": {
        "name": "registrar_pagamento_informado",
        "description": (
            "Registra que a cliente já pagou e envia o agradecimento e o bônus automaticamente. Use quando ela "
            "disser que já fez o Pix/pagamento (ex.: 'já paguei', 'fiz o pix de 20', 'transferi'). Não use para "
            "promessa de pagar depois. Depois de usar, não escreva nada."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "valor": {
                    "type": "number",
                    "description": "Valor em reais que ela disse ter pago, se disse (ex.: 20). Omita se não disse."
                }
            },
        },
    }
}

# Resposta fixa quando a IA identifica risco à vida: escala para um humano E responde (exceção à regra
# "escalou = silêncio"), porque a cliente não pode ficar sem nenhuma resposta.
MENSAGEM_RISCO_VIDA = (
    "Querida, sinto muito que você esteja passando por isso. 💛 Você não está sozinha.\n\n"
    "Por favor, converse agora com o *CVV*: é só ligar *188* (grátis, 24 horas) ou acessar *cvv.org.br*. "
    "Se estiver em perigo, ligue *192* (SAMU).\n\n"
    "Vou pedir para alguém da nossa equipe falar com você aqui também."
)

# Instruções do agente de e-mail (agente_resposta_email_produto.py), que só tem a ferramenta notificar_admin.
_INSTRUCOES_ESCALAMENTO = (
    "\n\n## ESCALAMENTO\n"
    "Use a ferramenta notificar_admin APENAS se o cliente pedir estorno, reembolso ou devolução.\n"
    "Para qualquer dúvida sobre o produto, conteúdo ou receitas, responda com base no contexto fornecido.\n"
    "Se o conteúdo não estiver no material, diga claramente que não está incluso.\n"
    "Após acionar a ferramenta, NÃO envie nenhuma mensagem ao cliente."
)

# Regras do WhatsApp (fluxo Responder): ferramentas notificar_admin, nao_responder e registrar_pagamento_informado.
_REGRAS_WHATSAPP = (
    "\n\n## REGRAS GERAIS (valem acima do FAQ e do texto acima)\n"
    "- NUNCA peça comprovante, print, nome do pagador, valor ou horário do pagamento. Nunca discuta se o "
    "pagamento foi feito: confiamos na cliente.\n"
    "- Use notificar_admin só nos casos descritos na ferramenta. Após acionar, NÃO envie mensagem.\n"
    "- Se a cliente falar em suicídio, em se machucar ou em violência, use notificar_admin com motivo "
    "'risco_vida' imediatamente.\n"
    "- Se a mensagem não pede resposta, use nao_responder.\n"
    "- Linhas do histórico que começam com '(Registro:' descrevem o que o sistema enviou; nunca copie esse "
    "formato na resposta.\n"
    "- Para dúvidas sobre o produto, conteúdo ou receitas, responda com base no contexto fornecido. Se o "
    "conteúdo não estiver no material, diga claramente que não está incluso."
)


def _formatar_data(valor) -> str:
    if isinstance(valor, datetime):
        return valor.strftime('%d/%m às %H:%M')
    return str(valor) if valor else ''


def _bloco_situacao_pedido(pedido: dict | None) -> str:
    """Estado do pagamento do pedido, relido no banco pelo responder. Vai depois do FAQ e prevalece sobre ele:
    o FAQ de alguns produtos manda pedir os dados do Pix, o que não pode acontecer com quem já pagou."""
    if pedido_esta_pago(pedido):
        quando = _formatar_data(pedido.get('data_pagamento'))
        valor = f"R$ {_valor_pago(pedido):.2f}".replace('.', ',') if _valor_pago(pedido) > 0 else ''
        detalhes = ', '.join(x for x in (f"em {quando}" if quando else '', valor) if x)
        return (
            "\n\n## SITUAÇÃO DO PEDIDO (prevalece sobre o FAQ)\n"
            f"- A cliente JÁ PAGOU{f' ({detalhes})' if detalhes else ''}. O pagamento está confirmado e o "
            "bônus/surpresa já foi enviado.\n"
            "- Não peça comprovante nem dados do Pix, não ofereça a chave Pix por conta própria e não fale em contribuição pendente.\n"
            "- Se ela agradecer, mandar emoji, confirmar o envio do comprovante, disser quanto pagou, repetir a "
            "chave Pix ou comentar o pagamento, use nao_responder (não agradeça de novo: cada mensagem tem custo). "
            "Na dúvida entre agradecer e nao_responder, use nao_responder.\n"
            "- Se ela quiser contribuir com mais, agradeça e passe a chave Pix do FAQ, sem pedir comprovante."
        )
    if pedido and pedido.get('estado_id') == ESTADO_COMPROVANTE_EM_ANALISE:
        return (
            "\n\n## SITUAÇÃO DO PEDIDO (prevalece sobre o FAQ)\n"
            "- A cliente acabou de enviar o comprovante, que está sendo conferido agora; o agradecimento e o bônus "
            "chegam em instantes, automaticamente.\n"
            "- Não peça comprovante nem dados do Pix e não ofereça a chave Pix.\n"
            "- Se a mensagem for sobre o pagamento ou o comprovante, use nao_responder."
        )
    if pode_informar_pagamento(pedido):
        ja_pagou = ("- Se ela disser que já pagou/fez o Pix, use registrar_pagamento_informado (com o valor, se ela "
                    "disse). Não peça comprovante, nome, valor nem horário.\n")
    else:
        ja_pagou = ("- Se ela disser que já pagou, agradeça e diga que vamos conferir, sem pedir comprovante, nome, "
                    "valor nem horário.\n")
    return (
        "\n\n## SITUAÇÃO DO PEDIDO (prevalece sobre o FAQ)\n"
        "- A cliente ainda não pagou.\n"
        + ja_pagou +
        "- Se disser que vai pagar depois, diga que tudo bem, sem cobrar."
    )


_RE_BOTAO = re.compile(r'^\[botão\]\s*(.*?)\s*→\s*(\S+)\s*$', re.S)


def _registro_legivel(conteudo: str) -> str | None:
    """Linhas que o executor de ações grava no histórico ("[arquivo] x", "[botão] Nome → url", "[imagem] ...")
    viram uma frase descritiva entre parênteses. Lidas literalmente, a IA chegou a responder copiando
    "[botão] Receitas da Lu → https://..." como se fosse texto. None = não é registro do executor (fica igual)."""
    if conteudo.startswith('[arquivo]'):
        nome = conteudo[len('[arquivo]'):].strip()
        return (f"(Registro: enviamos à cliente o arquivo PDF {nome}.)" if nome and nome != 'None'
                else "(Registro: enviamos à cliente um arquivo PDF.)")
    botao = _RE_BOTAO.match(conteudo)
    if botao:
        return f'(Registro: enviamos à cliente um botão "{botao.group(1)}" que abre o link {botao.group(2)}.)'
    if conteudo == '[imagem enviada]':
        return "(Registro: enviamos à cliente uma imagem.)"
    if conteudo.startswith('[imagem]'):
        return f"(Registro: enviamos à cliente uma imagem com a legenda: {conteudo[len('[imagem]'):].strip()})"
    if conteudo == '[áudio enviado]':
        return "(Registro: enviamos à cliente um áudio.)"
    if conteudo.startswith('[template]'):
        return f"(Registro: enviamos à cliente a mensagem: {conteudo[len('[template]'):].strip()})"
    return None


def _historico_legivel(historico: list) -> list:
    """Traduz linhas técnicas do histórico para o agente: o comprovante é gravado como fala da cliente
    ("Comprovante recebido: arquivo.pdf") e o bônus como "[arquivo] nome"; lidas literalmente, a IA achava que a
    cliente só *dizia* ter enviado e pedia os dados do Pix."""
    legivel = []
    for msg in historico:
        conteudo = str(msg.get('content') or '')
        if msg.get('role') == 'user' and conteudo.startswith('Comprovante recebido:'):
            conteudo = '(Registro: a cliente enviou o comprovante de pagamento.)'
        elif msg.get('role') == 'assistant':
            conteudo = _registro_legivel(conteudo) or conteudo
        legivel.append({**msg, 'content': conteudo})
    return legivel


def _notificar_se_necessario(pedido, produto, motivo, mensagem):
    if not pedido:
        return
    from database import tem_notificacao_em_analise
    from whatsapp import criar_notificacao_admin
    if tem_notificacao_em_analise(pedido['id']):
        return
    produto_id = produto.get('id') if produto else pedido.get('produto_id')
    criar_notificacao_admin(pedido['id'], produto_id, motivo, mensagem)
    logger.info(f"[AGENTE] 📋 Notificação criada para admin — motivo: {motivo}")


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


# Decisões que o agente devolve ao fluxo Responder.
ACAO_RESPONDER = 'responder'                     # texto em 'texto'
ACAO_SILENCIAR = 'silenciar'                     # a mensagem não pede resposta
ACAO_ESCALAR = 'escalar'                         # humano notificado; sem resposta (ou falha da OpenAI)
ACAO_RISCO_VIDA = 'risco_vida'                   # humano notificado E resposta fixa MENSAGEM_RISCO_VIDA
ACAO_PAGAMENTO_INFORMADO = 'pagamento_informado'  # cliente disse que pagou; valor citado em 'valor' (ou None)


def _decisao(acao, texto=None, valor=None) -> dict:
    return {'acao': acao, 'texto': texto, 'valor': valor}


def responder_cliente_com_historico_produto(
    pergunta: str, historico: list, produto: dict, pedido: dict = None
) -> dict:
    """Devolve {'acao', 'texto', 'valor'} (ver ACAO_*). `pedido` deve vir relido do banco: o bloco de situação
    (pago / não pago) sai dele."""
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

    system_prompt = montar_system_prompt(prompt_vendas, faq, pdf, pedido)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_historico_legivel(historico))
    messages.append({"role": "user", "content": pergunta})

    tools = [_TOOL_NOTIFICAR_ADMIN, _TOOL_NAO_RESPONDER]
    if pode_informar_pagamento(pedido):
        tools.append(_TOOL_PAGAMENTO_INFORMADO)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=300,
            tools=tools,
            tool_choice="auto",
            parallel_tool_calls=False,
        )
    except (RateLimitError, AuthenticationError, APIConnectionError, APITimeoutError) as exc:
        logger.error(f"[AGENTE] ❌ Erro OpenAI ({type(exc).__name__}): {exc}")
        _notificar_se_necessario(pedido, produto, 'pergunta_sem_resposta',
                                 f"Falha na API OpenAI ({type(exc).__name__}). Cliente não recebeu resposta.")
        return _decisao(ACAO_ESCALAR)

    choice = response.choices[0]

    if choice.message.tool_calls:
        return _tratar_ferramenta(_ferramenta_prioritaria(choice.message.tool_calls), pedido, produto)

    resposta = (choice.message.content or "").strip()
    if not resposta:
        logger.warning("[AGENTE] Resposta vazia da OpenAI.")
        _notificar_se_necessario(pedido, produto, 'pergunta_sem_resposta',
                                 f"Agente retornou resposta vazia. Cliente: {pedido.get('contact_name')} ({pedido.get('contact_phone')})" if pedido else "Agente retornou resposta vazia.")
        return _decisao(ACAO_ESCALAR)

    return _decisao(ACAO_RESPONDER, texto=resposta)


def montar_system_prompt(prompt_vendas: str, faq: str, pdf: str, pedido: dict | None) -> str:
    system_prompt = prompt_vendas
    if faq:
        system_prompt += f"\n\n=== FAQ E INFORMAÇÕES DO PRODUTO ===\n{faq}\n=== FIM DO FAQ ==="
    if pdf:
        system_prompt += f"\n\n=== CONTEÚDO DO PRODUTO ===\n{pdf}\n=== FIM DO CONTEÚDO ==="
    # Por último, para prevalecer sobre o FAQ ("exigir nome do pagador, valor e horário" em alguns produtos).
    system_prompt += _REGRAS_WHATSAPP
    system_prompt += _bloco_situacao_pedido(pedido)
    return system_prompt


def _args_ferramenta(tool_call) -> dict:
    try:
        return json.loads(tool_call.function.arguments or '{}') or {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _ferramenta_prioritaria(tool_calls):
    """Pedimos uma ferramenta por vez (parallel_tool_calls=False), mas se vierem várias, a mais grave vence:
    risco à vida > escalar > pagamento informado > não responder."""
    def peso(call):
        nome = call.function.name
        if nome == 'notificar_admin':
            return 0 if _args_ferramenta(call).get('motivo') == 'risco_vida' else 1
        return {'registrar_pagamento_informado': 2, 'nao_responder': 3}.get(nome, 4)
    return min(tool_calls, key=peso)


def _tratar_ferramenta(tool_call, pedido, produto) -> dict:
    nome = tool_call.function.name
    args = _args_ferramenta(tool_call)

    if nome == 'nao_responder':
        logger.info("[AGENTE] 🔕 Tool chamada: nao_responder")
        return _decisao(ACAO_SILENCIAR)

    if nome == 'registrar_pagamento_informado':
        if not pode_informar_pagamento(pedido):  # a ferramenta nem é oferecida nesses casos
            return _decisao(ACAO_SILENCIAR)
        valor = args.get('valor')
        try:
            valor = float(valor) if valor is not None else None
        except (TypeError, ValueError):
            valor = None
        if valor is not None and valor <= 0:
            valor = None
        logger.info(f"[AGENTE] 💬 Tool chamada: registrar_pagamento_informado | valor={valor}")
        return _decisao(ACAO_PAGAMENTO_INFORMADO, valor=valor)

    if nome != 'notificar_admin':
        # Ferramenta inesperada: não escala (escalar silencia a IA no pedido até um humano agir).
        logger.error(f"[AGENTE] ❌ Ferramenta desconhecida '{nome}' — mensagem fica sem resposta")
        return _decisao(ACAO_SILENCIAR)

    motivo = args.get('motivo', 'pergunta_sem_resposta')
    resumo = args.get('resumo', '')
    logger.info(f"[AGENTE] 🔧 Tool chamada: notificar_admin | motivo={motivo} | resumo={resumo[:80]}")
    _notificar_se_necessario(
        pedido, produto, motivo,
        f"Agente escalou. Motivo: {motivo}. Cliente: {pedido.get('contact_name')} ({pedido.get('contact_phone')}). Resumo: {resumo}" if pedido else f"Agente escalou. Motivo: {motivo}. Resumo: {resumo}",
    )
    if motivo == 'risco_vida':
        return _decisao(ACAO_RISCO_VIDA, texto=MENSAGEM_RISCO_VIDA)
    return _decisao(ACAO_ESCALAR)
