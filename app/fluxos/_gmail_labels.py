"""
Caixa de atendimento e marcadores (labels) do Gmail.

Os marcadores são o ESPELHO do estado de emails_atendimento (a fonte da verdade é o banco): quem
preferir trabalha direto no Gmail e vê a mesma organização. Dois eixos que se combinam — status
(Atendimento/…, Administrativo/…) e produto (Produto/<nome> ou Produto/Sem produto) — em vez de
uma pasta por combinação.

Proteção do dev: com credenciais de produção no .env, o leitor do dev marcaria e responderia a
caixa real (mesmo risco do incidente da NF-e). Fora de produção, caixa_atendimento() só devolve
uma caixa de teste explícita (EMAIL_ATENDIMENTO_CAIXA), nunca a de produção.
"""

import os
import json as _json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import EH_PRODUCAO

logger = logging.getLogger(__name__)

CAIXA_PRODUCAO = 'admin@lsnlivros.com.br'
_ESCOPOS = ['https://www.googleapis.com/auth/gmail.modify']

PROCESSADO = 'Sistema/Processado'
# Não pode ser "Enviados": o Gmail recusa ("Invalid label name") por ser o nome da pasta do sistema
ENVIOS = 'Envios'
PREFIXO_PRODUTO = 'Produto/'
RUIDO = 'Ruído'
SEM_PRODUTO = 'Produto/Sem produto'
# E-mails antigos (anteriores à fila) em que a cliente falou por último: ficam para revisão no
# Gmail, fora da fila do admin (scripts/organizar_caixa_email_antiga.py)
EM_ANALISE = 'Atendimento/Em análise'

# (tipo, estado) → marcador de status. tipo 'ruido' é tratado à parte (Ruído + arquivar).
_STATUS_VENDAS = {
    'a_responder':          'Atendimento/A responder',
    'aguardando_aprovacao': 'Atendimento/Aguardando aprovação',
    'aguardando_cliente':   'Atendimento/Aguardando cliente',
    'respondido':           'Atendimento/Respondido',
    'sem_acao':             'Atendimento/Sem ação',
}
_STATUS_ADMINISTRATIVO = {
    'a_responder': 'Administrativo/A responder',
    'respondido':  'Administrativo/Respondido',
    'sem_acao':    'Administrativo/Respondido',
}
_TODOS_STATUS = sorted(set(_STATUS_VENDAS.values()) | set(_STATUS_ADMINISTRATIVO.values()) | {EM_ANALISE})

_cache_ids: dict[str, str] = {}

# O banco grava as datas no horário de São Paulo, sem fuso (pedidos.data_pedido etc.). Converter
# explicitamente — e não confiar no TZ do processo — deixa as comparações certas também fora do
# container (o script de scripts/ roda no host, que pode estar em UTC).
FUSO_SP = ZoneInfo('America/Sao_Paulo')


def data_do_gmail(internal_date) -> datetime:
    """internalDate do Gmail (ms desde 1970, UTC) → horário de São Paulo, sem fuso (como no banco)."""
    return datetime.fromtimestamp(int(internal_date) / 1000, tz=FUSO_SP).replace(tzinfo=None)


def agora_sp() -> datetime:
    return datetime.now(FUSO_SP).replace(tzinfo=None)


def epoch_de_data_sp(data: datetime) -> float:
    """Inverso de data_do_gmail: data sem fuso (horário de São Paulo) → segundos desde 1970."""
    return data.replace(tzinfo=FUSO_SP).timestamp()


def caixa_atendimento() -> str | None:
    """Caixa lida/usada pelo atendimento. None = não mexer em caixa nenhuma (dev sem caixa de teste)."""
    caixa = (os.getenv('EMAIL_ATENDIMENTO_CAIXA') or '').strip().lower()
    if EH_PRODUCAO:
        return caixa or CAIXA_PRODUCAO
    if not caixa or caixa == CAIXA_PRODUCAO:
        return None
    return caixa


