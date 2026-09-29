"""
Leitor da caixa de atendimento (a cada 10min via Celery beat, ver tasks.verificar_emails_clientes).

Para cada e-mail novo na caixa de entrada:
  1. ruído (bounce, autoresponder, newsletter, Google/bancos) → marcador Ruído e arquivado
  2. triagem: vendas x administrativo e a categoria (agente_triagem_email; atalhos sem IA para
     e-mail em branco na chave PIX e agradecimento curto)
  3. vínculo com o pedido (fluxos/email_vinculo: thread, nº do pedido, e-mail, telefone, CPF,
     comprovante, nome)
  4. decisão e resposta pronta (fluxos/email_respostas) → fila global do admin
     (/admin/atendimento-email), registrada em emails_atendimento
  5. marcadores do Gmail espelhando o estado; envio automático só para os tipos liberados em
     EMAIL_ATENDIMENTO_AUTO_TIPOS (fase 1: nenhum — tudo passa por 1 clique no admin)

O leitor não depende mais de "não lido": o que já foi processado recebe o marcador
Sistema/Processado (antes, um e-mail aberto no Gmail antes do robô sumia da fila). Fora de
produção só lê uma caixa de teste explícita (ver _gmail_labels.caixa_atendimento).
"""

import os
import re
import base64
import logging
import time
import html as _html_entities  # nome diferente da variável local `html` (corpo HTML da mensagem)
from datetime import datetime
from pathlib import Path
from email.utils import parseaddr

from werkzeug.utils import secure_filename

from fluxos import _gmail_labels as _labels

logger = logging.getLogger(__name__)

_PREFIXOS_BOUNCE = ('mailer-daemon@', 'postmaster@', 'noreply@', 'no-reply@', 'donotreply@')
# Remetentes automáticos: o endereço COMEÇA com a marca, em inglês ou português (ex:
# nao-responder-serem@ da prefeitura, no_reply.notas@…) — no meio pode ser nome de cliente
_REGEX_NAO_RESPONDA = re.compile(
    r'(?:^|[<\s"\'])(?:no[-_.]?reply|do[-_.]?not[-_.]?reply|n[aã]o[-_.]?respond)[^@\s]*@', re.IGNORECASE)
_TAMANHO_MAX_MB = 25
# Base = /app (raiz do volume montado em ./storage:/app/storage — mesma pasta persistente que
# whatsapp_upload.py usa pra comprovantes). Diferente de Path(__file__).parent, que seria
# /app/fluxos e NÃO está no volume — qualquer rebuild da imagem apagaria os anexos recebidos,
# mesmo com a linha continuando no banco (bug real, pego em teste).
_BASE_APP = Path(__file__).parent.parent
_STORAGE_ANEXOS = _BASE_APP / 'storage' / 'email_anexos'


def resolver_caminho_anexo(caminho_relativo: str) -> Path | None:
    """Resolve o caminho absoluto de um anexo salvo por este módulo, validando que fica dentro
    do diretório de storage esperado (defesa contra path traversal). Usado pela rota do admin
    que serve o download do anexo."""
    candidato = (_BASE_APP / caminho_relativo).resolve()
    base = _STORAGE_ANEXOS.resolve()
    if candidato != base and base not in candidato.parents:
        return None
    return candidato if candidato.is_file() else None


def _e_bounce_ou_autoresponder(remetente_header: str, headers: dict) -> bool:
    remetente_lower = (remetente_header or '').lower()
    if any(prefixo in remetente_lower for prefixo in _PREFIXOS_BOUNCE) or _REGEX_NAO_RESPONDA.search(remetente_lower):
        return True
    auto_submitted = (headers.get('auto-submitted') or 'no').lower()
    return auto_submitted != 'no'


def _decodificar_b64url(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + '==')


