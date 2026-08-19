"""
Polling do Gmail (rodando a cada 10min via Celery beat, ver tasks.verificar_emails_clientes) —
lê as respostas de clientes à caixa admin@lsnlivros.com.br, associa ao pedido certo e aciona o
agente de e-mail dedicado (app/agente_resposta_email_produto.py) para sugerir uma resposta,
sempre em fila de aprovação humana (notificacoes_pedido, motivo='sugestao_resposta_email').

Threading: casamento primário por gmail_thread_id (nativo da API do Gmail, sobrevive a
assunto editado/traduzido); fallback por regex #NNNN no assunto, validado contra o e-mail do
remetente antes de aceitar (evita casar um número de pedido forjado no assunto).

E-mails que não batem com nenhum pedido ficam como não lidos — sem tela própria nesta fase,
por decisão de produto (ver plano). Bounces/autoresponders são filtrados antes de qualquer
persistência.
"""

import os
import re
import base64
import logging
import time
from datetime import datetime
from pathlib import Path
from email.utils import parseaddr

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

_GMAIL_SCOPES_LEITURA = ['https://www.googleapis.com/auth/gmail.modify']
_PREFIXOS_BOUNCE = ('mailer-daemon@', 'postmaster@', 'noreply@', 'no-reply@', 'donotreply@')
_TAMANHO_MAX_MB = 25
_REGEX_PEDIDO_ASSUNTO = re.compile(r'#(\d{4,})')
_STORAGE_ANEXOS = Path(__file__).parent / 'storage' / 'email_anexos'


def resolver_caminho_anexo(caminho_relativo: str) -> Path | None:
    """Resolve o caminho absoluto de um anexo salvo por este módulo, validando que fica dentro
    do diretório de storage esperado (defesa contra path traversal). Usado pela rota do admin
    que serve o download do anexo."""
    candidato = (Path(__file__).parent / caminho_relativo).resolve()
    base = _STORAGE_ANEXOS.resolve()
    if candidato != base and base not in candidato.parents:
        return None
    return candidato if candidato.is_file() else None


def _service():
    sa_json = os.getenv('GOOGLE_SA_JSON_P6')
    if not sa_json:
        raise RuntimeError('[EMAIL-CONVERSAS] GOOGLE_SA_JSON_P6 não configurada')
    import json as _json
    creds = Credentials.from_service_account_info(
        _json.loads(sa_json),
        scopes=_GMAIL_SCOPES_LEITURA,
        subject='admin@lsnlivros.com.br',
    )
    return build('gmail', 'v1', credentials=creds)


def _e_bounce_ou_autoresponder(remetente_header: str, headers: dict) -> bool:
    remetente_lower = (remetente_header or '').lower()
    if any(prefixo in remetente_lower for prefixo in _PREFIXOS_BOUNCE):
        return True
    auto_submitted = (headers.get('auto-submitted') or 'no').lower()
    return auto_submitted != 'no'


def _decodificar_b64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + '==')


def _header_parte(part: dict, nome: str) -> str:
    for h in part.get('headers', []) or []:
        if h.get('name', '').lower() == nome.lower():
            return h.get('value', '')
    return ''


def _extrair_conteudo(payload: dict) -> tuple[str, str, list]:
    """Percorre as partes MIME da mensagem: retorna (texto_plano, html, anexos).
    anexos = lista de {filename, mime_type, attachment_id, data, size}."""
    texto, html, anexos = '', '', []

    def _walk(part):
        nonlocal texto, html
        mime = part.get('mimeType', '')
        filename = part.get('filename') or ''
        body = part.get('body', {}) or {}
        # Content-Disposition: inline com filename é típico de logo/assinatura embutida no
        # corpo do e-mail (Outlook, Apple Mail…) — não é um anexo que o cliente quis mandar,
        # então não entra na lista de anexos (nem no texto/html — só é descartada).
        disposicao = _header_parte(part, 'Content-Disposition').lower()
        if filename and (body.get('attachmentId') or body.get('data')) and not disposicao.startswith('inline'):
            anexos.append({
                'filename': filename,
                'mime_type': mime,
                'attachment_id': body.get('attachmentId'),
                'data': body.get('data'),
                'size': body.get('size', 0),
            })
            return
        if mime == 'text/plain' and body.get('data') and not texto:
            texto = _decodificar_b64url(body['data']).decode('utf-8', errors='replace')
        elif mime == 'text/html' and body.get('data') and not html:
            html = _decodificar_b64url(body['data']).decode('utf-8', errors='replace')
        for sub in part.get('parts', []) or []:
            _walk(sub)

    _walk(payload)
    return texto.strip(), html.strip(), anexos


