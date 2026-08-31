"""
Entrega do e-book por e-mail com link de download.

Fluxo:
  1. Busca pedido (email, contact_name, produto_id)
  2. Busca produto (email_remetente, descricao, cores) — tabela produtos, só para personalização
  3. Busca os itens realmente comprados em `pedido_itens` (principal + bônus + bumps aceitos),
     só para o resumo em texto do que foi comprado
  4. Monta e-mail com um único link para a "Sua Estante" (/pedido/<guid>) — a página onde o
     cliente lê/salva todos os produtos que já comprou, não mais um botão de download por item
  5. Envia via Gmail API (Service Account + Domain-Wide Delegation)
  6. Marca data_envio_ebook no pedido
"""

import os
import time
import logging
from datetime import datetime

from fluxos._email_gmail import enviar as _enviar_gmail, wrapper_html as _wrapper_html

logger = logging.getLogger(__name__)


def executar(pedido_id: int) -> None:
    import database as db

    pedido  = db.get_pedido(pedido_id)
    produto = db.get_produto_disponivel_web(pedido['produto_id'])

    # Idempotência: se a task for reexecutada (ex: retry do Celery depois de uma falha
    # ocorrida DEPOIS do e-mail já ter sido enviado), não manda de novo.
    if pedido.get('data_envio_ebook'):
        logger.info(f'[EMAIL] Pedido #{pedido_id} já entregue em {pedido["data_envio_ebook"]} — ignorando reenvio')
        return

    if not pedido.get('email'):
        logger.warning(f'[EMAIL] Pedido #{pedido_id} sem e-mail — entrega ignorada')
        return

    destinatario = pedido['email']
    nome_cliente = (pedido.get('contact_name') or 'cliente').split()[0]
    remetente    = (produto or {}).get('email_remetente') or os.getenv('EMAIL_FROM', '')
    nome_produto = (produto or {}).get('nome', 'Guia Digital')
    pedido_num   = f'#{pedido_id:04d}'
    subject      = f'Pedido {pedido_num} ✅ Pronto para baixar: {nome_produto}!'

    # Personalização por produto (com fallback para valores padrão)
    nome_remetente_email = (produto or {}).get('email_nome_remetente') or 'LSN Livros'
    cor_primaria         = (produto or {}).get('email_cor_primaria') or '#2d6a1f'
    cor_secundaria       = (produto or {}).get('email_cor_secundaria') or '#b45309'

    base_url = os.getenv('APP_BASE_URL', '').rstrip('/')
    itens = [
        {'nome': item['nome'], 'tipo': item['tipo']}
        for item in db.listar_itens_pedido(pedido_id)
    ]
    link_estante = f"{base_url}/pedido/{db.garantir_guid_pedido(pedido_id)}"

    html_entrega = _corpo_html(nome_cliente, nome_produto, itens, link_estante,
                               nome_remetente_email, cor_primaria, cor_secundaria)

    resultado = _enviar_gmail(
        destinatario=destinatario,
        remetente=remetente,
        nome_remetente=f'{nome_remetente_email} — {nome_produto}',
        subject=subject,
        html=html_entrega,
    ) or {}
    db.marcar_ebook_enviado(pedido_id)

    thread_id = resultado.get('threadId')
    if thread_id:
        db.definir_gmail_thread_pedido(pedido_id, thread_id)

    # Registra o próprio e-mail de entrega na timeline de conversas — sem isso a tela "Conversa
    # E-mail" começaria vazia até a primeira resposta do cliente, e não teríamos o Message-ID
    # necessário pra ancorar o In-Reply-To/References dessa primeira resposta.
    db.salvar_mensagem_email_pedido(
        pedido_id=pedido_id,
        direcao='enviada',
        gmail_message_id=resultado.get('id') or f'local-{pedido_id}-{int(time.time())}',
        gmail_thread_id=thread_id or '',
        rfc_message_id=resultado.get('rfcMessageId'),
        assunto=subject,
        remetente=remetente,
        destinatario=destinatario,
        # Resumo curto, não o HTML inteiro — isso aqui vira "histórico" no contexto passado pro
        # agente (buscar_historico_email_conversa prefere corpo_texto quando presente); a
        # moldura da marca com botões/instruções de download não é conversa, é ruído e gasta
        # tokens à toa. O HTML completo continua guardado em corpo_html pra exibição na tela.
        corpo_texto=f'[E-book entregue: {nome_produto} — link de download enviado por e-mail]',
        corpo_html=html_entrega,
        data_mensagem=datetime.now(),
    )

    logger.info(f'[EMAIL] ✅ Pedido #{pedido_id} entregue para {destinatario}')