_REGEX_CITACAO_TEXTO = re.compile(
    r'(?:^|\n)[ \t]*(?:'
    # Gmail/Apple: "Em qua., 26 de ago. de 2026, 21:04, Luiza — Temperos… <admin@…> escreveu:" —
    # com o nome da persona passa de 80 caracteres e o Gmail costuma quebrar em duas linhas
    r'(?:em|on)\s[^\n]{0,250}(?:\n[^\n]{0,250})?\s(?:escreveu|wrote)\s*:'
    r'|-{2,}\s*(?:mensagem original|original message)\s*-{2,}'
    r'|_{10,}'                                                          # separador do Outlook
    r'|(?:de|from):[^\n]*\n[ \t]*(?:enviad[ao]|sent|data|date)\s*:'   # cabeçalho Outlook/BOL/UOL
    r'|>'                                                               # primeira linha citada
    r')',
    re.IGNORECASE,
)


def _truncar_no_blockquote(html_str: str) -> str:
    """Corta o HTML no primeiro <blockquote> — é onde Gmail/Apple Mail/Outlook embutem o
    e-mail citado numa resposta. Sem isso, toda resposta traria o e-mail de entrega inteiro
    (com todos os botões/HTML) de volta como se fosse parte da pergunta do cliente."""
    if not html_str:
        return html_str
    m = re.search(r'<blockquote', html_str, re.IGNORECASE)
    return html_str[:m.start()] if m else html_str


def _texto_de_html(html_str: str) -> str:
    """Fallback pra clientes de e-mail que só mandam text/html, sem text/plain (comum no Apple
    Mail/webmail) — sem isso a mensagem ficava com corpo_texto vazio e a IA nunca era acionada."""
    sem_tags = re.sub(r'<[^>]+>', ' ', html_str or '')
    sem_tags = _html_entities.unescape(sem_tags)
    return re.sub(r'\s+', ' ', sem_tags).strip()


def _cortar_citacao(texto: str) -> str:
    """Corta texto plano no cabeçalho de citação ('Em ... escreveu:' / 'On ... wrote:') —
    mesma ideia do _truncar_no_blockquote, mas pra quando o texto já veio de text/plain."""
    if not texto:
        return texto
    m = _REGEX_CITACAO_TEXTO.search(texto)
    return texto[:m.start()].strip() if m else texto.strip()


_REGEX_ASSINATURA_MOBILE = re.compile(
    r'(?:^|\n)\s*(enviado (do|via) meu \w+|sent from my \w+|get outlook for \w+)\s*$',
    re.IGNORECASE,
)


def _remover_assinatura_mobile(texto: str) -> str:
    """Remove a linha de assinatura padrão de app de e-mail móvel ('Enviado do meu iPhone' etc.)
    — testado com caso real: um e-mail só com anexo e sem pergunta chega com texto = só essa
    assinatura, o que bastava pra passar no "há texto?" e acionar a IA com uma pergunta vazia."""
    if not texto:
        return texto
    return _REGEX_ASSINATURA_MOBILE.sub('', texto).strip()


def _extrair_conteudo(payload: dict) -> tuple[str, str, list]:
    """Percorre as partes MIME da mensagem: retorna (texto_plano, html, anexos).
    anexos = lista de {filename, mime_type, attachment_id, data, size}.

    Captura qualquer parte com nome de arquivo, independente de Content-Disposition. Testado
    com iPhone Mail real: ele manda foto anexada como `inline` com `<img src="cid:...">` no
    corpo — exatamente o mesmo mecanismo de um logo de assinatura embutido, sem diferença
    estrutural nenhuma entre os dois. Tentar filtrar por isso (tentativa anterior) descartava
    fotos reais de clientes; ocasionalmente listar um logo de assinatura como "anexo" é bem
    menos grave que perder um anexo de verdade."""
    texto, html, anexos = '', '', []

    def _walk(part):
        nonlocal texto, html
        mime = part.get('mimeType', '')
        filename = part.get('filename') or ''
        body = part.get('body', {}) or {}
        if filename and (body.get('attachmentId') or body.get('data')):
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

    html = _truncar_no_blockquote(html.strip())
    texto = texto.strip() or _texto_de_html(html)
    texto = _remover_assinatura_mobile(_cortar_citacao(texto))

    return texto, html, anexos


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
        'caminho_arquivo': str(caminho_final.relative_to(_BASE_APP)),
        'mime_type': anexo['mime_type'],
        'tamanho_bytes': len(conteudo),
    }


