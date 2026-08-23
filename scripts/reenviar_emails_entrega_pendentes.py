#!/usr/bin/env python3
"""
Reenvia o e-mail de entrega do e-book para pedidos pagos hoje que ficaram sem
receber (data_envio_ebook IS NULL) — incidente: email_remetente novo
(tempero@/fatia@lsnlivros.com.br) não estava verificado como alias no Google
Workspace, e o envio via Gmail API falhava silenciosamente (retry 1x e desiste).

Idempotente: reusa fluxos.entrega_pedido_email.executar(), que já checa
data_envio_ebook antes de mandar — seguro rodar mais de uma vez.

Uso:
    python scripts/reenviar_emails_entrega_pendentes.py --dry-run
    python scripts/reenviar_emails_entrega_pendentes.py
    python scripts/reenviar_emails_entrega_pendentes.py --produto-id 11 12
"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Este script roda no host, fora da rede Docker: DB_HOST='db' (nome do serviço,
# usado pelos containers) não resolve aqui. O MySQL é publicado em 127.0.0.1:3306
# (ver docker-compose.yml), então trocamos para localhost quando aplicável.
if os.getenv('DB_HOST') == 'db':
    os.environ['DB_HOST'] = 'localhost'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import db
from fluxos.entrega_pedido_email import executar


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--produto-id', nargs='+', type=int, default=[11, 12])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    placeholders = ','.join(['%s'] * len(args.produto_id))
    pedidos = db.execute_query(
        f"""SELECT id, produto_id, email, contact_name
            FROM pedidos
            WHERE produto_id IN ({placeholders})
              AND estado_id = 1000
              AND data_envio_ebook IS NULL
              AND data_pagamento >= CURDATE()
            ORDER BY id""",
        tuple(args.produto_id), fetch_all=True
    )

    print(f"{len(pedidos)} pedido(s) pago(s) hoje sem e-mail de entrega:")
    for p in pedidos:
        print(f"  #{p['id']}  produto={p['produto_id']}  {p['email']}  {p['contact_name']}")

    if args.dry_run:
        print("\n--dry-run: nada foi enviado.")
        return

    print()
    ok, erro = 0, 0
    for p in pedidos:
        try:
            executar(p['id'])
            print(f"  OK   #{p['id']}")
            ok += 1
        except Exception as e:
            print(f"  ERRO #{p['id']}: {e}")
            erro += 1

    print(f"\nConcluído: {ok} reenviado(s), {erro} com erro.")


if __name__ == '__main__':
    main()