def _salvar_anexo(service, message_id: str, pedido_id: int, anexo: dict) -> dict | None:
    if anexo['data']:
        raw = anexo['data']
    else:
        att = service.users().messages().attachments().get(
            userId='me', messageId=message_id, id=anexo['attachment_id']).execute()
        raw = att['data']
    conteudo = _decodificar_b64url(raw)

    tamanho_mb = len(conteudo) / 1024 / 1024
    if tamanho_mb > _TAMANHO_MAX_MB:
        logger.warning(f"[EMAIL-CONVERSAS] ⚠️ Anexo '{anexo['filename']}' grande demais "
                       f"({tamanho_mb:.1f} MB > {_TAMANHO_MAX_MB} MB) — ignorado")
        return None

    agora = datetime.now()
    diretorio = _STORAGE_ANEXOS / str(agora.year) / f'{agora.month:02d}' / f'{agora.day:02d}'
    diretorio.mkdir(parents=True, exist_ok=True)

    nome_seguro = secure_filename(anexo['filename']) or 'anexo'
    nome_final = f'pedido_{pedido_id}_{int(time.time())}_{nome_seguro}'
    caminho_final = diretorio / nome_final
    with open(caminho_final, 'wb') as f:
        f.write(conteudo)

    return {
        'nome_arquivo': anexo['filename'],
        'caminho_arquivo': str(caminho_final.relative_to(Path(__file__).parent)),
        'mime_type': anexo['mime_type'],
        'tamanho_bytes': len(conteudo),
    }


def _resolver_pedido(db, thread_id: str, assunto: str, remetente_header: str):
    pedido = db.resolver_pedido_por_thread_gmail(thread_id)
    if pedido:
        return pedido

    match = _REGEX_PEDIDO_ASSUNTO.search(assunto or '')
    if not match:
        return None

    candidato = db.get_pedido(int(match.group(1)))
    if not candidato or candidato.get('estado_id') not in (1000, 1001, 1002, 1003, 1004):
        return None

    _, email_remetente = parseaddr(remetente_header or '')
    if not email_remetente or (candidato.get('email') or '').lower() != email_remetente.lower():
        return None

    # Só ancora se o pedido ainda não tem thread — se já tem (ex: thread da entrega original),
    # não sobrescreve: essa mensagem pode ser um e-mail novo/avulso citando o pedido, e
    # sobrescrever perderia a thread original, órfã pra sempre se a próxima resposta do cliente
    # não repetir o "#NNNN" no assunto.
    if not candidato.get('gmail_thread_id'):
        db.definir_gmail_thread_pedido(candidato['id'], thread_id)
    return candidato


def _marcar_como_lida(service, message_id: str) -> None:
    service.users().messages().modify(
        userId='me', id=message_id, body={'removeLabelIds': ['UNREAD']}).execute()


