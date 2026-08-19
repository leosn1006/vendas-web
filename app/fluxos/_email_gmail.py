"""
Envio de e-mail via Gmail API (Service Account + Domain-Wide Delegation).

Helper compartilhado entre os fluxos que enviam e-mail (entrega_pedido_email,
fluxo_followup_web) — evita duplicar o boilerplate de credencial/Gmail API em cada um.
"""

import os
import json as _json
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr, make_msgid

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

_GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.send']


def enviar(destinatario: str, remetente: str, nome_remetente: str,
          subject: str, html: str, imagens_inline: list = None,
          thread_id: str = None, in_reply_to: str = None) -> dict:
    """
    imagens_inline: lista opcional de {'cid': str, 'dados': bytes, 'subtype': str}.
    Referencie no HTML via <img src="cid:{cid}">. Anexo MIME inline (Content-ID),
    não data: URI — Yahoo Mail e Outlook removem imagens embutidas via data: URI,
    mas suportam normalmente o padrão cid: (usado por praticamente todo cliente de e-mail).

    thread_id: threadId do Gmail pra continuar uma conversa existente (opcional).
    in_reply_to: Message-ID (header RFC 2822) da última mensagem da thread — vira
    In-Reply-To/References do e-mail enviado. É isso que realmente faz o Gmail (e outros
    clientes) agruparem a conversa; threadId sozinho não é suficiente se o assunto não bater
    com o da thread (a API do Gmail pode até rejeitar o threadId nesse caso).

    Retorna o resultado bruto da API (dict com 'id'/'threadId') mais 'rfcMessageId' — o
    Message-ID que este envio gerou, pra ser guardado e usado como in_reply_to na próxima
    resposta dessa mesma conversa.
    """
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

    msg = MIMEMultipart('related') if imagens_inline else MIMEMultipart('alternative')
    msg['to']      = destinatario
    msg['from']    = formataddr((nome_remetente, remetente))
    msg['subject'] = subject
    dominio_msgid = remetente.split('@')[-1] if '@' in (remetente or '') else 'lsnlivros.com.br'
    message_id = make_msgid(domain=dominio_msgid)
    msg['Message-ID'] = message_id
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
        msg['References']  = in_reply_to
    msg.attach(MIMEText(html, 'html'))

    for img in (imagens_inline or []):
        parte = MIMEImage(img['dados'], _subtype=img.get('subtype', 'png'))
        parte.add_header('Content-ID', f"<{img['cid']}>")
        parte.add_header('Content-Disposition', 'inline', filename=f"{img['cid']}.{img.get('subtype', 'png')}")
        msg.attach(parte)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body = {'raw': raw}
    if thread_id:
        body['threadId'] = thread_id
    resultado = service.users().messages().send(userId='me', body=body).execute()
    resultado['rfcMessageId'] = message_id
    return resultado


def wrapper_html(titulo_header: str, corpo_interno_html: str, nome_remetente: str,
                  cor_primaria: str, cor_secundaria: str, rodape: str) -> str:
    """
    Moldura HTML compartilhada por todos os e-mails transacionais (entrega, resposta, followup):
    cabeçalho com gradiente na cor do produto, corpo livre (`corpo_interno_html`), rodapé fixo.
    Extraída de entrega_pedido_email._corpo_html() para reuso — não altera o HTML gerado por ela.
    """
    cor_primaria_clara = lighten_hex(cor_primaria, 0.3)

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

        <!-- Cabeçalho -->
        <tr>
          <td style="background:linear-gradient(135deg,{cor_primaria},{cor_primaria_clara}); padding:28px 32px; text-align:center;">
            <h1 style="color:#ffffff; font-size:24px; font-weight:bold; margin:0; font-family:Georgia,serif;">
              {titulo_header}
            </h1>
          </td>
        </tr>

        <!-- Corpo -->
        <tr>
          <td style="padding:32px;">
{corpo_interno_html}
          </td>
        </tr>

        <!-- Rodapé -->
        <tr>
          <td style="background:#f0f0f0; padding:16px 32px; text-align:center;">
            <p style="font-size:11px; color:#999; margin:0;">
              {rodape}
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def lighten_hex(hex_color: str, amount: float = 0.3) -> str:
    """Clareia uma cor hex (#RRGGBB) movendo cada componente em direção ao branco."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    r, g, b = min(255, r), min(255, g), min(255, b)
    return f'#{r:02x}{g:02x}{b:02x}'