def _baixar_anexo(service, message_id: str, anexo: dict) -> bytes:
    if anexo['data']:
        return _decodificar_b64url(anexo['data'])
    att = service.users().messages().attachments().get(
        userId='me', messageId=message_id, id=anexo['attachment_id']).execute()
    return _decodificar_b64url(att['data'])


# Remetentes que nunca são clientes (avisos, marketing, bancos, fornecedores de serviço)
_REGEX_REMETENTE_RUIDO = re.compile(
    r'@([\w.-]+\.)?(google\.com|googlemail\.com|youtube\.com|facebookmail\.com|hotmart\.com|'
    r'bb\.com\.br|bbclientesmpe\.com\.br|hostinger\.com|brevo\.com|cbl\.org\.br|ebanx\.com|'
    r'enotasgw\.com\.br|globalsign\.com)>?$', re.IGNORECASE)
_REGEX_AGRADECIMENTO = re.compile(
    r'^\W*(muito\s+)?(obrigad[oa]s?|obg|grat[ao]|gratidão|ok|okay|consegui( abrir)?|valeu|amém|am[eé]m|'
    r'deus (te|lhe) (abençoe|pague)|fique com deus)\W*$', re.IGNORECASE)
_CATEGORIAS_SEM_VINCULO = ('ruido', 'administrativo', 'agradecimento')
_EXTENSOES_COMPROVANTE = {'image/jpeg': '.jpg', 'image/png': '.png', 'application/pdf': '.pdf'}


def _e_ruido(remetente_email: str, headers: dict) -> bool:
    """Newsletter/marketing sempre traz List-Unsubscribe ou Precedence: bulk; cliente, nunca."""
    if headers.get('list-unsubscribe') or (headers.get('precedence') or '').lower() in ('bulk', 'list'):
        return True
    return bool(_REGEX_REMETENTE_RUIDO.search(remetente_email or ''))


def _e_da_equipe(remetente_email: str) -> bool:
    """Endereços nossos: domínio da empresa ou a lista EMAIL_ATENDIMENTO_EQUIPE (e-mails pessoais
    de quem atende, separados por vírgula)."""
    equipe = {e.strip().lower() for e in os.getenv('EMAIL_ATENDIMENTO_EQUIPE', '').split(',') if e.strip()}
    return remetente_email.endswith('@lsnlivros.com.br') or remetente_email in equipe


def _enderecos(headers: dict) -> list:
    from email.utils import getaddresses
    campos = [headers.get(h, '') for h in ('to', 'cc', 'delivered-to')]
    return sorted({e.lower() for _, e in getaddresses(campos) if '@' in e})


def _endereco_da_chave(destinatarios: list) -> str:
    """O alias para onde a cliente escreveu (ex: pudim@), não a caixa que recebe tudo."""
    from fluxos._gmail_labels import CAIXA_PRODUCAO, caixa_atendimento
    proprias = {CAIXA_PRODUCAO, caixa_atendimento()}
    return next((d for d in destinatarios if d not in proprias), destinatarios[0] if destinatarios else '')


def _triar(texto: str, assunto: str, destinatario: str, anexos: list, escreveu_para_chave_pix: bool):
    """Atalhos sem IA para os casos mais comuns e óbvios; o resto vai para o agente."""
    from agente_triagem_email import TriagemEmail, triar_email
    curto = (texto or '').strip()
    if not anexos and len(curto) <= 60 and _REGEX_AGRADECIMENTO.match(curto):
        return TriagemEmail(tipo='vendas', categoria='agradecimento', motivo='Agradecimento curto')
    # Chave PIX só no caso óbvio: vazio ou até 3 palavras além de endereços ("Pagamento",
    # "pudim@lsnlivros.com.br", "Fazer um pix"). "Não consigo fazer o Pix…" é dúvida de
    # pagamento (humano) — vai para a IA decidir.
    palavras = re.findall(r'\w+', re.sub(r'\S+@\S+', ' ', curto))
    if (escreveu_para_chave_pix and not anexos and len(palavras) <= 3
            and not re.search(r'\bn[aã]o\b|consig', curto, re.IGNORECASE)):
        return TriagemEmail(tipo='vendas', categoria='chave_pix',
                            motivo='E-mail vazio/quase vazio para o endereço da chave PIX')
    return triar_email(assunto, texto, destinatario, len(anexos))


