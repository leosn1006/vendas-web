"""
Envio de resposta de e-mail pelo admin a partir da tela de conversa — aprovando/editando a
sugestão da IA (app/agente_resposta_email_produto.py) ou escrevendo do zero.

Reaproveita o mesmo wrapper_html() (identidade visual da marca) usado no e-mail de entrega
(entrega_pedido_email.py), só trocando o conteúdo interno pelo HTML aprovado pelo admin.
"""

import os
import time
import logging
from datetime import datetime

from fluxos._email_gmail import enviar as _enviar_gmail, wrapper_html as _wrapper_html

logger = logging.getLogger(__name__)


def enviar_resposta(pedido_id: int, corpo_html: str, notificacao_id: int = None) -> None:
    import database as db

    pedido  = db.get_pedido(pedido_id)
    produto = db.get_produto_disponivel_web(pedido['produto_id'])

    destinatario = pedido.get('email')
    if not destinatario:
        raise ValueError(f'[EMAIL] Pedido #{pedido_id} sem e-mail — não é possível responder')

    nome_produto   = (produto or {}).get('nome', 'Guia Digital')
    remetente      = (produto or {}).get('email_remetente') or os.getenv('EMAIL_FROM', '')
    nome_remetente = (produto or {}).get('email_nome_remetente') or 'LSN Livros'
    cor_primaria   = (produto or {}).get('email_cor_primaria') or '#2d6a1f'
    cor_secundaria = (produto or {}).get('email_cor_secundaria') or '#b45309'

    # Continua a thread existente: assunto herdado da última mensagem (não um novo, que poderia
    # não bater com o da thread e fazer a API do Gmail rejeitar o threadId) + In-Reply-To/
    # References apontando pro Message-ID dessa última mensagem — é isso que realmente ancora a
    # resposta na conversa, o threadId sozinho não é suficiente.
    pedido_num  = f'#{pedido_id:04d}'
    ultima      = db.buscar_ultima_mensagem_email_pedido(pedido_id) or {}
    assunto_base = ultima.get('assunto') or f'Pedido {pedido_num} — {nome_produto}'
    subject      = assunto_base if assunto_base.lower().startswith('re:') else f'Re: {assunto_base}'
    in_reply_to  = ultima.get('rfc_message_id')

    rodape  = 'Você recebeu este e-mail porque realizou uma compra em lsnlivros.com.br.'

    html = _wrapper_html(
        titulo_header=f'{nome_remetente} respondeu',
        corpo_interno_html=corpo_html,
        nome_remetente=nome_remetente,
        cor_primaria=cor_primaria,
        cor_secundaria=cor_secundaria,
        rodape=rodape,
    )

    resultado = _enviar_gmail(
        destinatario=destinatario,
        remetente=remetente,
        nome_remetente=f'{nome_remetente} — {nome_produto}',
        subject=subject,
        html=html,
        thread_id=pedido.get('gmail_thread_id') or None,
        in_reply_to=in_reply_to,
    ) or {}

    thread_id = resultado.get('threadId') or pedido.get('gmail_thread_id') or ''
    if resultado.get('threadId') and not pedido.get('gmail_thread_id'):
        db.definir_gmail_thread_pedido(pedido_id, thread_id)

    db.salvar_mensagem_email_pedido(
        pedido_id=pedido_id,
        direcao='enviada',
        gmail_message_id=resultado.get('id') or f'local-{pedido_id}-{int(time.time())}',
        gmail_thread_id=thread_id,
        rfc_message_id=resultado.get('rfcMessageId'),
        assunto=subject,
        remetente=remetente,
        destinatario=destinatario,
        corpo_texto=None,
        corpo_html=corpo_html,
        data_mensagem=datetime.now(),
    )

    if notificacao_id and produto:
        db.marcar_notificacao_respondida(notificacao_id, produto['id'])

    logger.info(f'[EMAIL] ✅ Resposta enviada para pedido #{pedido_id} ({destinatario})')
