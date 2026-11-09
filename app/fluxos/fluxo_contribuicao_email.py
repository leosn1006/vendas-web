"""
E-mails da contribuição no site (docs/CONTRIBUICAO_WEB.md): a entrega do livro antes do pagamento e os lembretes
da contribuição — o equivalente, por e-mail, do follow-up de cobrança do WhatsApp (lá, ~1 em 4 vendas vem dele).

  enviar_entrega(pedido_id)  — logo depois do e-mail informado (estado 1009): "seu livro chegou", link da Estante.
  executar_lembretes()       — beat a cada 10 min: 1º lembrete `lembrete1_minutos` depois do e-mail (padrão 2h),
                               2º `lembrete2_minutos` (padrão 24h). Link /pedido2/<guid>?lembrete=1 (a Estante toca
                               o áudio de lembrete).

Travas (lição do follow-up web: 15 de 94 cobradas depois de já terem pago): não envia se ela já pagou o produto
(pedido vinculado ou mesmo e-mail — db.contribuicao_paga), só das 8h às 22h, e o lembrete é reservado ANTES de
enviar (duas varreduras nunca mandam o mesmo). Remetente e cores do produto; a resposta dela cai na fila de
atendimento por e-mail (thread gravada no pedido).
"""
import html as _html
import logging
import os
import time
from datetime import datetime

from fluxos._email_gmail import enviar as _enviar_gmail, wrapper_html as _wrapper_html
from fluxos._gmail_labels import agora_sp, rotular_enviado
from web.contribuicao import formatar_preco

logger = logging.getLogger(__name__)

_TAG = '[CONTRIBUICAO-EMAIL]'
HORARIO_LEMBRETE = (8, 22)  # [8h, 22h) em São Paulo


def _dados_envio(pedido: dict) -> dict:
    import database as db
    produto = db.get_produto_by_id(pedido['produto_id']) or {}
    config = db.get_contribuicao_config(pedido['produto_id']) or {}
    plano = db.get_plano_venda(pedido['produto_id'])
    preco = float(plano['preco_promocional']) if plano else None
    return {
        'remetente': produto.get('email_remetente') or os.getenv('EMAIL_FROM', ''),
        'nome_remetente': produto.get('email_nome_remetente') or config.get('persona_nome') or 'LSN Livros',
        'nome_produto': produto.get('nome') or 'seu livro',
        'cor_primaria': produto.get('email_cor_primaria') or '#2d6a1f',
        'cor_secundaria': produto.get('email_cor_secundaria') or '#b45309',
        'persona': config.get('persona_nome') or produto.get('email_nome_remetente') or '',
        'preco': formatar_preco(preco) if preco else '',
        'base_url': os.getenv('APP_BASE_URL', '').rstrip('/'),
    }


def _enviar(pedido: dict, d: dict, subject: str, corpo: str, resumo: str) -> None:
    """Envia, rotula e registra na timeline de atendimento (a resposta dela vira conversa do pedido)."""
    import database as db
    html = _wrapper_html(subject, corpo, d['nome_remetente'], d['cor_primaria'], d['cor_secundaria'],
                         'Você recebeu este e-mail porque pediu o livro no nosso site. '
                         'Responda este e-mail se precisar de ajuda.')
    # Cada e-mail abre a própria conversa: threadId sem In-Reply-To e com assunto diferente pode ser recusado pela
    # API do Gmail (ver _email_gmail.enviar). A thread do pedido continua sendo a da entrega.
    resultado = _enviar_gmail(destinatario=pedido['email'], remetente=d['remetente'],
                              nome_remetente=f"{d['nome_remetente']} — {d['nome_produto']}",
                              subject=subject, html=html) or {}
    rotular_enviado(resultado.get('id'), d['nome_produto'])
    thread_id = resultado.get('threadId')
    try:
        if thread_id and not pedido.get('gmail_thread_id'):
            db.definir_gmail_thread_pedido(pedido['id'], thread_id)
        db.salvar_mensagem_email_pedido(
            pedido_id=pedido['id'], direcao='enviada',
            gmail_message_id=resultado.get('id') or f"local-{pedido['id']}-{int(time.time())}",
            gmail_thread_id=thread_id or '', rfc_message_id=resultado.get('rfcMessageId'),
            assunto=subject, remetente=d['remetente'], destinatario=pedido['email'],
            corpo_texto=resumo, corpo_html=html, data_mensagem=datetime.now())
    except Exception as e:
        logger.error(f"{_TAG} E-mail do pedido #{pedido['id']} enviado, mas falhou ao registrar na timeline: {e}")


def _botao(link: str, texto: str, cor: str) -> str:
    return (f'<p style="text-align:center; margin:26px 0;"><a href="{_html.escape(link, quote=True)}" '
            f'style="background:{cor}; color:#fff; text-decoration:none; font-weight:bold; font-size:18px; '
            f'padding:16px 28px; border-radius:12px; display:inline-block;">{texto}</a></p>')


def _p(texto: str) -> str:
    return f'<p style="font-size:16px; color:#333; line-height:1.55; margin:0 0 14px;">{texto}</p>'