def _ler_comprovantes(service, message_id: str, anexos: list) -> list:
    """Nome do pagador lido pela IA nas imagens/PDFs anexos (até 2). Só chamado pela cascata de
    vínculo quando e-mail/telefone/CPF não resolveram — é a etapa mais cara (gpt-4o)."""
    import json as _json
    import tempfile
    from agente_valida_comprovante import validar_comprovante_com_ia
    lidos = []
    for anexo in [a for a in anexos if a['mime_type'] in _EXTENSOES_COMPROVANTE][:2]:
        try:
            conteudo = _baixar_anexo(service, message_id, anexo)
            if len(conteudo) > 10 * 1024 * 1024:
                continue
            with tempfile.NamedTemporaryFile(suffix=_EXTENSOES_COMPROVANTE[anexo['mime_type']]) as tmp:
                tmp.write(conteudo)
                tmp.flush()
                dados = _json.loads(validar_comprovante_com_ia(tmp.name) or '{}')
            if not dados.get('recusado') and dados.get('nome_pagador'):
                lidos.append(dados)
        except Exception as exc:
            logger.warning(f"[EMAIL-CONVERSAS] ⚠️ Comprovante '{anexo['filename']}' não lido: {exc}")
    return lidos


def _pode_enviar_sozinho(resposta_tipo: str, metodo_vinculo: str | None, thread_id: str,
                         remetente_email: str) -> bool:
    """Envio automático (sem o clique humano): só tipos liberados em EMAIL_ATENDIMENTO_AUTO_TIPOS,
    nunca a sugestão da IA, nunca vínculo por nome/comprovante, nunca num thread em que já
    respondemos (anti-loop) e no máximo 1 por remetente a cada 24h."""
    from fluxos.email_vinculo import METODOS_FORTES
    liberados = {t.strip() for t in os.getenv('EMAIL_ATENDIMENTO_AUTO_TIPOS', '').split(',') if t.strip()}
    if resposta_tipo not in liberados or resposta_tipo == 'ia':
        return False
    if resposta_tipo not in ('pedir_dados', 'chave_pix') and metodo_vinculo not in METODOS_FORTES:
        return False
    import database as db
    if db.thread_email_ja_respondido(thread_id):
        return False
    return db.contar_respostas_automaticas_recentes(remetente_email, horas=24) == 0


def _gravar_no_pedido(service, db, pedido: dict, full: dict, headers: dict, texto: str, html: str,
                      anexos: list) -> None:
    """Mantém a tela de conversa por produto e o histórico do agente de IA (mensagens_email_pedido)
    para e-mails ligados a um pedido."""
    mensagem_id = db.salvar_mensagem_email_pedido(
        pedido_id=pedido['id'], direcao='recebida', gmail_message_id=full['id'],
        gmail_thread_id=full.get('threadId', ''), rfc_message_id=headers.get('message-id'),
        assunto=headers.get('subject', ''), remetente=headers.get('from', ''),
        destinatario=headers.get('to', ''), corpo_texto=texto, corpo_html=html,
        data_mensagem=_labels.data_do_gmail(full['internalDate']),
    )
    if mensagem_id is None:
        return
    for anexo in anexos:
        salvo = _salvar_anexo(service, full['id'], pedido['id'], anexo)
        if salvo:
            db.salvar_anexo_email_mensagem(mensagem_id, salvo['nome_arquivo'], salvo['caminho_arquivo'],
                                           salvo['mime_type'], salvo['tamanho_bytes'])