def _corpo_html(nome: str, nome_produto: str,
                itens: list,
                link_estante: str,
                nome_remetente: str,
                cor_primaria: str,
                cor_secundaria: str) -> str:
    """
    Gera HTML do e-mail de entrega com personalização por produto.

    Args:
        nome: Primeiro nome do cliente
        nome_produto: Descrição do produto
        itens: lista de dicts {nome, tipo} — um por item de `pedido_itens`, usada só para
               o resumo em texto do que foi comprado (bônus x order bump)
        link_estante: URL de /pedido/<guid> — página onde o cliente lê/salva tudo que já
                      comprou. É o único link enviado no e-mail (botão + texto de apoio)
        nome_remetente: Nome usado no corpo e assinatura (ex: 'Luiza', 'Luiza Carolina')
        cor_primaria: Cor do header em hex (ex: '#2d6a1f')
        cor_secundaria: Cor dos botões em hex (ex: '#b45309')
    """
    def _juntar_nomes(nomes: list) -> str:
        if len(nomes) <= 1:
            return nomes[0] if nomes else ''
        return ', '.join(nomes[:-1]) + ' e ' + nomes[-1]

    principais  = [i for i in itens if i['tipo'] == 'principal']
    bonus_itens = [i for i in itens if i['tipo'] == 'bonus']
    bump_itens  = [i for i in itens if i['tipo'] == 'bump']

    # Resumo em texto do que foi comprado x ganho de bônus x order bump — sem isso a cliente
    # pode achar que o bump (pago) veio de graça junto com o bônus, já que os dois viram parte
    # do mesmo link de acesso (a Estante) e não têm mais um botão próprio que os diferencie.
    resumo_partes = []
    if principais:
        resumo_partes.append(f"você comprou <strong>{principais[0]['nome']}</strong>")
    if bonus_itens:
        nomes_bonus = _juntar_nomes([i['nome'] for i in bonus_itens])
        resumo_partes.append(f"ganhou de bônus <strong>{nomes_bonus}</strong>")
    if bump_itens:
        nomes_bump = _juntar_nomes([i['nome'] for i in bump_itens])
        resumo_partes.append(f"e também garantiu <strong>{nomes_bump}</strong>")

    resumo_compra = ''
    if resumo_partes:
        resumo_compra = f'''
            <p style="font-size:15px; color:#333; margin:0 0 20px;">
              Resumindo: {', '.join(resumo_partes)}.
            </p>'''

    corpo_interno = f"""
            <p style="font-size:16px; color:#333; margin:0 0 16px;">
              Oi, {nome}! Aqui é a <strong>{nome_remetente}</strong>. Sua compra foi confirmada — parabéns pela decisão! 🎉
            </p>
            {resumo_compra}
            <p style="font-size:15px; color:#333; margin:0 0 20px;">
              Para acessar, é só clicar no botão abaixo. Você vai entrar direto no nosso site,
              na sua página pessoal — a <strong>Sua Estante</strong> — onde fica tudo o que você
              já comprou com a gente. Dá pra ler direto no navegador, sem instalar nada, e
              também dá pra salvar para ler depois, quando quiser.
            </p>

            <!-- Botão de acesso -->
            <table width="100%" style="background:#fff8e1; border-radius:12px;
                                        margin:0 0 20px; text-align:center;">
              <tr>
                <td style="padding:24px 20px;">
                  <a href="{link_estante}"
                     style="display:inline-block; background:{cor_secundaria}; color:#ffffff;
                            font-size:17px; font-weight:bold; text-decoration:none;
                            padding:16px 32px; border-radius:12px;">
                    📚 Acessar minha estante
                  </a>
                </td>
              </tr>
            </table>

            <!-- Alternativa: copiar e colar o link -->
            <table width="100%" style="background:#f8f8f8; border-left:4px solid #555;
                                        border-radius:0 12px 12px 0; margin:0 0 24px;">
              <tr>
                <td style="padding:16px 20px;">
                  <p style="font-size:14px; color:#333; margin:0 0 10px;">
                    <strong>Não conseguiu clicar no botão?</strong> Sem problema: copie o link
                    abaixo e cole na barra de endereços do navegador do seu celular ou
                    computador (o mesmo lugar onde você digitaria "google.com"):
                  </p>
                  <p style="font-size:13px; font-family:monospace; color:{cor_primaria};
                            background:#ffffff; border:1px solid #ddd; border-radius:8px;
                            padding:10px 12px; margin:0; word-break:break-all;">
                    {link_estante}
                  </p>
                </td>
              </tr>
            </table>

            <p style="font-size:14px; color:#555; margin:0 0 8px;">
              Esse link é pessoal — é ele que abre sua Estante, e você pode acessar de
              qualquer celular ou computador, quantas vezes quiser.
            </p>
            <p style="font-size:14px; color:#555; margin:0 0 24px;">
              💡 <strong>Dica:</strong> guarde este e-mail. Sempre que quiser reler ou salvar
              seu material, é só voltar aqui e clicar no link novamente.
            </p>

            <p style="font-size:14px; color:#555; margin:0 0 24px;">
              Qualquer dúvida é só responder este e-mail. Estou aqui para ajudar! 😊
            </p>

            <p style="font-size:14px; color:#666; margin:0;">
              Com carinho,<br>
              <strong style="color:{cor_primaria};">{nome_remetente}</strong>
            </p>"""

    rodape = ('Você recebeu este e-mail porque realizou uma compra em lsnlivros.com.br.<br>'
               'Guarde este e-mail para ter sempre acesso aos seus produtos.')

    return _wrapper_html(
        titulo_header=f'✅ Seu {nome_produto} chegou, {nome}!',
        corpo_interno_html=corpo_interno,
        nome_remetente=nome_remetente,
        cor_primaria=cor_primaria,
        cor_secundaria=cor_secundaria,
        rodape=rodape,
    )
