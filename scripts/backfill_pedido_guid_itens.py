#!/usr/bin/env python3
"""
Backfill retroativo de guid + pedido_itens para pedidos já pagos via WhatsApp
(estado_id = 0), que nunca tiveram nenhum dos dois — pra habilitar a tela
/pedido/<guid> pra clientes antigos que reclamarem de um produto já comprado.

Escopo reduzido de propósito, em duas frentes:
  1. Só estado_id = 0 (pago). Pedidos nunca pagos NÃO recebem guid/itens aqui —
     se um cliente não-pago reclamar, ele simplesmente ainda não tem o link
     (mesma regra de sempre: só quem pagou tem acesso).
  2. Só pedidos pagos a partir de --data-inicio (padrão 2026-07-01) até agora —
     rodar em toda a base histórica (44 mil pedidos) levou ~9 minutos pra um
     ganho prático pequeno; a intenção é atender reclamações de compras
     recentes, não reconstruir anos de histórico.

Reaproveita get_ebook_principal_produto/criar_itens_pedido_web (as mesmas
funções usadas pelo checkout web e por criar_pedido no fluxo WhatsApp) — grava
o item 'principal' + os 'bonus' atuais do produto, sem bump (bump não existe
no WhatsApp).

Idempotente: o filtro já exclui quem não precisa de nada (guid já preenchido
E pedido_itens já existente), então rodar de novo não duplica nada.

Uso:
    python scripts/backfill_pedido_guid_itens.py --dry-run
    python scripts/backfill_pedido_guid_itens.py
    python scripts/backfill_pedido_guid_itens.py --data-inicio 2026-01-01
    python scripts/backfill_pedido_guid_itens.py --lote 1000 --max-pedidos 500
"""
import argparse
import os
import secrets
import sys

from dotenv import load_dotenv

load_dotenv()

# Este script roda no host, fora da rede Docker: DB_HOST='db' (nome do serviço,
# usado pelos containers) não resolve aqui. O MySQL é publicado em 127.0.0.1:3306
# (ver docker-compose.yml), então trocamos para localhost quando aplicável.
if os.getenv('DB_HOST') == 'db':
    os.environ['DB_HOST'] = 'localhost'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import db, get_ebook_principal_produto, criar_itens_pedido_web
from mysql.connector import IntegrityError

LOTE_PADRAO = 2000
MAX_TENTATIVAS_GUID = 5
DATA_INICIO_PADRAO = '2026-07-01'

QUERY_PENDENTES = """
    SELECT p.id, p.guid, p.produto_id, p.valor_pago
    FROM pedidos p
    WHERE p.estado_id = 0
      AND p.data_pagamento BETWEEN %s AND NOW()
      AND (p.guid IS NULL
           OR NOT EXISTS (SELECT 1 FROM pedido_itens pi WHERE pi.pedido_id = p.id))
    ORDER BY p.id
    LIMIT %s
"""


def contar_pendentes(data_inicio):
    row = db.execute_query(
        """SELECT COUNT(*) AS total FROM pedidos p
           WHERE p.estado_id = 0
             AND p.data_pagamento BETWEEN %s AND NOW()
             AND (p.guid IS NULL
                  OR NOT EXISTS (SELECT 1 FROM pedido_itens pi WHERE pi.pedido_id = p.id))""",
        (data_inicio,), fetch_one=True,
    )
    return row['total']


def atualizar_guid_com_retry(pedido_id):
    """Gera e grava um guid novo pro pedido, tentando de novo em caso de colisão na UNIQUE KEY
    (probabilidade ínfima, mas não nula — ver migration 062)."""
    for tentativa in range(1, MAX_TENTATIVAS_GUID + 1):
        guid = secrets.token_urlsafe(6)
        try:
            db.execute_query("UPDATE pedidos SET guid = %s WHERE id = %s", (guid, pedido_id))
            return guid
        except IntegrityError as e:
            if 'uk_pedidos_guid' not in str(e):
                raise
            print(f"  ⚠️  colisão de guid pro pedido {pedido_id} (tentativa {tentativa}), gerando outro...")
    raise RuntimeError(f"Não foi possível gerar um guid único pro pedido {pedido_id} após {MAX_TENTATIVAS_GUID} tentativas")


def processar_lote(pedidos):
    guids_gerados = 0
    itens_criados = 0
    for p in pedidos:
        if p['guid'] is None:
            atualizar_guid_com_retry(p['id'])
            guids_gerados += 1

        ebook_principal = get_ebook_principal_produto(p['produto_id'])
        if not ebook_principal:
            print(f"  ⚠️  pedido {p['id']}: produto {p['produto_id']} sem e-book principal cadastrado, pulando itens")
            continue
        criar_itens_pedido_web(p['id'], p['produto_id'], ebook_principal, p['valor_pago'])
        itens_criados += 1

    return guids_gerados, itens_criados


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lote', type=int, default=LOTE_PADRAO, help="Tamanho do lote por iteração.")
    parser.add_argument('--max-pedidos', type=int, default=None, help="Limite total de pedidos a processar (pra testar num subconjunto).")
    parser.add_argument('--data-inicio', default=DATA_INICIO_PADRAO, help=f"Só processa pedidos pagos a partir desta data (padrão {DATA_INICIO_PADRAO}), até agora.")
    parser.add_argument('--dry-run', action='store_true', help="Só mostra quantos pedidos seriam afetados, não escreve nada.")
    args = parser.parse_args()

    total_pendente = contar_pendentes(args.data_inicio)
    print(f"Pedidos pagos via WhatsApp (estado_id=0) entre {args.data_inicio} e agora, sem guid e/ou sem pedido_itens: {total_pendente}")

    if total_pendente == 0:
        print("Nada a fazer.")
        return

    if args.dry_run:
        print("Dry-run: nenhuma escrita feita.")
        return

    total_guids = 0
    total_itens = 0
    total_processado = 0

    while True:
        if args.max_pedidos is not None and total_processado >= args.max_pedidos:
            break

        lote = args.lote
        if args.max_pedidos is not None:
            lote = min(lote, args.max_pedidos - total_processado)

        pedidos = db.execute_query(QUERY_PENDENTES, (args.data_inicio, lote), fetch_all=True)
        if not pedidos:
            break

        guids, itens = processar_lote(pedidos)
        total_guids += guids
        total_itens += itens
        total_processado += len(pedidos)
        print(f"Processados {total_processado} pedidos até agora (guids gerados: {total_guids}, itens criados: {total_itens})")

    print(f"\nConcluído. Total processado: {total_processado} | guids gerados: {total_guids} | itens criados: {total_itens}")


if __name__ == '__main__':
    main()