def _resposta_ia(db, pedido: dict, texto: str) -> str | None:
    """Sugestão do agente de e-mail do produto (dúvida de uso). None = agente escalou/falhou."""
    produto = db.get_produto_disponivel_web(pedido['produto_id'])
    if not produto or pedido.get('email_bloqueado') or not texto:
        return None
    from agente_resposta_email_produto import responder_cliente_email_com_historico_produto
    historico = db.buscar_historico_email_conversa(pedido['id'], limite=10)
    return responder_cliente_email_com_historico_produto(texto, historico, produto, pedido)


def _processar_mensagem(service, db, message_id: str, envio_automatico: bool = True) -> None:
    from fluxos import _gmail_labels as labels
    from fluxos.fluxo_resposta_atendimento import aplicar_rotulos, enviar as enviar_resposta

    full = service.users().messages().get(userId='me', id=message_id, format='full').execute()
    headers = {h['name'].lower(): h['value'] for h in full.get('payload', {}).get('headers', [])}
    remetente_nome, remetente_email = parseaddr(headers.get('from', ''))
    remetente_email = remetente_email.lower()
    thread_id = full.get('threadId', '')
    assunto = headers.get('subject', '')
    destinatarios = _enderecos(headers)
    registro = {
        'gmail_message_id': full['id'], 'gmail_thread_id': thread_id,
        'rfc_message_id': headers.get('message-id'), 'remetente_email': remetente_email or '(sem remetente)',
        'remetente_nome': (remetente_nome or '')[:150], 'destinatario': ', '.join(destinatarios)[:255],
        'assunto': assunto[:255], 'recebido_em': _labels.data_do_gmail(full['internalDate']),
        'pedido_id': None, 'resposta_tipo': None, 'resposta_html': None,
    }

    ja_registrado = db.get_email_atendimento_por_mensagem(full['id'])
    if ja_registrado:
        # Gravado numa rodada anterior, mas os marcadores falharam: só reaplica (sem nova triagem)
        aplicar_rotulos(service, ja_registrado)
        return

    if _e_da_equipe(remetente_email):
        # Alguém da equipe respondeu por fora (ex: Gmail pessoal com cópia para a caixa): o thread
        # está respondido — não é pendência nova.
        for pendente in db.listar_emails_atendimento_pendentes_por_thread():
            if pendente['gmail_thread_id'] == thread_id:
                db.atualizar_email_atendimento(pendente['id'], estado='respondido', respondido_por=remetente_email,
                                               respondido_em=_labels.agora_sp())
                aplicar_rotulos(service, db.get_email_atendimento(pendente['id']))
        labels.aplicar(service, message_id, [labels.PROCESSADO])
        return

    if _e_bounce_ou_autoresponder(headers.get('from', ''), headers) or _e_ruido(remetente_email, headers):
        registro.update(tipo='ruido', categoria='ruido', estado='sem_acao')
        db.inserir_email_atendimento(registro)
        aplicar_rotulos(service, registro)  # se falhar, a próxima rodada reaplica (ja_registrado acima)
        return

    try:
        analise = _analisar(service, db, full, message_id, registro, remetente_nome, destinatarios)
    except Exception as exc:
        # Falha antes de gravar (OpenAI fora, pedido estranho…): vai para a fila humana com o erro,
        # em vez de ficar sem 'Processado' e ser reprocessado (e cobrado) a cada 10 minutos.
        logger.error(f"[EMAIL-CONVERSAS] ❌ Análise falhou na mensagem {message_id}: {exc}")
        registro.update(tipo='vendas', categoria='outros', estado='a_responder',
                        motivo_triagem=f'Erro no processamento automático: {type(exc).__name__}: {exc}'[:255])
        analise = None

    atendimento_id = db.inserir_email_atendimento(registro)
    if atendimento_id is None:  # outra execução gravou ao mesmo tempo
        return

    # Daqui em diante o e-mail já está na fila: cada passo é independente (um marcador que falha
    # não impede o histórico do pedido nem o envio automático).
    def tentar(descricao, funcao):
        try:
            funcao()
        except Exception as exc:
            logger.warning(f"[EMAIL-CONVERSAS] ⚠️ #{atendimento_id}: {descricao} falhou: {exc}")

    tentar('marcadores', lambda: aplicar_rotulos(service, db.get_email_atendimento(atendimento_id)))
    # Só a nova pendência substitui a anterior: um "Oi"/"??" (sem ação) depois de uma pergunta
    # ainda sem resposta não pode tirar a pergunta da fila.
    if registro['estado'] in ('a_responder', 'aguardando_aprovacao'):
        for antigo_id in db.fechar_atendimentos_anteriores_do_thread(thread_id, atendimento_id):
            tentar('marcadores do anterior', lambda i=antigo_id: aplicar_rotulos(service, db.get_email_atendimento(i)))
    if not analise:
        return

    pedido, vinculo = analise['pedido'], analise['vinculo']
    if pedido:
        tentar('histórico do pedido', lambda: _gravar_no_pedido(service, db, pedido, full, headers, analise['texto'],
                                                                 analise['html'], analise['anexos']))
        if not pedido.get('gmail_thread_id') and vinculo.metodo in ('numero_pedido', 'email'):
            tentar('thread do pedido', lambda: db.definir_gmail_thread_pedido(pedido['id'], thread_id))

    logger.info(f"[EMAIL-CONVERSAS] ✅ #{atendimento_id} {registro['tipo']}/{registro['categoria']} — "
                f"pedido {registro['pedido_id'] or '-'} ({vinculo.metodo or 'sem vínculo'}), "
                f"{registro['estado']} {registro['resposta_tipo'] or ''}")

    if envio_automatico and registro['resposta_tipo'] and _pode_enviar_sozinho(
            registro['resposta_tipo'], vinculo.metodo, thread_id, remetente_email):
        tentar('envio automático', lambda: enviar_resposta(atendimento_id, registro['resposta_html'],
                                                           por='sistema', automatica=True))


