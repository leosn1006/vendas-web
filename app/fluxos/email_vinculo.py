"""
Liga um e-mail de cliente ao pedido dela — a busca que o humano fazia na mão (SELECT … LIKE).

Cascata, do dado mais confiável ao menos confiável; para no primeiro passo que resolve:
  1. thread do Gmail (resposta ao e-mail de entrega/cobrança)
  2. nº do pedido no assunto/corpo (aceito só se o e-mail do pedido é o do remetente)
  3. e-mail do remetente e e-mails escritos no corpo
  4. telefone e CPF escritos no corpo
  5. escreveu para o alias de um produto (chave PIX): pedidos DESSE produto nos 7 dias antes do
     e-mail, pagos ou não, com qualquer palavra do nome — a cliente acabou de receber a chave no
     WhatsApp e o pedido costuma ainda não estar pago
  6. comprovante anexo (nome do pagador lido pela IA) — só se os passos baratos falharem
  7. nome do remetente: nome completo, depois primeiro + último nome

Vínculo por nome (5–7) nunca escolhe um pedido de produto diferente do alias para onde ela
escreveu: esse pedido vira candidato (caso real: e-mail em branco para semacucar@ achou, pelo
nome, um Pudim pago antigo — e respondeu sobre o produto errado).

Regra de ouro (medição de 27/09/2026): só vale quando os pedidos PAGOS encontrados são de UMA
pessoa. Nome comum ('Vera Lucia': 273 pessoas) vira lista de candidatos para o humano escolher.
Pedido não pago só conta nos passos 1–4 (identificador forte) e na busca focada (5), que é
restrita ao produto do alias e aos 7 dias antes do e-mail; no nome geral (6–7), nunca.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import database as db

ESTADOS_PAGOS = (0, 1000)

# Metodos que identificam a cliente com certeza (podem virar resposta automática); nome e
# comprovante (lido por IA) sempre passam por aprovação humana.
METODOS_FORTES = ('thread', 'numero_pedido', 'email', 'telefone', 'cpf')

# Busca focada no produto do alias: quantos dias antes do e-mail o pedido pode ter sido criado
DIAS_BUSCA_POR_PRODUTO = 7

# Nomes e sobrenomes muito comuns: sozinhos não identificam ninguém ("Maria Aparecida Souza" não
# pode ser ligada a "Maria Lima" só pelo "maria"). Um nome raro sozinho vale ("Bernadete").
NOMES_COMUNS = frozenset('''
    maria ana jose joao antonio francisco carlos paulo pedro lucas luiz luis marcos gabriel rafael
    daniel marcelo bruno eduardo felipe raimundo rodrigo manoel manuel mateus matheus andre fernando
    fabio leonardo gustavo guilherme leandro tiago thiago ricardo marcio jorge sebastiao alexandre
    roberto edson sergio claudio geraldo luciano julio renato vinicius rogerio mario francisca
    antonia adriana juliana marcia fernanda patricia aline sandra camila amanda bruna jessica
    leticia julia luciana vanessa mariana gabriela vera lucia aparecida rosa rita helena regina
    silva santos oliveira souza sousa lima pereira ferreira costa rodrigues almeida nascimento
    alves carvalho araujo ribeiro gomes martins rocha barbosa dias lopes soares vieira monteiro
    mendes cardoso moreira freitas batista'''.split())

_RE_EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
_RE_PEDIDO = re.compile(r'(?:pedido|#)\s*(?:n[º°o.]*\s*)?#?\s*(\d{4,7})\b', re.IGNORECASE)
_RE_TELEFONE = re.compile(r'(?:\+?55[\s.-]*)?\(?\b\d{2}\)?[\s.-]*9?\d{4}[\s.-]?\d{4}\b')
_RE_CPF = re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b')
_DOMINIOS_PROPRIOS = ('lsnlivros.com.br',)
_PALAVRAS_IGNORADAS = {'da', 'de', 'do', 'das', 'dos', 'e'}


@dataclass
class Vinculo:
    pedido: dict | None = None
    metodo: str | None = None
    candidatos: list = field(default_factory=list)

    @property
    def pago(self) -> bool:
        return bool(self.pedido) and self.pedido['estado_id'] in ESTADOS_PAGOS


def _pessoa(pedido: dict) -> str:
    """Mesma chave da medição: e-mail, senão telefone, senão o próprio pedido."""
    return (pedido.get('email') or '').strip().lower() or pedido.get('contact_phone') or f"pedido:{pedido['id']}"


def _mais_recente(pedidos: list, produto_id: int | None) -> dict:
    do_produto = [p for p in pedidos if produto_id and p['produto_id'] == produto_id]
    return max(do_produto or pedidos, key=lambda p: (p.get('data_pedido') is not None, p.get('data_pedido'), p['id']))


def _decidir(pedidos: list, produto_id: int | None, aceita_nao_pago: bool) -> tuple[dict | None, list]:
    """(pedido escolhido, candidatos). Pagos de 1 pessoa → o mais recente (do produto, se houver).
    Pagos de várias → candidatos. Sem pago → o não pago mais recente, se o identificador é forte."""
    pagos = [p for p in pedidos if p['estado_id'] in ESTADOS_PAGOS]
    if pagos:
        if len({_pessoa(p) for p in pagos}) == 1:
            return _mais_recente(pagos, produto_id), []
        return None, pagos
    if aceita_nao_pago and pedidos:
        return _mais_recente(pedidos, produto_id), []
    return None, []


def normalizar_nome(nome: str) -> tuple[str, str, str]:
    """(nome completo, primeiro, último) sem acento e em minúsculas. Nome que é e-mail, tem
    dígito ou uma palavra só não serve pra busca ('Dora', 'fran.albano', 'G3neci')."""
    texto = unicodedata.normalize('NFKD', nome or '').encode('ascii', 'ignore').decode().lower()
    texto = re.sub(r'\s+', ' ', texto).strip()
    if not texto or '@' in texto:
        return '', '', ''
    palavras = [p for p in re.split(r'[^a-z]+', texto) if len(p) >= 3 and p not in _PALAVRAS_IGNORADAS]
    if len(palavras) < 2 or re.search(r'\d', texto):
        return '', '', ''
    completo = re.sub(r"[^a-z ]", '', texto).strip()
    primeiro, ultimo = palavras[0], palavras[-1]
    return completo, (primeiro if primeiro != ultimo else ''), (ultimo if primeiro != ultimo else '')


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode().lower()


def palavras_do_nome(nome: str) -> list:
    """Palavras úteis do nome para a busca focada: aceita uma palavra só ('Dora') e descarta as
    que têm dígito ('G3neci'), mas não o nome inteiro. E-mail no lugar do nome não serve."""
    texto = _sem_acento(nome)
    if '@' in texto:
        return []
    # Separa em qualquer coisa que não seja letra ou dígito ("maria.souza", "Ana-Paula") e descarta
    # só as palavras com dígito ("G3neci"), não o nome inteiro
    palavras = [p for p in re.split(r'[^a-z0-9]+', texto) if p and not re.search(r'\d', p)]
    return list(dict.fromkeys(p for p in palavras if len(p) >= 3 and p not in _PALAVRAS_IGNORADAS))


def _decidir_por_palavras(pedidos: list, palavras: list) -> tuple[dict | None, list]:
    """Pontua cada pessoa pelo nº de palavras do nome que aparecem no contato/pagador. Uma pessoa
    com a maior pontuação → o pedido dela (pago primeiro, depois o mais recente). Empate → candidatos."""
    if not pedidos:
        return None, []
    pontos = {}
    for p in pedidos:
        # Palavra inteira: 'ana' não pode contar dentro de 'mariana' (o LIKE do banco é mais largo)
        nomes = set(re.findall(r'[a-z]+', _sem_acento(f"{p.get('contact_name') or ''} {p.get('nome_pagador') or ''}")))
        pontos[p['id']] = sum(1 for palavra in palavras if palavra in nomes)
    por_pessoa = {}
    for p in pedidos:
        por_pessoa[_pessoa(p)] = max(por_pessoa.get(_pessoa(p), 0), pontos[p['id']])
    melhor = max(por_pessoa.values())
    if melhor == 0:
        return None, []
    vencedoras = [pessoa for pessoa, pt in por_pessoa.items() if pt == melhor]
    dela = [p for p in pedidos if _pessoa(p) in vencedoras and pontos[p['id']] == melhor]
    if len(vencedoras) > 1:
        return None, dela
    if melhor == 1:
        # Uma palavra só: vale se for rara; nome comum sozinho vira candidato para o humano
        nomes = set(re.findall(r'[a-z]+', _sem_acento(
            f"{dela[0].get('contact_name') or ''} {dela[0].get('nome_pagador') or ''}")))
        if all(palavra in NOMES_COMUNS for palavra in palavras if palavra in nomes):
            return None, dela
    return max(dela, key=lambda p: (p['estado_id'] in ESTADOS_PAGOS, p.get('data_pedido') or datetime.min, p['id'])), []


def extrair_identificadores(texto: str, remetente_email: str, enderecos_ignorados: list = ()) -> dict:
    texto = texto or ''
    ignorar = {e.lower() for e in enderecos_ignorados} | {(remetente_email or '').lower()}
    emails = [e.lower() for e in _RE_EMAIL.findall(texto)
              if e.lower() not in ignorar and not e.lower().endswith(_DOMINIOS_PROPRIOS)]
    cpfs = {re.sub(r'\D', '', c) for c in _RE_CPF.findall(texto)}
    telefones = {re.sub(r'\D', '', t) for t in _RE_TELEFONE.findall(texto)}
    return {
        'pedidos': sorted({int(n) for n in _RE_PEDIDO.findall(texto)}),
        'emails': sorted(set(emails)),
        # 11 dígitos sem máscara pode ser celular ou CPF: tenta como os dois
        'telefones': sorted(telefones),
        'cpfs': sorted(cpfs | {t for t in telefones if len(t) == 11}),
    }


def vincular(remetente_email: str, remetente_nome: str, assunto: str, corpo: str, thread_id: str,
             produto_id: int | None = None, enderecos_ignorados: list = (),
             ler_comprovantes: Callable[[], list] | None = None, recebido_em: datetime | None = None) -> Vinculo:
    """produto_id: produto do alias para onde a cliente escreveu (chave PIX), se houver.
    recebido_em: horário do e-mail em São Paulo, sem fuso — limite da busca focada."""
    remetente_email = (remetente_email or '').strip().lower()

    pedido = db.resolver_pedido_por_thread_gmail(thread_id) if thread_id else None
    if pedido:
        return Vinculo(pedido=pedido, metodo='thread')

    ids = extrair_identificadores(f'{assunto or ""}\n{corpo or ""}', remetente_email, enderecos_ignorados)

    for numero in ids['pedidos']:
        candidato = db.get_pedido(numero)
        if candidato and (candidato.get('email') or '').strip().lower() == remetente_email:
            return Vinculo(pedido=candidato, metodo='numero_pedido')

    candidatos_ambiguos = []
    passos = [
        ('email', lambda: db.buscar_pedidos_vinculo_por_email([remetente_email, *ids['emails']])),
        ('telefone', lambda: db.buscar_pedidos_vinculo_por_telefone(ids['telefones'])),
        ('cpf', lambda: [p for c in ids['cpfs'] for p in db.buscar_pedidos_vinculo_por_cpf(c)]),
    ]
    for metodo, buscar in passos:
        escolhido, candidatos = _decidir(buscar(), produto_id, aceita_nao_pago=True)
        if escolhido:
            return Vinculo(pedido=escolhido, metodo=metodo)
        candidatos_ambiguos = candidatos_ambiguos or candidatos

    if produto_id and recebido_em:
        palavras = palavras_do_nome(remetente_nome)
        pedidos = db.buscar_pedidos_vinculo_por_produto_e_nome(
            produto_id, recebido_em - timedelta(days=DIAS_BUSCA_POR_PRODUTO), recebido_em, palavras)
        escolhido, candidatos = _decidir_por_palavras(pedidos, palavras)
        if escolhido:
            return Vinculo(pedido=escolhido, metodo='nome')
        candidatos_ambiguos = candidatos_ambiguos or candidatos

    nomes = []
    if ler_comprovantes:
        nomes += [('comprovante', c.get('nome_pagador')) for c in (ler_comprovantes() or [])]
    nomes.append(('nome', remetente_nome))
    for metodo, nome in nomes:
        completo, primeiro, ultimo = normalizar_nome(nome)
        if not completo:
            continue
        busca = db.buscar_pedidos_vinculo_por_nome(completo, primeiro, ultimo)
        for estrategia in ('completo', 'primeiro_ultimo'):
            escolhido, candidatos = _decidir(busca[estrategia], produto_id, aceita_nao_pago=False)
            if escolhido and produto_id and escolhido['produto_id'] != produto_id:
                # Nome aponta outro produto que não o do alias: não é sobre ele que ela escreveu
                candidatos_ambiguos = candidatos_ambiguos or [escolhido]
                continue
            if escolhido:
                return Vinculo(pedido=escolhido, metodo=metodo)
            candidatos_ambiguos = candidatos_ambiguos or candidatos

    return Vinculo(candidatos=candidatos_ambiguos[:20])
