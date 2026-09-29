"""
Envio da resposta de um e-mail da fila de atendimento (emails_atendimento) — pela aprovação no
admin (1 clique) ou pelo envio automático do leitor (fluxo_email_conversas), quando o tipo de
resposta está liberado em EMAIL_ATENDIMENTO_AUTO_TIPOS.

Responde no mesmo thread (threadId + In-Reply-To), com a moldura e a persona do produto, e
atualiza o estado e os marcadores do Gmail. Se houver pedido vinculado, grava também em
mensagens_email_pedido (tela de conversa do produto e histórico do agente de IA).
"""

import os
import logging
from datetime import datetime

import database as db
from fluxos import _gmail_labels as labels
from fluxos._email_gmail import enviar as _enviar_gmail, wrapper_html as _wrapper_html
from fluxos.email_respostas import TIPOS_AGUARDAM_CLIENTE, assinatura

logger = logging.getLogger(__name__)

_TAG = 'ATENDIMENTO-EMAIL'


def aplicar_rotulos(service, atendimento: dict) -> None:
    """Espelha no Gmail o estado atual do atendimento (status + produto + processado)."""
    adicionar, remover = labels.rotulos_do_estado(atendimento['tipo'], atendimento['estado'])
    adicionar.append(labels.PROCESSADO)
    if atendimento['tipo'] == 'vendas':
        adicionar.append(labels.nome_label_produto(atendimento.get('produto_nome')))
    labels.aplicar(service, atendimento['gmail_message_id'], adicionar, remover,
                   arquivar=atendimento['tipo'] == 'ruido')


REMETENTE_SEM_PRODUTO = 'suporte@lsnlivros.com.br'


def escolher_remetente(caixa: str, produto: dict | None) -> str:
    """Por qual endereço a resposta sai. Com produto (do pedido ou do alias da chave PIX para onde
    a cliente escreveu): o alias do produto, o mesmo da entrega e das cobranças — a cliente
    continua falando com a mesma persona. Sem produto: o suporte (EMAIL_ATENDIMENTO_REMETENTE),
    nunca o admin@, que fica para assuntos administrativos. No dev, sempre a caixa de teste.

    Todo endereço usado aqui precisa estar em "Enviar e-mail como" da caixa, senão o Gmail troca
    o remetente pelo endereço principal com o nome padrão da conta."""
    if caixa != labels.CAIXA_PRODUCAO:
        return caixa
    return ((produto or {}).get('email_remetente')
            or (os.getenv('EMAIL_ATENDIMENTO_REMETENTE') or '').strip()
            or REMETENTE_SEM_PRODUTO)


def enviar(atendimento_id: int, corpo_html: str, por: str, automatica: bool = False) -> None:
    atendimento = db.get_email_atendimento(atendimento_id)
    if not atendimento:
        raise ValueError(f'Atendimento #{atendimento_id} não encontrado')
    caixa = labels.caixa_atendimento()
    if not caixa:
        raise RuntimeError('Caixa de atendimento não configurada (no dev, defina EMAIL_ATENDIMENTO_CAIXA '
                           'com uma caixa de teste)')

    produto = db.get_produto_by_id(atendimento['produto_id']) if atendimento.get('produto_id') else None
    nome_persona = assinatura(produto)
    nome_produto = (produto or {}).get('nome')
    remetente = escolher_remetente(caixa, produto)

    assunto = (atendimento.get('assunto') or '').strip() or 'Sua mensagem'
    assunto = assunto if assunto.lower().startswith('re:') else f'Re: {assunto}'

    html = _wrapper_html(
        titulo_header=f'{nome_persona} respondeu',
        corpo_interno_html=corpo_html,
        nome_remetente=nome_persona,
        cor_primaria=(produto or {}).get('email_cor_primaria') or '#2d6a1f',
        cor_secundaria=(produto or {}).get('email_cor_secundaria') or '#b45309',
        rodape='Você recebeu este e-mail em resposta à sua mensagem para a LBE Livros.',
    )
    if not db.reservar_envio_atendimento(atendimento_id, por):
        raise ValueError(f'Atendimento #{atendimento_id} já foi respondido (ou está sendo enviado agora)')
    try:
        resultado = _enviar_gmail(
            destinatario=atendimento['remetente_email'],
            remetente=remetente,
            nome_remetente=f'{nome_persona} — {nome_produto}' if nome_produto else nome_persona,
            subject=assunto,
            html=html,
            thread_id=atendimento['gmail_thread_id'],
            in_reply_to=atendimento.get('rfc_message_id'),
            conta=caixa,
        ) or {}
    except Exception:
        db.liberar_envio_atendimento(atendimento_id)  # não saiu: pode tentar de novo
        raise

    estado = 'aguardando_cliente' if atendimento.get('resposta_tipo') in TIPOS_AGUARDAM_CLIENTE else 'respondido'
    agora = datetime.now()
    db.atualizar_email_atendimento(atendimento_id, estado=estado, resposta_html=corpo_html,
                                   respondido_em=agora, respondido_por=por,
                                   resposta_automatica=1 if automatica else 0)
    logger.info(f"[{_TAG}] ✉️ Resposta enviada — atendimento #{atendimento_id} "
                f"({atendimento.get('resposta_tipo') or 'manual'}, por {por})")

    # Organização (marcadores) e histórico do pedido: o e-mail já saiu, falha aqui só loga
    try:
        service = labels.servico(caixa)
        aplicar_rotulos(service, {**atendimento, 'estado': estado})
        if resultado.get('id'):
            labels.aplicar(service, resultado['id'], [f"Enviados/{nome_produto or 'Sem produto'}"])
    except Exception as exc:
        logger.warning(f"[{_TAG}] ⚠️ Marcadores não aplicados no atendimento #{atendimento_id}: {exc}")

    if atendimento.get('pedido_id'):
        db.salvar_mensagem_email_pedido(
            pedido_id=atendimento['pedido_id'], direcao='enviada',
            gmail_message_id=resultado.get('id') or f"local-atend-{atendimento_id}",
            gmail_thread_id=resultado.get('threadId') or atendimento['gmail_thread_id'],
            rfc_message_id=resultado.get('rfcMessageId'), assunto=assunto, remetente=remetente,
            destinatario=atendimento['remetente_email'], corpo_texto=None, corpo_html=corpo_html,
            data_mensagem=agora,
        )


def mudar_estado(atendimento_id: int, estado: str, por: str, **campos) -> None:
    """Mudança manual pelo admin (respondido sem enviar, mover p/ administrativo…) + marcadores."""
    db.atualizar_email_atendimento(atendimento_id, estado=estado, **campos,
                                   **({'respondido_em': datetime.now(), 'respondido_por': por}
                                      if estado in ('respondido', 'sem_acao') else {}))
    caixa = labels.caixa_atendimento()
    if not caixa:
        return
    try:
        aplicar_rotulos(labels.servico(caixa), db.get_email_atendimento(atendimento_id))
    except Exception as exc:
        logger.warning(f"[{_TAG}] ⚠️ Marcadores não aplicados no atendimento #{atendimento_id}: {exc}")
