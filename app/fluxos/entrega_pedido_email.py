"""
Entrega do e-book por e-mail com link de download.

Fluxo:
  1. Busca pedido (email, contact_name, produto_id)
  2. Busca produto (email_remetente, descricao, cores) — tabela produtos, só para personalização
  3. Busca os itens realmente comprados em `pedido_itens` (principal + bônus + bumps aceitos)
  4. Monta e-mail com um botão de download por item, apontando para a rota protegida por
     pedido_id (em vez de linkar direto pro arquivo estático) — sem anexo
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
        {
            'nome': item['nome'],
            'tipo': item['tipo'],
            'url': f"{base_url}/api/v1/pedido/{pedido_id}/itens/{item['id']}/download",
        }
        for item in db.listar_itens_pedido(pedido_id)
    ]

    html_entrega = _corpo_html(nome_cliente, nome_produto, itens,
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
                nome_remetente: str,
                cor_primaria: str,
                cor_secundaria: str) -> str:
    """
    Gera HTML do e-mail de entrega com personalização por produto.

    Args:
        nome: Primeiro nome do cliente
        nome_produto: Descrição do produto
        itens: lista de dicts {nome, tipo, url} — um por item de `pedido_itens`
               (tipo='principal' vira o botão grande; 'bonus'/'bump' viram botões extras)
        nome_remetente: Nome usado no corpo e assinatura (ex: 'Luiza', 'Luiza Carolina')
        cor_primaria: Cor do header em hex (ex: '#2d6a1f')
        cor_secundaria: Cor dos botões em hex (ex: '#b45309')
    """
    def _botao(item: dict, principal: bool = False) -> str:
        rotulo = f"📥 Baixar meu {nome_produto}" if principal else f"🎁 Baixar {item['nome']}"
        tamanho = '17px' if principal else '15px'
        padding = '16px 32px' if principal else '12px 24px'
        return f'''
      <a href="{item['url']}"
         style="display:inline-block; background:{cor_secundaria}; color:#ffffff;
                font-size:{tamanho}; font-weight:bold; text-decoration:none;
                padding:{padding}; border-radius:12px; margin:8px 0;">
        {rotulo}
      </a>'''

    principais = [i for i in itens if i['tipo'] == 'principal']
    extras     = [i for i in itens if i['tipo'] != 'principal']

    btn_principal = _botao(principais[0], principal=True) if principais else ''

    secao_bonus = ''
    if extras:
        botoes_extras = ''.join(_botao(i) for i in extras)
        secao_bonus = f'''
            <p style="font-size:14px; color:#555; margin:0 0 8px;">
              Você também ganhou:
            </p>
            {botoes_extras}
    '''

    corpo_interno = f"""
            <p style="font-size:16px; color:#333; margin:0 0 16px;">
              Aqui é a <strong>{nome_remetente}</strong>. Seu pagamento foi confirmado — parabéns pela decisão! 🎉
            </p>

            <!-- Botões de download -->
            <table width="100%" style="background:#fff8e1; border-radius:12px;
                                        margin:0 0 28px; text-align:center;">
              <tr>
                <td style="padding:24px 20px;">
                  <p style="font-size:15px; font-weight:bold; color:#1a4012; margin:0 0 16px;">
                    Toque no botão abaixo para baixar:
                  </p>
                  {btn_principal}
                  {secao_bonus}
                </td>
              </tr>
            </table>

            <!-- iPhone -->
            <table width="100%" style="background:#f8f8f8; border-left:4px solid #555;
                                        border-radius:0 12px 12px 0; margin:0 0 16px;">
              <tr>
                <td style="padding:16px 20px;">
                  <p style="font-size:15px; font-weight:bold; color:#333; margin:0 0 10px;">
                    📱 Usando iPhone?
                  </p>
                  <ol style="font-size:14px; color:#444; line-height:1.9; margin:0; padding-left:20px;">
                    <li>Toque no botão marrom acima.</li>
                    <li>O arquivo abre — toque nos <strong>3 pontinhos ⋯</strong> no canto superior direito.</li>
                    <li>Toque em <strong>"Salvar em Arquivos"</strong> → escolha <strong>"No meu iPhone"</strong>.</li>
                  </ol>
                  <p style="font-size:13px; color:{cor_primaria}; font-weight:bold; margin:10px 0 0;">
                    ✅ Pronto! Fica salvo para sempre, mesmo sem internet.
                  </p>
                </td>
              </tr>
            </table>

            <!-- Android -->
            <table width="100%" style="background:#f8f8f8; border-left:4px solid #555;
                                        border-radius:0 12px 12px 0; margin:0 0 24px;">
              <tr>
                <td style="padding:16px 20px;">
                  <p style="font-size:15px; font-weight:bold; color:#333; margin:0 0 10px;">
                    🤖 Usando Android?
                  </p>
                  <ol style="font-size:14px; color:#444; line-height:1.9; margin:0; padding-left:20px;">
                    <li>Toque no botão acima.</li>
                    <li>O arquivo baixa automaticamente.</li>
                    <li>Abra o app <strong>"Arquivos"</strong> (ou <strong>"Meus Arquivos"</strong>) → pasta <strong>Downloads</strong>.</li>
                  </ol>
                  <p style="font-size:13px; color:{cor_primaria}; font-weight:bold; margin:10px 0 0;">
                    ✅ Pronto! Ele fica salvo no seu celular.
                  </p>
                </td>
              </tr>
            </table>

            <!-- Dica WhatsApp -->
            <table width="100%" style="background:#fff8e1; border:1px dashed #f59e0b;
                                        border-radius:12px; margin:0 0 24px;">
              <tr>
                <td style="padding:14px 20px;">
                  <p style="font-size:14px; color:{cor_secundaria}; margin:0;">
                    💡 <strong>Dica rápida:</strong> encaminhe este e-mail para você mesma no
                    <strong>WhatsApp</strong> — assim você nunca perde o link!
                  </p>
                </td>
              </tr>
            </table>

            <p style="font-size:14px; color:#555; margin:0 0 24px;">
              Qualquer dúvida é só responder este e-mail. Estou aqui para ajudar! 😊
            </p>

            <p style="font-size:14px; color:#666; margin:0;">
              Com carinho,<br>
              <strong style="color:{cor_primaria};">{nome_remetente}</strong>
            </p>"""

    rodape = ('Você recebeu este e-mail porque realizou uma compra em lsnlivros.com.br.<br>'
               'Guarde este e-mail para ter sempre acesso ao seu link de download.')

    return _wrapper_html(
        titulo_header=f'✅ Seu {nome_produto} chegou, {nome}!',
        corpo_interno_html=corpo_interno,
        nome_remetente=nome_remetente,
        cor_primaria=cor_primaria,
        cor_secundaria=cor_secundaria,
        rodape=rodape,
    )
