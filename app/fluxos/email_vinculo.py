"""
Liga um e-mail de cliente ao pedido dela — a busca que o humano fazia na mão (SELECT … LIKE).

Cascata, do dado mais confiável ao menos confiável; para no primeiro passo que resolve:
  1. thread do Gmail (resposta ao e-mail de entrega/cobrança)
  2. nº do pedido no assunto/corpo (aceito só se o e-mail do pedido é o do remetente)
  3. e-mail do remetente e e-mails escritos no corpo
  4. telefone e CPF escritos no corpo
  5. comprovante anexo (nome do pagador lido pela IA) — só se os passos baratos falharem
  6. nome do remetente: nome completo, depois primeiro + último nome

Regra de ouro (medição de 27/09/2026): só vale quando os pedidos PAGOS encontrados são de UMA
pessoa. Nome comum ('Vera Lucia': 273 pessoas) vira lista de candidatos para o humano escolher.
Pedido não pago só conta nos passos 1–4 (identificador forte); por nome, nunca.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

import database as db

ESTADOS_PAGOS = (0, 1000)

# Metodos que identificam a cliente com certeza (podem virar resposta automática); nome e
# comprovante (lido por IA) sempre passam por aprovação humana.
METODOS_FORTES = ('thread', 'numero_pedido', 'email', 'telefone', 'cpf')

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
             ler_comprovantes: Callable[[], list] | None = None) -> Vinculo:
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
            if escolhido:
                return Vinculo(pedido=escolhido, metodo=metodo)
            candidatos_ambiguos = candidatos_ambiguos or candidatos

    return Vinculo(candidatos=candidatos_ambiguos[:20])
