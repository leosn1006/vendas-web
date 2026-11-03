"""Conversões da Meta: sem rede e sem MySQL. As consultas de verdade de database.py rodam num SQLite em memória, com a
tradução mínima do dialeto em `_para_sqlite`."""
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta

# Como no container (app/ copiado para /app): imports "database", "fluxos"...
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'app'))

# lead_incluir importa o agente de IA, que cria o cliente OpenAI já no import (não é chamado nos testes).
os.environ.setdefault('OPENAI_API_KEY', 'sk-teste-nao-usada')

import pytest  # noqa: E402

_COLUNAS_PEDIDOS = """
    produto_id, guid, valor_pago, estado_id, fluxo_inicial, gclid, wbraid, gbraid, fbc, client_ip, client_user_agent,
    data_ultima_atualizacao, mensagem_sugerida, emoji_sugerida, data_contato_site, phone_number_id, contact_phone,
    contact_name, bsuid, contact_to, data_pedido, interesse_produto, campaignid, adgroupid, creative, matchtype, device,
    placement, video_id, path_comprovante, data_followup, nome_banco, nome_pagador, data_pagamento, data_envio_pedido,
    data_envio_google_ads, data_envio_meta, data_agendamento_pagamento, dns_origem, email
"""

_ESQUEMA = f"""
    CREATE TABLE pedidos (id INTEGER PRIMARY KEY AUTOINCREMENT, {_COLUNAS_PEDIDOS});
    CREATE TABLE campanhas (produto_id INT, campaignid TEXT, nome TEXT NOT NULL, venda_web INT DEFAULT 0,
                            plataforma TEXT NOT NULL DEFAULT 'google', PRIMARY KEY (produto_id, campaignid));
    CREATE TABLE orcamento_campanha (produto_id INT, campaignid TEXT, data TEXT, valor_investido REAL, cliques INT,
                                     impressoes INT, PRIMARY KEY (produto_id, campaignid, data));
    CREATE TABLE meta_dataset_dns (id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INT, dns TEXT, dataset_id TEXT,
                                   token_env_var TEXT, ativo INT DEFAULT 1, UNIQUE (produto_id, dns));
    CREATE TABLE google_ads_planilha_dns (id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INT, dns TEXT,
                                          google_sheets_spreadsheet_id TEXT, google_sheets_sheet_name TEXT,
                                          google_ads_conversion_name TEXT, google_sa_env_var TEXT, ativo INT DEFAULT 1);
    CREATE TABLE musicas (id INTEGER PRIMARY KEY, pedido_origem_id INT);
    CREATE TABLE musica_pedidos (pedido_id INT PRIMARY KEY, musica_id INT);
"""


def _para_sqlite(sql: str) -> str:
    sql = sql.replace('%s', '?')
    sql = sql.replace('NOW() - INTERVAL 6 DAY', "datetime('now', 'localtime', '-6 days')")
    sql = sql.replace('INSERT IGNORE', 'INSERT OR IGNORE')
    if 'ON DUPLICATE KEY UPDATE' in sql:
        sql = re.sub(r'VALUES\((\w+)\)', r'excluded.\1', sql).replace('ON DUPLICATE KEY UPDATE', 'ON CONFLICT DO UPDATE SET')
    if 'UPDATE pedidos p JOIN musicas' in sql:  # vincular_pedido: UPDATE ... JOIN vira UPDATE ... FROM
        sql = re.sub(r'UPDATE pedidos p JOIN musicas m ON m\.id = \? JOIN pedidos o ON o\.id = m\.pedido_origem_id\s+SET',
                     'UPDATE pedidos AS p SET', sql)
        cabeca, resto = re.split(r'\bWHERE\b', sql, maxsplit=1)
        sql = (re.sub(r'\bp\.(\w+) = o\.', r'\1 = o.', cabeca)
               + 'FROM musicas m JOIN pedidos o ON o.id = m.pedido_origem_id WHERE m.id = ? AND' + resto)
    return sql


class BancoSqlite:
    def __init__(self):
        self.conexao = sqlite3.connect(':memory:')
        self.conexao.row_factory = sqlite3.Row
        self.conexao.executescript(_ESQUEMA)

    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False, return_rowcount=False):
        cursor = self.conexao.execute(_para_sqlite(query), params or ())
        if fetch_one:
            linha = cursor.fetchone()
            return dict(linha) if linha else None
        if fetch_all:
            return [dict(l) for l in cursor.fetchall()]
        return cursor.rowcount if return_rowcount else cursor.lastrowid

    def pedido(self, **campos) -> int:
        nomes = ', '.join(campos)
        marcas = ', '.join('?' for _ in campos)
        return self.conexao.execute(f'INSERT INTO pedidos ({nomes}) VALUES ({marcas})', tuple(campos.values())).lastrowid

    def campanha(self, campaignid, produto_id=1, nome=None, plataforma='google', venda_web=0):
        self.conexao.execute('INSERT INTO campanhas (produto_id, campaignid, nome, plataforma, venda_web) VALUES (?, ?, ?, ?, ?)',
                             (produto_id, campaignid, nome or campaignid, plataforma, venda_web))

    def dataset(self, dns='site.com', produto_id=1, dataset_id='999', token_env_var='META_TOKEN_LSN', ativo=1):
        self.conexao.execute('INSERT INTO meta_dataset_dns (produto_id, dns, dataset_id, token_env_var, ativo) VALUES (?, ?, ?, ?, ?)',
                             (produto_id, dns, dataset_id, token_env_var, ativo))

    def ler_pedido(self, pedido_id) -> dict:
        return dict(self.conexao.execute('SELECT * FROM pedidos WHERE id = ?', (pedido_id,)).fetchone())

    def ler_campanha(self, campaignid, produto_id=1):
        linha = self.conexao.execute('SELECT * FROM campanhas WHERE produto_id = ? AND campaignid = ?',
                                     (produto_id, campaignid)).fetchone()
        return dict(linha) if linha else None

    def contar(self, tabela) -> int:
        return self.conexao.execute(f'SELECT COUNT(*) FROM {tabela}').fetchone()[0]


@pytest.fixture
def banco(monkeypatch):
    import database
    falso = BancoSqlite()
    monkeypatch.setattr(database.db, 'execute_query', falso.execute_query)
    return falso


@pytest.fixture
def venda_meta(banco):
    """Cria uma venda paga que entra na seleção; os campos passados sobrescrevem os padrões."""
    def criar(**campos):
        padrao = dict(produto_id=1, estado_id=1000, valor_pago=47.9, campaignid='123', dns_origem='site.com', gclid='',
                      fbc='fb.1.1700000000000.AbC', client_ip='200.1.2.3', client_user_agent='Mozilla/5.0',
                      email=' Maria@Exemplo.com ', contact_phone='556181163324', data_pagamento=dias_atras(1))
        return banco.pedido(**{**padrao, **campos})
    return criar


def dias_atras(dias: float) -> str:
    """Data em horário local, como o banco grava."""
    return (datetime.now() - timedelta(days=dias)).strftime('%Y-%m-%d %H:%M:%S')