def _analisar(service, db, full: dict, message_id: str, registro: dict, remetente_nome: str,
              destinatarios: list) -> dict:
    """Triagem + vínculo + decisão + resposta pronta. Preenche `registro` e devolve o que o resto
    do processamento usa."""
    from fluxos.email_vinculo import Vinculo, vincular
    from fluxos.email_respostas import decidir, e_atrasada, montar_resposta, primeiro_nome

    remetente_email, thread_id = registro['remetente_email'], registro['gmail_thread_id']
    assunto = next((h['value'] for h in full.get('payload', {}).get('headers', [])
                    if h['name'].lower() == 'subject'), '')
    texto, html, anexos = _extrair_conteudo(full.get('payload', {}))
    chave_pix = db.buscar_chave_pix_do_email(destinatarios)
    escreveu_para_chave_pix = chave_pix is not None
    # Pista de produto só de chave de produto ativo (pascoa@ foi a chave de todos os produtos do site)
    produto_da_chave = chave_pix['produto_id'] if chave_pix and chave_pix['aponta_produto'] else None
    triagem = _triar(texto, assunto, registro['destinatario'], anexos, escreveu_para_chave_pix)
    registro.update(tipo=triagem.tipo, categoria=triagem.categoria, motivo_triagem=triagem.motivo[:255])

    if triagem.tipo == 'vendas' and triagem.categoria not in _CATEGORIAS_SEM_VINCULO:
        vinculo = vincular(remetente_email, remetente_nome, assunto, texto, thread_id,
                           produto_id=produto_da_chave, enderecos_ignorados=destinatarios,
                           ler_comprovantes=lambda: _ler_comprovantes(service, message_id, anexos),
                           recebido_em=registro['recebido_em'])
    else:
        vinculo = Vinculo()
    pedido = vinculo.pedido
    produto_id = (pedido or {}).get('produto_id') or produto_da_chave
    produto = db.get_produto_by_id(produto_id) if produto_id else None

    tem_comprovante = any(a['mime_type'] in _EXTENSOES_COMPROVANTE for a in anexos)
    decisao = decidir(triagem.tipo, triagem.categoria, vinculo, produto, escreveu_para_chave_pix, tem_comprovante)
    resposta_html = None
    if decisao.resposta_tipo == 'ia':
        resposta_html = _resposta_ia(db, pedido, texto)
    elif decisao.resposta_tipo:
        try:
            resposta_html = montar_resposta(decisao.resposta_tipo, pedido, produto,
                                            primeiro_nome(remetente_nome, (pedido or {}).get('contact_name')),
                                            destinatario=_endereco_da_chave(destinatarios),
                                            atrasada=e_atrasada(registro['recebido_em']))
        except ValueError as exc:
            logger.warning(f"[EMAIL-CONVERSAS] ⚠️ Resposta pronta não montada ({exc}) — vai pro humano")
    if decisao.resposta_tipo and not resposta_html:
        decisao.estado, decisao.resposta_tipo = 'a_responder', None

    registro.update(
        pedido_id=(pedido or {}).get('id'), produto_id=produto_id, metodo_vinculo=vinculo.metodo,
        candidatos=[{k: c.get(k) for k in ('id', 'estado_id', 'produto_id', 'email', 'contact_phone',
                                            'contact_name', 'nome_pagador', 'data_pedido')}
                    for c in vinculo.candidatos] or None,
        estado=decisao.estado, resposta_tipo=decisao.resposta_tipo, resposta_html=resposta_html,
    )
    return {'texto': texto, 'html': html, 'anexos': anexos, 'pedido': pedido, 'vinculo': vinculo}