def servico(caixa: str):
    sa_json = os.getenv('GOOGLE_SA_JSON_P6')
    if not sa_json:
        raise RuntimeError('[GMAIL] GOOGLE_SA_JSON_P6 não configurada')
    creds = Credentials.from_service_account_info(_json.loads(sa_json), scopes=_ESCOPOS, subject=caixa)
    return build('gmail', 'v1', credentials=creds)


def nome_label_produto(produto_nome: str | None) -> str:
    return f'{PREFIXO_PRODUTO}{produto_nome.strip()}' if produto_nome else SEM_PRODUTO


def nome_label_envio(produto_nome: str | None) -> str:
    return f"{ENVIOS}/{(produto_nome or 'Sem produto').strip()}"


def rotulos_do_estado(tipo: str, estado: str) -> tuple[list, list]:
    """(adicionar, remover) de status para o estado atual — remove os outros status, pra um
    e-mail nunca aparecer em 'A responder' e 'Respondido' ao mesmo tempo."""
    if tipo == 'ruido':
        return [RUIDO], list(_TODOS_STATUS)
    mapa = _STATUS_ADMINISTRATIVO if tipo == 'administrativo' else _STATUS_VENDAS
    atual = mapa.get(estado)
    return ([atual] if atual else []), [s for s in _TODOS_STATUS if s != atual]


def garantir_label(service, nome: str) -> str:
    """Id do marcador, criando-o (e os pais, pra aninhar na barra lateral do Gmail) se preciso."""
    if nome in _cache_ids:
        return _cache_ids[nome]
    if not _cache_ids:
        _recarregar_cache(service)
        if nome in _cache_ids:
            return _cache_ids[nome]
    if '/' in nome:
        garantir_label(service, nome.rsplit('/', 1)[0])
    try:
        criado = service.users().labels().create(
            userId='me', body={'name': nome, 'labelListVisibility': 'labelShow',
                               'messageListVisibility': 'show'}).execute()
    except HttpError as exc:
        # 409: outro processo (outro worker, o app) criou depois que este carregou o cache
        if exc.resp.status != 409:
            raise
        _recarregar_cache(service)
        return _cache_ids[nome]
    _cache_ids[nome] = criado['id']
    return criado['id']


def _recarregar_cache(service) -> None:
    _cache_ids.clear()
    for label in service.users().labels().list(userId='me').execute().get('labels', []):
        _cache_ids[label['name']] = label['id']


def aplicar(service, message_id: str, adicionar: list = (), remover: list = (), arquivar: bool = False,
            remover_prefixos: tuple = ()) -> None:
    """remover_prefixos: tira os marcadores que começam com o prefixo e não estão em `adicionar`
    (ex: o Produto/<antigo> quando o humano vincula o e-mail a um pedido de outro produto)."""
    add_ids = [garantir_label(service, n) for n in adicionar]
    # Remover só o que já existe (não cria marcador só pra tirá-lo)
    if not _cache_ids:
        garantir_label(service, PROCESSADO)
    remover = list(remover) + [n for n in _cache_ids if n.startswith(tuple(remover_prefixos))]
    rem_ids = [_cache_ids[n] for n in dict.fromkeys(remover) if n in _cache_ids and n not in adicionar]
    if arquivar:
        rem_ids.append('INBOX')
    if add_ids or rem_ids:
        service.users().messages().modify(
            userId='me', id=message_id, body={'addLabelIds': add_ids, 'removeLabelIds': rem_ids}).execute()


def rotular_enviado(message_id: str, produto_nome: str | None) -> None:
    """Marca um e-mail enviado pelo sistema (entrega, follow-up, resposta) com Envios/<produto>.
    Nunca levanta exceção: o e-mail já saiu, o marcador é só organização."""
    caixa = caixa_atendimento()
    if not caixa or not message_id:
        return
    try:
        aplicar(servico(caixa), message_id, adicionar=[nome_label_envio(produto_nome)])
    except Exception as exc:
        logger.warning(f'[GMAIL-LABELS] ⚠️ Não marcou o enviado {message_id}: {exc}')
