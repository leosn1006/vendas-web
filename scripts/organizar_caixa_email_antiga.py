#!/usr/bin/env python3
"""
Organiza, uma vez só, os e-mails ANTIGOS da caixa de atendimento — os anteriores à fila
(/admin/atendimento-email). O leitor (fluxos/fluxo_email_conversas.py) só olha os últimos 3
dias; sem esta rotina, o estoque da caixa ficaria sem marcador nenhum.

A organização não usa IA, não responde ninguém e não grava no banco — só aplica marcadores:
  - ruído (Google, bancos, devoluções, newsletters) ...... Ruído + arquivado
  - cliente, e nós respondemos por último ................ Atendimento/Respondido
  - cliente, e ela falou por último há mais de 30 dias ... Atendimento/Em análise (fora da fila)
  - cliente, e ela falou por último nos últimos 30 dias .. vai para a FILA do admin: com
    --aplicar, exatamente essas mensagens passam pelo leitor (triagem, vínculo e resposta pronta,
    que começa com "Desculpe a demora"), sem envio automático — tudo com aprovação no admin
  - resposta da própria equipe ........................... (só Processado)
  - e-mails que o sistema enviou (entrega, follow-up) .... Envios/<produto>
Todos recebem Sistema/Processado, para o leitor nunca pegá-los. Clientes ganham também
Produto/<nome> quando dá para saber sem IA (nº do pedido no assunto ou alias da chave PIX).

Roda em SIMULAÇÃO por padrão (mostra quantos e-mails iriam para cada marcador); só aplica
com --aplicar. Idempotente: e-mails já com Sistema/Processado são ignorados.

Uso (no servidor, venv do projeto, na pasta do projeto):
    python scripts/organizar_caixa_email_antiga.py
    python scripts/organizar_caixa_email_antiga.py --aplicar
    python scripts/organizar_caixa_email_antiga.py --fila-dias 0   # nada vai para a fila
"""
import argparse
import collections
import os
import re
import sys
from datetime import datetime, timedelta  # noqa: F401 (anotações)

from dotenv import load_dotenv

load_dotenv()

# Roda no host, fora da rede Docker: o MySQL é publicado em 127.0.0.1:3306 (docker-compose.yml)
if os.getenv('DB_HOST') == 'db':
    os.environ['DB_HOST'] = 'localhost'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import database as db  # noqa: E402
from fluxos import _gmail_labels as labels  # noqa: E402
from fluxos.fluxo_email_conversas import (  # noqa: E402
    _e_bounce_ou_autoresponder, _e_da_equipe, _e_ruido, _enderecos,
)

_RE_PEDIDO = re.compile(r'#(\d{4,7})\b')
# Assuntos que o sistema gera: entrega ("Pronto para baixar: <produto>!") e cobrança
# ("🎁 Maria, seu <produto> ainda está te esperando!")
_RE_ASSUNTO_DO_SISTEMA = re.compile(r'(?:Pronto para baixar:\s*(.+?)!?\s*$|, seu\s+(.+?)\s+ainda está te esperando)',
                                    re.IGNORECASE)


def _listar(service, consulta: str) -> list:
    ids, pagina = [], None
    while True:
        resp = service.users().messages().list(userId='me', q=consulta, maxResults=500, pageToken=pagina).execute()
        ids += [m['id'] for m in resp.get('messages', [])]
        pagina = resp.get('nextPageToken')
        if not pagina:
            return ids


def _cabecalhos(service, message_id: str) -> tuple[dict, dict]:
    msg = service.users().messages().get(
        userId='me', id=message_id, format='metadata',
        metadataHeaders=['From', 'To', 'Cc', 'Delivered-To', 'Subject', 'List-Unsubscribe', 'Precedence',
                         'Auto-Submitted']).execute()
    return msg, {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}


def _remetente(headers: dict) -> str:
    from email.utils import parseaddr
    return parseaddr(headers.get('from', ''))[1].lower()


