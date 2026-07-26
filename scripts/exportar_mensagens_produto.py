#!/usr/bin/env python3
"""
Exporta para CSV as mensagens de mensagens_pedidos de um produto, para
análise de texto (ex: dores/reclamações de clientes) em notebook.

Uso:
    python scripts/exportar_mensagens_produto.py --produto-id 11 --dias 30
    make exportar-mensagens produto=11 dias=30
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

# Este script roda no host, fora da rede Docker: DB_HOST='db' (nome do serviço,
# usado pelos containers) não resolve aqui. O MySQL é publicado em 127.0.0.1:3306
# (ver docker-compose.yml), então trocamos para localhost quando aplicável.
if os.getenv('DB_HOST') == 'db':
    os.environ['DB_HOST'] = 'localhost'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database import db

COLUNAS = ['pedido_id', 'sequencial_mensagem', 'data_mensagem', 'tipo_mensagem', 'mensagem_texto']


def buscar_mensagens(produto_id, data_inicio=None):
    query = """
        SELECT mp.pedido_id, mp.sequencial_mensagem, mp.data_mensagem,
               mp.tipo_mensagem, mp.mensagem_json AS mensagem_texto
        FROM mensagens_pedidos mp
        JOIN pedidos p ON mp.pedido_id = p.id
        WHERE p.produto_id = %s
    """
    params = [produto_id]

    if data_inicio:
        query += " AND DATE(p.data_contato_site) > %s"
        params.append(data_inicio)

    query += " ORDER BY mp.pedido_id, mp.sequencial_mensagem ASC"

    return db.execute_query(query, tuple(params), fetch_all=True)


def exportar_csv(linhas, caminho_saida):
    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
    with open(caminho_saida, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=COLUNAS)
        writer.writeheader()
        writer.writerows(linhas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--produto-id', type=int, required=True)
    parser.add_argument('--dias', type=int, default=15,
                         help="Exporta mensagens dos últimos N dias (default: 15).")
    args = parser.parse_args()

    data_inicio = (datetime.now() - timedelta(days=args.dias)).strftime('%Y-%m-%d')

    caminho_saida = os.path.join(
        os.path.dirname(__file__), '..', 'static-mensagens',
        f'mensagens_produto_{args.produto_id}.csv'
    )

    linhas = buscar_mensagens(args.produto_id, data_inicio)
    exportar_csv(linhas, caminho_saida)

    pedidos_distintos = len({linha['pedido_id'] for linha in linhas})
    print(f"Mensagens exportadas: {len(linhas)}")
    print(f"Pedidos distintos: {pedidos_distintos}")
    print(f"Arquivo: {caminho_saida}")


if __name__ == '__main__':
    main()
