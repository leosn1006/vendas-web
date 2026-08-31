#!/usr/bin/env python3
"""
Backfill retroativo de guid + pedido_itens para pedidos pagos via web
(estado_id = 1000) que nunca tiveram um dos dois — irmão de
backfill_pedido_guid_itens.py (que cobre WhatsApp, estado_id = 0), necessário
porque aquele script filtra estado_id = 0 de propósito e nunca tocou nos web.

Escopo e limitações, de propósito:
  1. Só estado_id = 1000 (pago). Estados intermediários do web (1001-1006,
     leads não convertidos) não recebem guid/itens aqui — mesma regra de
     sempre: só quem pagou tem acesso a /pedido/<guid>.
  2. Reconstrói só 'principal' + 'bonus' atuais do produto (mesma limitação
     do script irmão) — NÃO reconstrói 'bump': não há registro confiável de
     qual order bump foi aceito em pedidos antigos sem pedido_itens, então
     preferimos deixar de fora a arriscar gravar um bump que o cliente não
     comprou. Pedidos que tinham bump pago aparecerão na Estante sem esse
     item — aceitável, o principal continua acessível.
  3. O valor gravado no item 'principal' vem de resolver_valor_principal_produto
     (preço ATUAL do produto), não de pedidos.valor_pago — de propósito,
     porque valor_pago pode incluir um bump somado, e usá-lo infliaria o
     valor do item 'principal' em pedido_itens (afetaria relatórios de
     receita que somam essa coluna).
  4. Só grava itens pra quem realmente não tem NENHUM ainda (checa via
     listar_itens_pedido antes de chamar criar_itens_pedido_web) — o pedido
     pode ter caído no filtro só por falta de guid, já com itens gravados no
     checkout original; chamar criar_itens_pedido_web de novo duplicaria
     essas linhas (e o produto pode ter trocado de e-book principal/bônus
     desde a compra, então o item novo nem representaria o mesmo livro
     vendido).

Na prática a maioria dos pedidos web já tem guid e pedido_itens (gerados no
próprio checkout desde 2026-07-05, migration 041) — este script cobre as
sobras de antes disso e qualquer lacuna pontual.

Idempotente: o filtro já exclui quem não precisa de nada (guid já preenchido
E pedido_itens já existente), então rodar de novo não duplica nada.

Uso:
    python scripts/backfill_pedido_web_guid_itens.py --dry-run
    python scripts/backfill_pedido_web_guid_itens.py
    python scripts/backfill_pedido_web_guid_itens.py --data-inicio 2026-01-01
    python scripts/backfill_pedido_web_guid_itens.py --lote 1000 --max-pedidos 500
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

from database import db, resolver_valor_principal_produto, criar_itens_pedido_web, listar_itens_pedido
from mysql.connector import IntegrityError

LOTE_PADRAO = 2000
MAX_TENTATIVAS_GUID = 5
DATA_INICIO_PADRAO = '2026-01-01'

QUERY_PENDENTES = """
    SELECT p.id, p.guid, p.produto_id
    FROM pedidos p
    WHERE p.estado_id = 1000
      AND p.data_pagamento BETWEEN %s AND NOW()
      AND (p.guid IS NULL
           OR NOT EXISTS (SELECT 1 FROM pedido_itens pi WHERE pi.pedido_id = p.id))
    ORDER BY p.id
    LIMIT %s
"""


def contar_pendentes(data_inicio):
    row = db.execute_query(
        """SELECT COUNT(*) AS total FROM pedidos p
           WHERE p.estado_id = 1000
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

        # A query já filtra por (guid IS NULL OR itens ausentes), então um pedido pode cair
        # aqui só por falta de guid, já com pedido_itens gravado no checkout original — chamar
        # criar_itens_pedido_web incondicionalmente duplicaria esses itens (e o produto pode
        # ter mudado de e-book principal/bônus desde a compra, então o item novo nem seria o
        # mesmo livro do original). Só cria itens quando o pedido realmente não tem nenhum.
        if listar_itens_pedido(p['id']):
            continue

        ebook_principal, valor_principal = resolver_valor_principal_produto(p['produto_id'])
        if not ebook_principal:
            print(f"  ⚠️  pedido {p['id']}: produto {p['produto_id']} sem e-book principal cadastrado, pulando itens")
            continue
        criar_itens_pedido_web(p['id'], p['produto_id'], ebook_principal, valor_principal)
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
    print(f"Pedidos pagos via web (estado_id=1000) entre {args.data_inicio} e agora, sem guid e/ou sem pedido_itens: {total_pendente}")

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