class Produtos:
    """Produto sem IA, do mais confiável ao menos: nome do produto escrito no assunto (entrega e
    cobrança sempre o trazem), nº do pedido no assunto, alias da chave PIX. O nome vem antes do
    pedido porque em pedidos antigos o produto_id não bate mais com o que foi vendido (produtos
    reaproveitados/renomeados: "Pedido #305168 … Temperos" aponta hoje para o Sem Açúcar)."""

    def __init__(self):
        linhas = db.db.execute_query("SELECT id, nome FROM produtos", fetch_all=True) or []
        self.nomes = {l['id']: l['nome'] for l in linhas}
        # Mais longo primeiro: "Guia das Orquídeas" antes de "Orquídeas"
        self._por_tamanho = sorted((n for n in self.nomes.values() if n and n.strip()), key=len, reverse=True)
        self._pedidos = {}

    def do_email(self, headers: dict) -> str | None:
        assunto = headers.get('subject', '')
        # Nome do produto só vale em assunto gerado pelo sistema; escrito pela cliente ("receita do
        # pudim") pode citar outro produto — aí manda o nº do pedido
        gerado = _RE_ASSUNTO_DO_SISTEMA.search(assunto)
        if gerado:
            trecho = next(g for g in gerado.groups() if g).strip().lower()
            no_assunto = next((n for n in self._por_tamanho if n.strip().lower() in trecho), None)
            if no_assunto:
                return no_assunto
        for numero in _RE_PEDIDO.findall(assunto):
            if numero not in self._pedidos:
                pedido = db.get_pedido(int(numero))
                self._pedidos[numero] = pedido['produto_id'] if pedido else None
            if self._pedidos[numero]:
                return self.nomes.get(self._pedidos[numero])
        produto_id = db.buscar_produto_por_chave_pix(_enderecos(headers))
        return self.nomes.get(produto_id) if produto_id else None