def enviar_entrega(pedido_id: int, reenvio: bool = False) -> None:
    """'Seu livro chegou' — o link da Estante pra ela não perder o livro. Só para entrega (1009).
    reenvio=True: botão "Reenviar o e-mail" da Estante; se ela já contribuiu, sai sem o pedido de contribuição."""
    import database as db
    pedido = db.get_pedido(pedido_id)
    if not pedido or pedido['estado_id'] != db.ESTADO_CONTRIBUICAO_ENTREGUE or not pedido.get('email'):
        logger.info(f'{_TAG} Pedido #{pedido_id} não é entrega de contribuição com e-mail — ignorado')
        return
    d = _dados_envio(pedido)
    nome = _html.escape((pedido.get('contact_name') or '').split(' ')[0] or 'meu bem')
    link = f"{d['base_url']}/pedido2/{pedido['guid']}"
    contribuicao = ''
    if d['preco'] and not (reenvio and db.contribuicao_paga(pedido)):
        contribuicao = (f" Se gostar, a sua contribuição é de <strong>R$ {d['preco']}</strong>, e os seus bônus "
                        f"aparecem na Estante na hora.")
    corpo = (_p(f'Oi, {nome}! 💛') +
             _p(f"Seu livro <strong>{_html.escape(d['nome_produto'])}</strong> já está na sua Estante. "
                f"Guarde este e-mail: é só tocar no botão para abrir quando quiser.") +
             _botao(link, '📖 Abrir meu livro', d['cor_secundaria']) +
             _p(f'Dá uma olhadinha com calma.{contribuicao}') +
             _p(f"Um beijo,<br><strong>{_html.escape(d['persona'])}</strong>"))
    subject = f"{nome}, seu livro chegou 📖"
    _enviar(pedido, d, subject, corpo, '[Contribuição: link da Estante reenviado pela Estante]' if reenvio
            else '[Contribuição: livro entregue — link da Estante enviado por e-mail]')
    logger.info(f"{_TAG} ✅ Entrega do pedido #{pedido_id} enviada para {pedido['email']}")


def _corpo_lembrete(pedido: dict, d: dict, lembrete: int) -> tuple:
    nome = _html.escape((pedido.get('contact_name') or '').split(' ')[0] or 'meu bem')
    link = f"{d['base_url']}/pedido2/{pedido['guid']}?lembrete=1"
    persona = _html.escape(d['persona'])
    valor = f"de R$ {d['preco']} " if d['preco'] else ''
    if lembrete == 1:
        subject = f"{nome}, conseguiu abrir o seu livro? 💛"
        abertura = (f"Passando pra saber se você conseguiu abrir o seu livro direitinho. "
                    f"Te deixei um recadinho em áudio lá na sua Estante 🎙️")
    else:
        subject = f"{nome}, seus bônus ainda estão te esperando 🎁"
        abertura = ("Eu sei como a rotina é corrida e a gente acaba deixando algumas coisas pra depois. "
                    "Quando você conseguir um tempinho, eu vou ficar muito agradecida.")
    corpo = (_p(f'Oi, {nome}! É a {persona} 😊') +
             _p(abertura) +
             _p(f"Se você gostou do material, a sua contribuição {valor}me ajuda a continuar criando essas receitas. "
                f"Assim que ela cair, os seus bônus aparecem na Estante na hora, sem precisar mandar comprovante.") +
             _botao(link, '💛 Abrir minha Estante', d['cor_secundaria']) +
             _p('Se tiver qualquer dificuldade, é só responder este e-mail que eu te ajudo, tá bom?') +
             _p(f'Um beijo,<br><strong>{persona}</strong>'))
    return subject, corpo


def _limite_lembretes_hora() -> int:
    try:
        return max(1, int(os.getenv('CONTRIBUICAO_LEMBRETE_LIMITE_HORA', '200')))
    except ValueError:
        return 200


def executar_lembretes(agora=None) -> int:
    """Uma varredura dos lembretes. Retorna quantos foram enviados."""
    import database as db
    agora = agora or agora_sp()
    if not (HORARIO_LEMBRETE[0] <= agora.hour < HORARIO_LEMBRETE[1]):
        return 0
    enviados = 0
    for pedido in db.buscar_contribuicoes_para_lembrete():
        lembrete = int(pedido['lembrete'])
        try:
            if db.contribuicao_paga(pedido):
                # Já pagou (outro pedido): encerra a série sem enviar.
                db.marcar_lembrete_contribuicao(pedido['id'], 1)
                db.marcar_lembrete_contribuicao(pedido['id'], 2)
                continue
            # Teto por hora (envios_email_site), como a entrega e o reenvio: as entregas têm e-mail não verificado, e
            # um pico delas não pode virar centenas de lembretes que estouram a cota do Gmail do admin@.
            motivo = db.reservar_envio_email('lembrete_contribuicao', pedido['id'], None, _limite_lembretes_hora())
            if motivo == 'global':
                logger.error(f'{_TAG} ⚠️ Teto de lembretes por hora atingido ({_limite_lembretes_hora()}) — '
                             f'o resto fica para a próxima varredura')
                break
            if motivo != 'ok':
                continue
            if not db.marcar_lembrete_contribuicao(pedido['id'], lembrete):
                db.desfazer_envio_email('lembrete_contribuicao', pedido['id'])
                continue  # outra varredura já reservou
            d = _dados_envio(pedido)
            subject, corpo = _corpo_lembrete(pedido, d, lembrete)
            _enviar(pedido, d, subject, corpo, f'[Contribuição: lembrete {lembrete} enviado por e-mail]')
            enviados += 1
            logger.info(f"{_TAG} ✅ Lembrete {lembrete} do pedido #{pedido['id']} enviado")
        except Exception as e:
            # Reservado e não enviado: não tenta de novo (melhor um lembrete a menos do que dois iguais).
            logger.exception(f"{_TAG} Erro no lembrete {lembrete} do pedido #{pedido['id']}: {e}")
    return enviados
