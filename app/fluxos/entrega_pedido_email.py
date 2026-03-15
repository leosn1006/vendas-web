"""
Entrega do e-book por e-mail com link de download.

Fluxo:
  1. Busca pedido (email, contact_name, produto_id)
  2. Busca produto (url_pdf, url_pdf_bonus, email_remetente, descricao) — tabela produtos
  3. Monta e-mail com botões de download (sem anexo)
  4. Envia via Gmail API (Service Account + Domain-Wide Delegation)
  5. Marca data_envio_ebook no pedido
"""

import os
import json as _json
import logging
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

_GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.send']


def executar(pedido_id: int) -> None:
    import database as db

    pedido  = db.get_pedido(pedido_id)
    produto = db.get_produto_disponivel_web(pedido['produto_id'])

    if not pedido.get('email'):
        logger.warning(f'[EMAIL] Pedido #{pedido_id} sem e-mail — entrega ignorada')
        return

    destinatario = pedido['email']
    nome_cliente = (pedido.get('contact_name') or '').split()[0] or 'cliente'
    remetente    = (produto or {}).get('email_remetente') or os.getenv('EMAIL_FROM', '')
    nome_produto = (produto or {}).get('descricao', 'Guia Digital')
    pedido_num   = f'#{pedido_id:04d}'
    subject      = f'Pedido {pedido_num} ✅ Seu {nome_produto} está pronto para baixar!'

    base_url = os.getenv('APP_BASE_URL', '').rstrip('/')
    url_download       = f"{base_url}/static/arquivos/{produto['url_pdf']}"       if produto and produto.get('url_pdf')       else None
    url_download_bonus = f"{base_url}/static/arquivos/{produto['url_pdf_bonus']}" if produto and produto.get('url_pdf_bonus') else None

    _enviar(
        destinatario=destinatario,
        remetente=remetente,
        subject=subject,
        html=_corpo_html(nome_cliente, nome_produto, url_download, url_download_bonus),
    )
    db.marcar_ebook_enviado(pedido_id)
    logger.info(f'[EMAIL] ✅ Pedido #{pedido_id} entregue para {destinatario}')


def _enviar(destinatario: str, remetente: str, subject: str, html: str) -> None:
    # Usa sempre a SA do produto 6 (conta empresarial com Google Workspace)
    # TODO: migrar produto 1 para Workspace e usar GOOGLE_SA_JSON_P{produto_id}
    sa_json = os.getenv('GOOGLE_SA_JSON_P6')
    if not sa_json:
        raise RuntimeError('[EMAIL] GOOGLE_SA_JSON_P6 não configurada')

    creds = Credentials.from_service_account_info(
        _json.loads(sa_json),
        scopes=_GMAIL_SCOPES,
        subject='admin@lsnlivros.com.br',  # TODO: usar remetente quando produto 1 migrar para Workspace
        # subject=remetente,
    )
    service = build('gmail', 'v1', credentials=creds)

    msg = MIMEMultipart('alternative')
    msg['to']      = destinatario
    msg['from']    = remetente
    msg['subject'] = subject
    msg.attach(MIMEText(html, 'html'))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()


def _corpo_html(nome: str, nome_produto: str,
                url_download: str | None,
                url_download_bonus: str | None) -> str:

    btn_principal = f'''
      <a href="{url_download}"
         style="display:inline-block; background:#2d6a1f; color:#ffffff;
                font-size:17px; font-weight:bold; text-decoration:none;
                padding:16px 32px; border-radius:12px; margin:8px 0;">
        📥 Baixar meu {nome_produto}
      </a>''' if url_download else ''

    btn_bonus = f'''
      <a href="{url_download_bonus}"
         style="display:inline-block; background:#b45309; color:#ffffff;
                font-size:15px; font-weight:bold; text-decoration:none;
                padding:12px 24px; border-radius:12px; margin:8px 0;">
        🎁 Baixar meu Bônus
      </a>''' if url_download_bonus else ''

    secao_bonus = f'''
            <p style="font-size:14px; color:#555; margin:0 0 8px;">
              Você também ganhou um bônus especial:
            </p>
            {btn_bonus}
    ''' if url_download_bonus else ''

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; background:#f9f5ef; margin:0; padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9f5ef; padding:24px 0;">
    <tr><td align="center">
      <table width="100%" style="max-width:560px; background:#ffffff; border-radius:16px;
                                  overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.08);">

        <!-- Cabeçalho verde -->
        <tr>
          <td style="background:linear-gradient(135deg,#1a4012,#2d6a1f); padding:28px 32px; text-align:center;">
            <h1 style="color:#ffffff; font-size:22px; margin:0; font-family:Georgia,serif;">
              ✅ Seu {nome_produto} chegou, {nome}!
            </h1>
          </td>
        </tr>

        <!-- Corpo -->
        <tr>
          <td style="padding:32px;">

            <p style="font-size:16px; color:#333; margin:0 0 16px;">
              Aqui é a <strong>Luiza</strong>. Seu pagamento foi confirmado — parabéns pela decisão! 🎉
            </p>

            <!-- Botões de download -->
            <table width="100%" style="background:#f0f7eb; border-radius:12px;
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
                    <li>Toque no botão verde acima.</li>
                    <li>O arquivo abre — toque nos <strong>3 pontinhos ⋯</strong> no canto superior direito.</li>
                    <li>Toque em <strong>"Salvar em Arquivos"</strong> → escolha <strong>"No meu iPhone"</strong>.</li>
                  </ol>
                  <p style="font-size:13px; color:#2d6a1f; font-weight:bold; margin:10px 0 0;">
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
                    <li>Toque no botão verde acima.</li>
                    <li>O arquivo baixa automaticamente.</li>
                    <li>Abra o app <strong>"Arquivos"</strong> (ou <strong>"Meus Arquivos"</strong>) → pasta <strong>Downloads</strong>.</li>
                  </ol>
                  <p style="font-size:13px; color:#2d6a1f; font-weight:bold; margin:10px 0 0;">
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
                  <p style="font-size:14px; color:#b45309; margin:0;">
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
              <strong style="color:#1a4012;">Luiza — Guia Pães Saudáveis</strong>
            </p>
          </td>
        </tr>

        <!-- Rodapé -->
        <tr>
          <td style="background:#f0f0f0; padding:16px 32px; text-align:center;">
            <p style="font-size:11px; color:#999; margin:0;">
              Você recebeu este e-mail porque realizou uma compra em lsnlivros.com.br.<br>
              Guarde este e-mail para ter sempre acesso ao seu link de download.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