def _ultima_do_thread(service, thread_id: str, cache: dict) -> tuple[bool, datetime]:
    """(o thread termina com mensagem nossa?, data da última mensagem). "Nossa" = enviada pela
    caixa ou por alguém da equipe (EMAIL_ATENDIMENTO_EQUIPE)."""
    if thread_id not in cache:
        from email.utils import parseaddr
        thread = service.users().threads().get(userId='me', id=thread_id, format='metadata',
                                               metadataHeaders=['From']).execute()
        # Rascunho (sai "do admin@") e spam não são a conversa: um rascunho não enviado faria a
        # pergunta da cliente parecer respondida e sumir da fila para sempre. Da lixeira, só vale o
        # que foi enviado (resposta nossa apagada depois continua sendo resposta).
        def conta(m):
            rotulos = set(m.get('labelIds', []))
            return not {'DRAFT', 'SPAM'} & rotulos and ('TRASH' not in rotulos or 'SENT' in rotulos)
        validas = [m for m in thread.get('messages', []) if conta(m)]
        if not validas:
            cache[thread_id] = (False, datetime.min)
            return cache[thread_id]
        ultima = max(validas, key=lambda m: int(m['internalDate']))
        de = next((h['value'] for h in ultima.get('payload', {}).get('headers', []) if h['name'] == 'From'), '')
        nossa = 'SENT' in ultima.get('labelIds', []) or _e_da_equipe(parseaddr(de)[1].lower())
        cache[thread_id] = (nossa, labels.data_do_gmail(ultima['internalDate']))
    return cache[thread_id]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--aplicar', action='store_true', help='Aplica os marcadores (sem isso, só simula)')
    parser.add_argument('--dias', type=int, default=3,
                        help='Só e-mails mais antigos que isso (os recentes são do leitor). Padrão: 3')
    parser.add_argument('--fila-dias', type=int, default=30,
                        help='Conversas em que a cliente falou por último há até N dias vão para a fila '
                             'do admin (0 = nenhuma). Padrão: 30')
    args = parser.parse_args()
    limite_fila = labels.agora_sp() - timedelta(days=args.fila_dias)
    para_a_fila = []

    caixa = labels.caixa_atendimento()
    if not caixa:
        sys.exit('Sem caixa de atendimento (fora de produção, defina EMAIL_ATENDIMENTO_CAIXA com uma caixa de teste).')
    service = labels.servico(caixa)
    produtos = Produtos()
    processado = labels.PROCESSADO.lower().replace('/', '-')

    grupos = collections.defaultdict(list)   # (adicionar, arquivar) -> [ids]
    exemplos = collections.defaultdict(list)
    threads = {}

    entrada = _listar(service, f'in:inbox -in:sent older_than:{args.dias}d -label:{processado}')
    print(f'Caixa {caixa}: {len(entrada)} e-mail(s) antigo(s) na entrada sem {labels.PROCESSADO}')
    for i, message_id in enumerate(entrada, 1):
        msg, headers = _cabecalhos(service, message_id)
        remetente = _remetente(headers)
        if _e_bounce_ou_autoresponder(headers.get('from', ''), headers) or _e_ruido(remetente, headers):
            chave = ((labels.RUIDO, labels.PROCESSADO), True)
        elif _e_da_equipe(remetente):
            chave = ((labels.PROCESSADO,), False)
        else:
            nossa, data_ultima = _ultima_do_thread(service, msg['threadId'], threads)
            if not nossa and data_ultima >= limite_fila:
                if labels.data_do_gmail(msg['internalDate']) >= limite_fila:
                    para_a_fila.append((int(msg['internalDate']), message_id,
                                        f"{remetente} | {headers.get('subject', '')[:60]}"))
                    continue  # sem marcador aqui: vai para a fila no --aplicar
                # Mensagem mais velha que a janela num thread que vai para a fila: a mais nova
                # representa a conversa na fila; esta só sai do caminho do leitor.
                grupos[((labels.PROCESSADO,), False)].append(message_id)
                continue
            status = labels.rotulos_do_estado('vendas', 'respondido')[0][0] if nossa else labels.EM_ANALISE
            chave = ((status, labels.nome_label_produto(produtos.do_email(headers)), labels.PROCESSADO), False)
        grupos[chave].append(message_id)
        if len(exemplos[chave]) < 3:
            exemplos[chave].append(f"{remetente} | {headers.get('subject', '')[:60]}")
        if i % 100 == 0:
            print(f'  … {i}/{len(entrada)}')

    enviados = _listar(service, f'in:sent -label:{processado}')
    print(f'Enviados sem {labels.PROCESSADO}: {len(enviados)}')
    for i, message_id in enumerate(enviados, 1):
        _, headers = _cabecalhos(service, message_id)
        produto = produtos.do_email(headers)
        chave = ((labels.nome_label_envio(produto), labels.PROCESSADO), False)
        grupos[chave].append(message_id)
        if len(exemplos[chave]) < 3:
            exemplos[chave].append(headers.get('subject', '')[:70])
        if i % 200 == 0:
            print(f'  … {i}/{len(enviados)}')

    print('\nResumo:')
    for (adicionar, arquivar), ids in sorted(grupos.items(), key=lambda g: -len(g[1])):
        print(f"  {len(ids):5d}  {' + '.join(adicionar)}{' + arquivar' if arquivar else ''}")
        for exemplo in exemplos[(adicionar, arquivar)]:
            print(f'           ex.: {exemplo}')

    print(f'\n  {len(para_a_fila):5d}  → FILA do admin (cliente falou por último nos últimos {args.fila_dias} dias)')
    for _, _, exemplo in para_a_fila[:10]:
        print(f'           {exemplo}')

    if not args.aplicar:
        print('\nSimulação — nada foi alterado. Rode com --aplicar para aplicar os marcadores e montar a fila.')
        return

    for (adicionar, arquivar), ids in grupos.items():
        add_ids = [labels.garantir_label(service, nome) for nome in adicionar]
        for inicio in range(0, len(ids), 1000):  # batchModify aceita até 1000 ids por chamada
            service.users().messages().batchModify(userId='me', body={
                'ids': ids[inicio:inicio + 1000], 'addLabelIds': add_ids,
                'removeLabelIds': ['INBOX'] if arquivar else []}).execute()
    print(f'\n✅ Marcadores aplicados em {sum(len(ids) for ids in grupos.values())} e-mail(s).')

    if para_a_fila:
        # Exatamente as mensagens separadas acima (sem nova busca por data: o newer_than do Gmail é
        # aproximado por dia e deixaria sem marcador as que estão no limite), na ordem de chegada
        # e sem envio automático — e-mail antigo sempre passa pela aprovação no admin.
        from fluxos.fluxo_email_conversas import processar_mensagens
        print(f'Montando a fila com {len(para_a_fila)} mensagem(ns)…')
        falhas = processar_mensagens(service, [mid for _, mid, _ in sorted(para_a_fila)], envio_automatico=False)
        if falhas:
            # Ficaram sem Processado e são mais velhas que 3 dias: o leitor do Celery não as pega
            print(f'⚠️ {len(falhas)} mensagem(ns) falharam (ver log). Rode o --aplicar de novo para tentar só essas.')
        print(f'✅ Fila montada ({len(para_a_fila) - len(falhas)} de {len(para_a_fila)}) — '
              'confira em /admin/atendimento-email')


if __name__ == '__main__':
    main()