def _conferir_respondidos_no_gmail(service, db) -> None:
    """Pendência respondida direto no Gmail (sem passar pelo admin) sai da fila."""
    from fluxos.fluxo_resposta_atendimento import aplicar_rotulos
    pendentes = db.listar_emails_atendimento_pendentes_por_thread()
    for thread_id in {p['gmail_thread_id'] for p in pendentes}:
        try:
            thread = service.users().threads().get(userId='me', id=thread_id, format='minimal').execute()
        except Exception as exc:
            logger.warning(f"[EMAIL-CONVERSAS] ⚠️ Thread {thread_id} não lido: {exc}")
            continue
        enviados = [int(m['internalDate']) / 1000 for m in thread.get('messages', [])
                    if 'SENT' in m.get('labelIds', [])]  # segundos desde 1970 (UTC)
        for pendente in (p for p in pendentes if p['gmail_thread_id'] == thread_id):
            if any(e > _labels.epoch_de_data_sp(pendente['recebido_em']) for e in enviados):
                db.atualizar_email_atendimento(pendente['id'], estado='respondido', respondido_por='gmail',
                                               respondido_em=_labels.agora_sp())
                aplicar_rotulos(service, db.get_email_atendimento(pendente['id']))


def executar(janela_dias: int = 3, maximo: int = 50, envio_automatico: bool = True) -> int:
    """Processa os e-mails novos da caixa. Devolve quantos processou.

    janela_dias — só e-mails dos últimos N dias: a caixa tem meses de mensagens antigas sem o
    marcador Processado, que não devem virar respostas atrasadas nem centenas de triagens. O
    Celery usa o padrão (3); a janela maior é para a carga única da fila
    (scripts/organizar_caixa_email_antiga.py --aplicar), que desliga o envio automático: e-mail
    antigo sempre passa pela aprovação no admin.
    """
    import database as db
    from fluxos import _gmail_labels as labels

    caixa = labels.caixa_atendimento()
    if not caixa:
        logger.info("[EMAIL-CONVERSAS] ⏭ Fora de produção sem EMAIL_ATENDIMENTO_CAIXA (caixa de teste) — "
                    "não lê a caixa real")
        return 0
    service = labels.servico(caixa)

    _conferir_respondidos_no_gmail(service, db)

    consulta = (f"in:inbox -in:sent newer_than:{janela_dias}d "
                f"-label:{labels.PROCESSADO.lower().replace('/', '-')}")
    ids, pagina = [], None
    while len(ids) < maximo:
        resp = service.users().messages().list(userId='me', q=consulta, pageToken=pagina,
                                               maxResults=min(500, maximo - len(ids))).execute()
        ids += [m['id'] for m in resp.get('messages', [])]
        pagina = resp.get('nextPageToken')
        if not pagina:
            break
    logger.info(f"[EMAIL-CONVERSAS] 📬 {len(ids)} mensagem(ns) nova(s) em {caixa} (últimos {janela_dias} dias)")
    # O Gmail lista do mais novo para o mais antigo: invertida, a lista fica na ordem de chegada
    processar_mensagens(service, list(reversed(ids)), envio_automatico=envio_automatico)
    return len(ids)


