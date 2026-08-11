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
from email.utils import formataddr

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

_GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.send']


def enviar(destinatario: str, remetente: str, nome_remetente: str,
          subject: str, html: str, imagens_inline: list = None) -> None:
    """
    imagens_inline: lista opcional de {'cid': str, 'dados': bytes, 'subtype': str}.
    Referencie no HTML via <img src="cid:{cid}">. Anexo MIME inline (Content-ID),
    não data: URI — Yahoo Mail e Outlook removem imagens embutidas via data: URI,
    mas suportam normalmente o padrão cid: (usado por praticamente todo cliente de e-mail).
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
    msg.attach(MIMEText(html, 'html'))

    for img in (imagens_inline or []):
        parte = MIMEImage(img['dados'], _subtype=img.get('subtype', 'png'))
        parte.add_header('Content-ID', f"<{img['cid']}>")
        parte.add_header('Content-Disposition', 'inline', filename=f"{img['cid']}.{img.get('subtype', 'png')}")
        msg.attach(parte)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()


def lighten_hex(hex_color: str, amount: float = 0.3) -> str:
    """Clareia uma cor hex (#RRGGBB) movendo cada componente em direção ao branco."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    r, g, b = min(255, r), min(255, g), min(255, b)
    return f'#{r:02x}{g:02x}{b:02x}'
