#!/usr/bin/env python3
"""
Varre os pedidos web (estado_id >= 1000) em busca de e-mails com formato suspeito
de erro de digitação — mesma regra usada no checkout (web/email_validacao.py):
domínio malformado ou "sobra" depois de um domínio comum (ex: gmail.comm,
gmail.compraiagrande). Só leitura — não altera nada, não reenvia nada.

Serve para levantar os pedidos já existentes com e-mail provavelmente errado,
pra decidir contato manual (ex: pedir e-mail alternativo).

Uso:
    python scripts/auditar_emails_invalidos.py
    python scripts/auditar_emails_invalidos.py --todos-estados
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
from web.email_validacao import validar_email


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--todos-estados', action='store_true',
                         help='Inclui todos os pedidos web (estado_id >= 1000), '
                              'não só os pagos (estado_id = 1000)')
    args = parser.parse_args()

    condicao = 'estado_id >= 1000' if args.todos_estados else 'estado_id = 1000'
    pedidos = db.execute_query(
        f"""SELECT id, produto_id, email, contact_name, data_pedido
            FROM pedidos
            WHERE {condicao} AND email IS NOT NULL AND email != ''
            ORDER BY id""",
        fetch_all=True
    )

    invalidos = [(p, validar_email(p['email'])) for p in pedidos]
    invalidos = [(p, r) for p, r in invalidos if not r['valido']]

    print(f"{len(invalidos)} de {len(pedidos)} pedido(s) com e-mail suspeito de erro de digitação:\n")
    for p, r in invalidos:
        sugestao = f", sugestão: {r['sugestao']}" if r['sugestao'] else ''
        print(f"  #{p['id']}  produto={p['produto_id']}  {p['email']}  "
              f"({r['motivo']}{sugestao})  — {p['contact_name']}  ({p['data_pedido']})")


if __name__ == '__main__':
    main()