def processar_mensagens(service, ids_em_ordem_de_chegada: list, envio_automatico: bool = True) -> list:
    """Processa as mensagens na ordem em que chegaram: a mais nova de um thread é a última
    gravada — é ela que fica na fila (a gravação de uma pendência fecha as anteriores do thread).
    Usada pelo leitor e pela carga única do script da caixa antiga (que passa os ids exatos).
    Devolve os ids que falharam (ficam sem Processado; a próxima rodada tenta de novo)."""
    import database as db
    falhas = []
    for message_id in ids_em_ordem_de_chegada:
        try:
            _processar_mensagem(service, db, message_id, envio_automatico=envio_automatico)
        except Exception as exc:
            falhas.append(message_id)
            logger.error(f"[EMAIL-CONVERSAS] ❌ Erro ao processar mensagem {message_id}: {exc}")
    return falhas


# ─── Leitura sob demanda para a tela do admin (o corpo não é copiado para o banco) ───

def ler_thread(thread_id: str) -> list:
    """Mensagens do thread direto do Gmail, mais antiga primeiro: remetente, data, texto (já sem
    citação), html bruto (a view sanitiza), anexos e se foi enviada por nós."""
    from fluxos import _gmail_labels as labels
    caixa = labels.caixa_atendimento()
    if not caixa:
        return []
    service = labels.servico(caixa)
    thread = service.users().threads().get(userId='me', id=thread_id, format='full').execute()
    mensagens = []
    for m in thread.get('messages', []):
        headers = {h['name'].lower(): h['value'] for h in m.get('payload', {}).get('headers', [])}
        texto, html, anexos = _extrair_conteudo(m.get('payload', {}))
        mensagens.append({
            'id': m['id'],
            'de': headers.get('from', ''),
            'data': _labels.data_do_gmail(m['internalDate']),
            'enviada': 'SENT' in m.get('labelIds', []),
            'texto': texto,
            'html': html,
            # Identificado pela posição: o attachmentId do Gmail muda a cada leitura da mensagem
            'anexos': [{'indice': i, 'filename': a['filename'], 'mime_type': a['mime_type'], 'size': a['size']}
                       for i, a in enumerate(anexos)],
        })
    return mensagens


def baixar_anexo(thread_id: str, message_id: str, indice: int) -> tuple[bytes, str, str] | None:
    """(conteúdo, nome do arquivo, mime) de um anexo — para o download no admin. Só de mensagens
    do thread informado (o do atendimento), pra URL não servir anexo de outra conversa da caixa."""
    from fluxos import _gmail_labels as labels
    caixa = labels.caixa_atendimento()
    if not caixa:
        return None
    service = labels.servico(caixa)
    full = service.users().messages().get(userId='me', id=message_id, format='full').execute()
    if full.get('threadId') != thread_id:
        return None
    _, _, anexos = _extrair_conteudo(full.get('payload', {}))
    if not 0 <= indice < len(anexos):
        return None
    anexo = anexos[indice]
    return _baixar_anexo(service, message_id, anexo), anexo['filename'], anexo['mime_type']