def _processar_mensagem(service, db, message_id: str) -> None:
    full = service.users().messages().get(userId='me', id=message_id, format='full').execute()
    headers = {h['name'].lower(): h['value'] for h in full.get('payload', {}).get('headers', [])}
    remetente = headers.get('from', '')

    if _e_bounce_ou_autoresponder(remetente, headers):
        logger.info(f"[EMAIL-CONVERSAS] ↪️ Ignorando bounce/autoresponder: {remetente}")
        _marcar_como_lida(service, message_id)
        return

    thread_id = full.get('threadId', '')
    assunto = headers.get('subject', '')

    pedido = _resolver_pedido(db, thread_id, assunto, remetente)
    if not pedido:
        logger.info(f"[EMAIL-CONVERSAS] ❓ Mensagem sem pedido correspondente (assunto: "
                   f"'{assunto[:80]}') — deixando não lida para revisão manual no Gmail")
        return

    texto, html, anexos_brutos = _extrair_conteudo(full.get('payload', {}))
    internal_date = datetime.fromtimestamp(int(full['internalDate']) / 1000)

    mensagem_id = db.salvar_mensagem_email_pedido(
        pedido_id=pedido['id'],
        direcao='recebida',
        gmail_message_id=full['id'],
        gmail_thread_id=thread_id,
        rfc_message_id=headers.get('message-id'),
        assunto=assunto,
        remetente=remetente,
        destinatario=headers.get('to', ''),
        corpo_texto=texto,
        corpo_html=html,
        data_mensagem=internal_date,
    )
    _marcar_como_lida(service, message_id)

    if mensagem_id is None:
        return  # já processada em rodada anterior (dedupe por gmail_message_id)

    for anexo in anexos_brutos:
        salvo = _salvar_anexo(service, message_id, pedido['id'], anexo)
        if salvo:
            db.salvar_anexo_email_mensagem(mensagem_id, salvo['nome_arquivo'],
                                           salvo['caminho_arquivo'], salvo['mime_type'],
                                           salvo['tamanho_bytes'])

    logger.info(f"[EMAIL-CONVERSAS] ✅ Mensagem persistida — pedido #{pedido['id']}, "
               f"{len(anexos_brutos)} anexo(s), texto: {len(texto)} chars")

    if pedido.get('email_bloqueado'):
        logger.info(f"[EMAIL-CONVERSAS] 🔕 Pedido #{pedido['id']} com e-mail bloqueado — sem sugestão da IA")
        return
    if not texto:
        logger.info(f"[EMAIL-CONVERSAS] 📎 Mensagem sem texto (só anexo) — sem sugestão da IA, "
                   f"aguardando revisão manual")
        return

    _acionar_agente(db, pedido, texto)


def _acionar_agente(db, pedido: dict, texto: str) -> None:
    produto = db.get_produto_disponivel_web(pedido['produto_id'])
    if not produto:
        logger.warning(f"[EMAIL-CONVERSAS] ⚠️ Produto {pedido['produto_id']} não disponível para "
                       f"web — pedido #{pedido['id']} sem sugestão da IA")
        return

    from agente_resposta_email_produto import responder_cliente_email_com_historico_produto
    historico = db.buscar_historico_email_conversa(pedido['id'], limite=10)
    resposta = responder_cliente_email_com_historico_produto(texto, historico, produto, pedido)

    if resposta:
        db.criar_sugestao_resposta_email(pedido['id'], produto['id'], resposta)
        logger.info(f"[EMAIL-CONVERSAS] 🤖 Sugestão de resposta criada — pedido #{pedido['id']}")
    # resposta None: agente já escalou (ou falhou) e criou sua própria notificação


def executar() -> None:
    import database as db

    service = _service()
    resultado = service.users().messages().list(userId='me', q='is:unread -in:sent', maxResults=50).execute()
    mensagens = resultado.get('messages', [])

    logger.info(f"[EMAIL-CONVERSAS] 📬 {len(mensagens)} mensagem(ns) não lida(s) encontrada(s)")

    for msg in mensagens:
        try:
            _processar_mensagem(service, db, msg['id'])
        except Exception as exc:
            logger.error(f"[EMAIL-CONVERSAS] ❌ Erro ao processar mensagem {msg['id']}: {exc}")
