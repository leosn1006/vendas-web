"""
Módulo de conexão com o banco de dados MySQL.
"""
import os
import mysql.connector
from mysql.connector import Error
from contextlib import contextmanager
import logging
from typing import TypedDict, Optional

logger = logging.getLogger(__name__)


class Database:
    """
    Classe para gerenciar conexões com o banco de dados MySQL.
    """

    def __init__(self):
        """
        Inicializa as configurações de conexão com o banco de dados.
        """
        self.config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'database': os.getenv('DB_NAME', 'vendasdb'),
            'user': os.getenv('DB_USER', 'appuser'),
            'password': os.getenv('DB_PASSWORD', ''),
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci',
            'autocommit': False,
            'pool_name': 'vendas_pool',
            'pool_size': 5,
            'pool_reset_session': True
        }
        self._connection_pool = None

    def _create_pool(self):
        """
        Cria um pool de conexões com o banco de dados.
        """
        if self._connection_pool is None:
            try:
                self._connection_pool = mysql.connector.pooling.MySQLConnectionPool(**self.config)
                logger.info(f"Pool de conexões criado: {self.config['database']}@{self.config['host']}")
            except Error as e:
                logger.error(f"Erro ao criar pool de conexões: {e}")
                raise

    def get_connection(self):
        """
        Obtém uma conexão do pool.

        Returns:
            mysql.connector.connection.MySQLConnection: Conexão com o banco de dados
        """
        if self._connection_pool is None:
            self._create_pool()

        try:
            connection = self._connection_pool.get_connection()
            return connection
        except Error as e:
            logger.error(f"Erro ao obter conexão: {e}")
            raise

    @contextmanager
    def get_cursor(self, dictionary=True, buffered=True):
        """
        Context manager para obter um cursor do banco de dados.

        Args:
            dictionary: Se True, retorna resultados como dicionários
            buffered: Se True, faz buffer dos resultados

        Yields:
            mysql.connector.cursor.MySQLCursor: Cursor do banco de dados
        """
        connection = self.get_connection()
        cursor = None
        try:
            cursor = connection.cursor(dictionary=dictionary, buffered=buffered)
            yield cursor
            connection.commit()
        except Error as e:
            if connection:
                connection.rollback()
            logger.error(f"Erro na operação do banco de dados: {e}")
            raise
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        """
        Executa uma query no banco de dados.

        Args:
            query: Query SQL a ser executada
            params: Parâmetros da query (opcional)
            fetch_one: Se True, retorna apenas um resultado
            fetch_all: Se True, retorna todos os resultados

        Returns:
            Resultado da query ou None
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, params or ())

            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()

            return cursor.lastrowid

    def execute_many(self, query, params_list):
        """
        Executa múltiplas queries com diferentes parâmetros.

        Args:
            query: Query SQL a ser executada
            params_list: Lista de tuplas com os parâmetros

        Returns:
            Número de linhas afetadas
        """
        with self.get_cursor() as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount

    def test_connection(self):
        """
        Testa a conexão com o banco de dados.

        Returns:
            bool: True se a conexão for bem-sucedida, False caso contrário
        """
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                logger.info("✅ Conexão com o banco de dados OK")
                return result is not None
        except Error as e:
            logger.error(f"❌ Erro ao testar conexão: {e}")
            return False


# Instância global do banco de dados
db = Database()


# Funções auxiliares para operações comuns

def get_produto_by_id(produto_id):
    """
    Busca um produto pelo ID.

    Args:
        produto_id: ID do produto

    Returns:
        dict: Dados do produto ou None
    """
    query = "SELECT * FROM produtos WHERE id = %s AND ativo = TRUE"
    return db.execute_query(query, (produto_id,), fetch_one=True)

class Pedido(TypedDict):
    id: Optional[int]
    produto_id: Optional[int]
    valor_pago: Optional[float]
    estado_id: int
    gclid: Optional[str]
    data_ultima_atualizacao: Optional[str]
    mensagem_sugerida: Optional[str]
    emoji_sugerida: Optional[str]
    data_contato_site: Optional[str]
    interesse_produto: Optional[bool]
    phone_number_id: Optional[str]
    contact_phone: Optional[str]
    contact_name: Optional[str]
    data_pedido: Optional[str]
    campaignid: Optional[str]
    adgroupid: Optional[str]
    creative: Optional[str]
    matchtype: Optional[str]
    device: Optional[str]
    placement: Optional[str]
    video_id: Optional[str]
    path_comprovante: Optional[str]
    data_followup: Optional[str]
    nome_banco: Optional[str]
    nome_pagador: Optional[str]
    data_pagamento: Optional[str]
    data_envio_pedido: Optional[str]
    data_envio_google_ads: Optional[str]
    data_agendamento_pagamento: Optional[str]

def criar_pedido(pedido: Pedido):
    """
    Cria um novo pedido.
    Args:
        Pedido: Dicionário com os dados do pedido, incluindo:
    Returns:
        int: ID do pedido criado
    """
    produto_id = pedido.get('produto_id') or 0
    valor_pago = pedido.get('valor_pago') or 0.0
    estado_id = 1  # Estado Iniciado
    gclid = pedido.get('gclid')
    mensagem_sugerida = pedido.get('mensagem_sugerida')
    emoji_sugerida = pedido.get('emoji_sugerida')
    phone_number_id = pedido.get('phone_number_id')
    contact_phone = pedido.get('contact_phone')
    contact_name = pedido.get('contact_name')
    data_pedido = pedido.get('data_pedido')
    interesse_produto = pedido.get('interesse_produto')  # None se não informado
    campaignid = pedido.get('campaignid')
    adgroupid = pedido.get('adgroupid')
    creative = pedido.get('creative')
    matchtype = pedido.get('matchtype')
    device = pedido.get('device')
    placement = pedido.get('placement')
    video_id = pedido.get('video_id')
    path_comprovante = pedido.get('path_comprovante') or ""
    data_followup = pedido.get('data_followup')
    nome_banco = pedido.get('nome_banco')
    nome_pagador = pedido.get('nome_pagador')
    data_pagamento = pedido.get('data_pagamento')
    data_envio_pedido = pedido.get('data_envio_pedido')
    data_envio_google_ads = pedido.get('data_envio_google_ads')
    data_agendamento_pagamento = pedido.get('data_agendamento_pagamento')


    query = """
        INSERT INTO pedidos (
             produto_id
           , valor_pago
           , estado_id
           , gclid
           , data_ultima_atualizacao
           , mensagem_sugerida
           , emoji_sugerida
           , data_contato_site
           , phone_number_id
           , contact_phone
           , contact_name
           , data_pedido
           , interesse_produto
           , campaignid
           , adgroupid
           , creative
           , matchtype
           , device
           , placement
           , video_id
           , path_comprovante
           , data_followup
           , nome_banco
           , nome_pagador
           , data_pagamento
           , data_envio_pedido
           , data_envio_google_ads
           , data_agendamento_pagamento
            )
        VALUES (
             %s
           , %s
           , %s
           , %s
           , CURRENT_TIMESTAMP
           , %s
           , %s
           , CURRENT_TIMESTAMP
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           , %s
           )
    """
    pedido_id = db.execute_query(query, (
             produto_id
           , valor_pago
           , estado_id
           , gclid
           , mensagem_sugerida
           , emoji_sugerida
           , phone_number_id
           , contact_phone
           , contact_name
           , data_pedido
           , interesse_produto
           , campaignid
           , adgroupid
           , creative
           , matchtype
           , device
           , placement
           , video_id
           , path_comprovante
           , data_followup
           , nome_banco
           , nome_pagador
           , data_pagamento
           , data_envio_pedido
           , data_envio_google_ads
           , data_agendamento_pagamento
        ))
    return pedido_id


def atualizar_estado_pedido(pedido_id, novo_estado_id):
    """
    Atualiza o estado de um pedido.

    Args:
        pedido_id: ID do pedido
        novo_estado_id: ID do novo estado

    Returns:
        int: ID do pedido
    """

    query = "UPDATE pedidos SET estado_id = %s WHERE id = %s"
    db.execute_query(query, (novo_estado_id, pedido_id))
    return pedido_id


def salvar_mensagem_pedido(mensagem_id, pedido_id, mensagem_json, tipo_mensagem='recebida'):
    """
    Salva uma mensagem relacionada a um pedido.

    Args:
        mensagem_id: ID da mensagem do WhatsApp
        pedido_id: ID do pedido
        mensagem_json: JSON da mensagem
        tipo_mensagem: Tipo da mensagem (recebida ou enviada)

    Returns:
        str: ID da mensagem
    """
    # Buscar o próximo sequencial para este pedido
    query_seq = """
        SELECT COALESCE(MAX(sequencial_mensagem), 0) + 1 as proximo_sequencial
        FROM mensagens_pedidos
        WHERE pedido_id = %s
    """
    result = db.execute_query(query_seq, (pedido_id,), fetch_one=True)
    sequencial = result['proximo_sequencial'] if result else 1

    query = """
        INSERT INTO mensagens_pedidos (message_id, pedido_id, sequencial_mensagem, mensagem_json, tipo_mensagem)
        VALUES (%s, %s, %s, %s, %s)
    """
    db.execute_query(query, (mensagem_id, pedido_id, sequencial, mensagem_json, tipo_mensagem))
    return mensagem_id

def get_pedido(id_pedido):
    """
    Busca um pedido pelo ID.

    Args:
        dict: Pedidos

    Returns:
        dict: Dados do pedido ou None
    """
    query = """
        SELECT *
        FROM pedidos p
        WHERE p.id = %s
    """
    return db.execute_query(query, (id_pedido,), fetch_one=True)

def atualizar_txid_pedido(pedido_id: int, txid: str) -> None:
    """Salva o txid do BB Pay no pedido."""
    db.execute_query(
        "UPDATE pedidos SET txid = %s WHERE id = %s",
        (txid, pedido_id)
    )


def get_pedido_by_txid(txid: str):
    """Busca um pedido pelo txid do BB Pay."""
    return db.execute_query(
        "SELECT * FROM pedidos WHERE txid = %s",
        (txid,), fetch_one=True
    )


def get_ultimo_pedido_by_phone(contact_phone, produto_id):
    """
    Busca o último pedido de um contato pelo telefone.

    Args:
        contact_phone: Telefone do contato

    Returns:
        dict: Dados do pedido ou None
    """
    query = """
        SELECT *
        FROM pedidos p
        WHERE p.contact_phone = %s
        AND   p.produto_id    = %s
        ORDER BY p.data_pedido DESC
        LIMIT 1
    """
    return db.execute_query(query, (contact_phone, produto_id), fetch_one=True)

def get_ultimo_pedido_por_mensagem_sugerida(mensagem_sugerida):
    """
    Busca o último pedido de um contato pelo telefone.
    -- filtra pedidos que estão nos estados Iniciado
    -- filtra pedidos com mensagem sugerida igual nas últimas 1 hora
    Args:
        mensagem_sugerida: Mensagem sugerida do pedido

    Returns:
        dict: Dados do pedido ou None
    """
    query = """
        SELECT *
        FROM pedidos p
        WHERE p.mensagem_sugerida = %s
          AND p.data_contato_site >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
          AND p.estado_id         =  1
        ORDER BY p.data_pedido DESC
        LIMIT 1
    """
    return db.execute_query(query, (mensagem_sugerida,), fetch_one=True)

def vincula_pedido_com_contato(id_pedido, contact_phone, contact_name, phone_number_id):
    """
    Vincula um pedido existente a um contato.
    Args:
        id_pedido: ID do pedido
        contact_phone: Telefone do contato
        contact_name: Nome do contato
        phone_number_id: ID do número de telefone
    Returns:
        Pedido atualizado ou None se não conseguiu vincular
    """
    query = """
        UPDATE pedidos
        SET contact_phone   = %s,
            contact_name    = %s,
            phone_number_id = %s,
            estado_id       = 1,
            data_pedido     = CURRENT_TIMESTAMP
        WHERE id = %s and estado_id = 1 -- só vincula se estiver no estado Iniciado
    """
    resultado = db.execute_query(query, (contact_phone, contact_name, phone_number_id, id_pedido))
    if resultado is None:
        return None
    else:
        # devolve pedido atualizado
        pedido = get_pedido(id_pedido)
        return pedido

#atualizar pedido com caminho do comprovante
def atualizar_pedido_com_comprovante(pedido_id, path_comprovante):
    """
    Atualiza um pedido com o caminho do comprovante.

    Args:
        pedido_id: ID do pedido
        path_comprovante: Caminho do comprovante

    Returns:
        int: ID do pedido
    """
    query = "UPDATE pedidos SET path_comprovante = %s WHERE id = %s"
    db.execute_query(query, (path_comprovante, pedido_id))
    return pedido_id

# atualizar pedido com o valor pago e estado de pago
def atualizar_pedido_com_pagamento(pedido_id, valor_pago, nome_banco, nome_pagador, data_pagamento):
    """
    Atualiza um pedido com o valor pago e estado de pago.

    Args:
        pedido_id: ID do pedido
        valor_pago: Valor pago
        nome_banco: Nome do banco pagador
        nome_pagador: Nome do pagador
        data_pagamento: Data do pagamento

    Returns:
        int: ID do pedido
    """
    query = "UPDATE pedidos SET valor_pago = %s, nome_banco = %s, nome_pagador = %s, data_pagamento = %s, estado_id = 0 WHERE id = %s"
    db.execute_query(query, (valor_pago, nome_banco, nome_pagador, data_pagamento, pedido_id))
    return pedido_id

def atualizar_pedido_com_interesse_produto(pedido_id, interesse_produto):
    """
    Atualiza um pedido com o interesse do produto.

    Args:
        pedido_id: ID do pedido
        interesse_produto: Interesse do produto (True/False)

    Returns:
        int: ID do pedido
    """
    query = "UPDATE pedidos SET interesse_produto = %s WHERE id = %s"
    db.execute_query(query, (interesse_produto, pedido_id))
    return pedido_id

def atualizar_pedido_com_data_followup(pedido_id):
    """
    Atualiza um pedido com a data do followup.

    Args:
        pedido_id: ID do pedido

    Returns:
        int: ID do pedido
    """
    query = "UPDATE pedidos SET data_followup = CURRENT_TIMESTAMP WHERE id = %s"
    db.execute_query(query, (pedido_id,))
    return pedido_id

def atualizar_pedido_com_data_envio_pedido(pedido_id):
    """
    Atualiza um pedido com a data do envio do pedido.

    Args:
        pedido_id: ID do pedido

    Returns:
        int: ID do pedido
    """
    query = "UPDATE pedidos SET data_envio_pedido = CURRENT_TIMESTAMP WHERE id = %s"
    db.execute_query(query, (pedido_id,))
    return pedido_id

def buscar_pedidos_followup( horas_sem_atualizacao: int) -> list:
    query = """
        SELECT *
        FROM pedidos
        WHERE estado_id = 3 -- estado 'produto enviado, aguardando pagamento'
        AND data_envio_pedido < NOW() - INTERVAL %s HOUR
        AND contact_phone IS NOT NULL
        AND interesse_produto = 1
    """
    return db.execute_query(query, (horas_sem_atualizacao,), fetch_all=True)

def buscar_historico_conversa(pedido_id: int, limite: int = 10) -> list:
    """Busca as últimas mensagens do pedido formatadas para a OpenAI."""
    query = """
        SELECT tipo_mensagem, mensagem_json
        FROM mensagens_pedidos
        WHERE pedido_id = %s
        ORDER BY sequencial_mensagem DESC
        LIMIT %s
    """
    mensagens = db.execute_query(query, (pedido_id, limite), fetch_all=True)

    # Proteção defensiva
    if not mensagens:
        return []

    # Reverte para ordem cronológica
    mensagens = list(reversed(mensagens))

    return [
        {
            "role": "assistant" if msg['tipo_mensagem'] == 'enviada' else "user",
            "content": msg['mensagem_json']
        }
        for msg in mensagens
    ]

def busca_vendas_pendentes_google()-> list:
    """
    Busca vendas que converteram e possuem GCLID, mas ainda não foram enviadas para o Google Ads.
    Retorna também as configurações do Google Sheets do produto (para exportação offline).
    """
    query = """
        SELECT p.*,
               pr.id AS produto_id,
               pr.google_sheets_spreadsheet_id,
               pr.google_sheets_sheet_name,
               pr.google_ads_conversion_name
        FROM pedidos p
        JOIN produtos pr ON pr.id = p.produto_id
        WHERE p.gclid IS NOT NULL
          AND p.gclid != ''
          AND p.estado_id = 0 -- estado Pago
          AND p.data_envio_google_ads IS NULL
          AND pr.google_sheets_spreadsheet_id IS NOT NULL
    """
    vendas = db.execute_query(query, fetch_all=True)
    #proteção defensiva caso o banco retorne None
    if vendas is None:
        return []

    return vendas

def marcar_venda_como_enviada_ao_google_ads(pedido_id):
    """
    Atualiza o pedido para marcar que a venda foi enviada ao Google Ads.
    """
    query = "UPDATE pedidos SET data_envio_google_ads = CURRENT_TIMESTAMP WHERE id = %s"
    db.execute_query(query, (pedido_id,))
    return pedido_id


# ── telefones_produto ─────────────────────────────────────────────────────────

def get_produto_by_phone_number_id(phone_number_id):
    """
    Busca o produto associado a um phone_number_id do WhatsApp Business.
    Usado como fallback quando campaignid/gclid não chegam.

    Args:
        phone_number_id: Número WhatsApp do vendedor (phone_number_id da API)

    Returns:
        dict: Dados do produto ou None
    """
    query = """
        SELECT p.*
        FROM produtos p
        INNER JOIN telefones_produto tp ON tp.produto_id = p.id
        WHERE tp.telefone = %s AND p.ativo = TRUE
        LIMIT 1
    """
    return db.execute_query(query, (phone_number_id,), fetch_one=True)


def listar_telefones_produto(produto_id):
    """
    Lista todos os telefones associados a um produto.

    Args:
        produto_id: ID do produto

    Returns:
        list: Lista de dicts com id, telefone, created_at
    """
    query = """
        SELECT id, telefone, created_at
        FROM telefones_produto
        WHERE produto_id = %s
        ORDER BY created_at ASC
    """
    return db.execute_query(query, (produto_id,), fetch_all=True) or []


def adicionar_telefone_produto(telefone, produto_id):
    """
    Adiciona um mapeamento telefone → produto.

    Args:
        telefone: phone_number_id do WhatsApp Business
        produto_id: ID do produto

    Returns:
        int: ID do registro criado
    """
    query = "INSERT INTO telefones_produto (telefone, produto_id) VALUES (%s, %s)"
    return db.execute_query(query, (telefone, produto_id))


def remover_telefone_produto(telefone_id):
    """
    Remove um mapeamento telefone → produto pelo ID do registro.

    Args:
        telefone_id: ID do registro em telefones_produto
    """
    query = "DELETE FROM telefones_produto WHERE id = %s"
    db.execute_query(query, (telefone_id,))


# ── mensagens_sugeridas_produto ───────────────────────────────────────────────

def listar_mensagens_sugeridas(produto_id):
    """
    Lista todas as mensagens sugeridas de um produto.

    Returns:
        list: Lista de dicts com id e mensagem
    """
    query = "SELECT id, mensagem FROM mensagens_sugeridas_produto WHERE produto_id = %s ORDER BY id ASC"
    return db.execute_query(query, (produto_id,), fetch_all=True) or []


def adicionar_mensagem_sugerida(produto_id, mensagem):
    """
    Adiciona uma mensagem sugerida para um produto.

    Returns:
        int: ID do registro criado
    """
    query = "INSERT INTO mensagens_sugeridas_produto (produto_id, mensagem) VALUES (%s, %s)"
    return db.execute_query(query, (produto_id, mensagem))


def remover_mensagem_sugerida(mensagem_id):
    """Remove uma mensagem sugerida pelo ID."""
    db.execute_query("DELETE FROM mensagens_sugeridas_produto WHERE id = %s", (mensagem_id,))


# ============================================================
# Ações de fluxo por produto  (tabela acoes_fluxo_produto)
# ============================================================

def listar_acoes_fluxo(produto_id, fluxo):
    """Retorna todas as ações de um fluxo para um produto, ordenadas por condicao e ordem."""
    return db.execute_query(
        "SELECT * FROM acoes_fluxo_produto WHERE produto_id = %s AND fluxo = %s ORDER BY condicao, ordem",
        (produto_id, fluxo), fetch_all=True
    ) or []


def get_acao_fluxo(acao_id):
    """Retorna uma ação pelo ID."""
    return db.execute_query(
        "SELECT * FROM acoes_fluxo_produto WHERE id = %s",
        (acao_id,), fetch_one=True
    )


def adicionar_acao_fluxo(produto_id, fluxo, ordem, condicao, acao,
                          url, mensagem, caption, nome_arquivo,
                          delay_inicial, delay_final,
                          param1=None, param2=None):
    """Insere uma nova ação de fluxo. Retorna o ID criado."""
    return db.execute_query(
        """INSERT INTO acoes_fluxo_produto
               (produto_id, fluxo, ordem, condicao, acao,
                url, mensagem, caption, nome_arquivo, delay_inicial, delay_final,
                param1, param2)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (produto_id, fluxo, ordem, condicao, acao,
         url or None, mensagem or None, caption or None, nome_arquivo or None,
         delay_inicial, delay_final,
         param1 or None, param2 or None)
    )


def atualizar_acao_fluxo(acao_id, ordem, condicao, acao,
                          url, mensagem, caption, nome_arquivo,
                          delay_inicial, delay_final,
                          param1=None, param2=None):
    """Atualiza uma ação existente pelo ID."""
    db.execute_query(
        """UPDATE acoes_fluxo_produto SET
               ordem=%s, condicao=%s, acao=%s,
               url=%s, mensagem=%s, caption=%s, nome_arquivo=%s,
               delay_inicial=%s, delay_final=%s,
               param1=%s, param2=%s
           WHERE id=%s""",
        (ordem, condicao, acao,
         url or None, mensagem or None, caption or None, nome_arquivo or None,
         delay_inicial, delay_final,
         param1 or None, param2 or None,
         acao_id)
    )


def remover_acao_fluxo(acao_id):
    """Remove uma ação de fluxo pelo ID."""
    db.execute_query("DELETE FROM acoes_fluxo_produto WHERE id = %s", (acao_id,))


def buscar_todas_mensagens_pedido(pedido_id: int) -> list:
    """Retorna todas as mensagens de um pedido em ordem cronológica."""
    rows = db.execute_query(
        "SELECT tipo_mensagem, mensagem_json, sequencial_mensagem, data_mensagem "
        "FROM mensagens_pedidos WHERE pedido_id = %s ORDER BY sequencial_mensagem ASC",
        (pedido_id,), fetch_all=True
    )
    return rows if rows else []


def buscar_pedido_por_nome(contact_name: str, produto_id: int):
    """Busca o pedido mais recente de um cliente pelo nome (contact_name)."""
    return db.execute_query(
        "SELECT * FROM pedidos WHERE contact_name LIKE %s AND produto_id = %s "
        "ORDER BY data_pedido DESC LIMIT 1",
        (f"%{contact_name}%", produto_id), fetch_one=True
    )


def acertar_valor_pedido(pedido_id: int, valor_pago: float):
    """Marca um pedido como pago com o valor informado e registra data_pagamento."""
    db.execute_query(
        "UPDATE pedidos SET valor_pago = %s, estado_id = 0, data_pagamento = NOW() WHERE id = %s",
        (valor_pago, pedido_id)
    )


# ============================================================
# Funções do fluxo Web Checkout (tabelas produto_web / pedido_web / pagamento_web)
# Independentes do fluxo WhatsApp — não tocam na tabela pedidos
# ============================================================

def get_produto_web(produto_web_id: int):
    """Retorna produto_web por id ou None."""
    return db.execute_query(
        "SELECT * FROM produto_web WHERE id = %s AND ativo = 1",
        (produto_web_id,), fetch_one=True
    )


def criar_pedido_web(remetente_id: str, valor: float, gclid: str = '',
                     phone_contact: str = '', nome_cliente: str = '',
                     email: str = '', campaignid: str = '',
                     adgroupid: str = '', creative: str = '',
                     matchtype: str = '', device: str = '',
                     placement: str = '', video_id: str = '') -> int:
    """Cria um pedido_web com estado=1 (Pedido criado). Retorna o id gerado."""
    return db.execute_query(
        """INSERT INTO pedido_web
             (estado, valor, remetente_id, gclid, phone_contact, nome_cliente, email,
              campaignid, adgroupid, creative, matchtype, device, placement, video_id)
           VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (valor, remetente_id, gclid or '', phone_contact or '',
         nome_cliente or '', email or '',
         campaignid or '', adgroupid or '', creative or '',
         matchtype or '', device or '', placement or '', video_id or '')
    )


def get_pedido_web(pedido_web_id: int):
    """Retorna pedido_web por id ou None."""
    return db.execute_query(
        "SELECT * FROM pedido_web WHERE id = %s",
        (pedido_web_id,), fetch_one=True
    )


def get_pedido_web_by_numero_solicitacao(numero_solicitacao: str):
    """Retorna pedido_web pelo txid BB Pay ou None."""
    return db.execute_query(
        "SELECT * FROM pedido_web WHERE numero_solicitacao = %s",
        (numero_solicitacao,), fetch_one=True
    )


def atualizar_numero_solicitacao_pedido_web(pedido_web_id: int, txid: str):
    """Salva o txid BB Pay e avança estado para 2 (Aguardando pagamento)."""
    db.execute_query(
        "UPDATE pedido_web SET numero_solicitacao = %s, estado = 2 WHERE id = %s",
        (txid, pedido_web_id)
    )


def atualizar_estado_pedido_web(pedido_web_id: int, estado: int):
    """Atualiza o estado de um pedido_web."""
    db.execute_query(
        "UPDATE pedido_web SET estado = %s WHERE id = %s",
        (estado, pedido_web_id)
    )


def atualizar_phone_name_pedido_web(pedido_web_id: int, phone_name: str):
    """Preenche o nome do cliente após entrega via WhatsApp."""
    db.execute_query(
        "UPDATE pedido_web SET phone_name = %s WHERE id = %s",
        (phone_name, pedido_web_id)
    )


def criar_pagamento_web(pedido_web_id: int, valor: float,
                        tipo_pagamento: str = 'Pix',
                        nome_pagador: str = '', id_pagador: str = '',
                        e2e_pix: str = '', valor_tarifa: float = None) -> int:
    """Registra o pagamento confirmado em pagamento_web. Retorna o id gerado."""
    return db.execute_query(
        """INSERT INTO pagamento_web
             (pedido_web_id, valor, valor_tarifa, data_pagamento,
              tipo_pagamento, id_pagador, nome_pagador, e2e_pix)
           VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s)""",
        (pedido_web_id, valor, valor_tarifa,
         tipo_pagamento, id_pagador or '', nome_pagador or '', e2e_pix or '')
    )


# ============================================================
# Funções do fluxo Web Checkout Unificado (tabela pedidos)
# Usam estados 1001/1002/1003 para não conflitar com o fluxo WhatsApp (0-4).
# ============================================================

def get_produto_disponivel_web(produto_id: int):
    """Retorna produto de `produtos` habilitado para venda web ou None."""
    return db.execute_query(
        "SELECT * FROM produtos WHERE id = %s AND disponivel_web = TRUE AND ativo = TRUE",
        (produto_id,), fetch_one=True
    )


def get_phone_number_id_produto(produto_id: int):
    """Retorna o phone_number_id WhatsApp Business associado ao produto ou None."""
    row = db.execute_query(
        "SELECT telefone FROM telefones_produto WHERE produto_id = %s LIMIT 1",
        (produto_id,), fetch_one=True
    )
    return row['telefone'] if row else None


def criar_pedido_web_unificado(produto_id: int, phone_number_id: str,
                               contact_phone: str, contact_name: str,
                               email: str = '', gclid: str = '',
                               campaignid: str = '', adgroupid: str = '',
                               creative: str = '', matchtype: str = '',
                               device: str = '', placement: str = '',
                               video_id: str = '') -> int:
    """Cria pedido em `pedidos` com estado 1001 (Pedido web criado). Retorna o id."""
    return db.execute_query(
        """INSERT INTO pedidos
             (produto_id, valor_pago, estado_id, gclid,
              data_ultima_atualizacao, data_contato_site, data_pedido,
              phone_number_id, contact_phone, contact_name, email,
              campaignid, adgroupid, creative, matchtype, device, placement, video_id)
           VALUES (%s, 0.0, 1001, %s,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                   %s, %s, %s, %s,
                   %s, %s, %s, %s, %s, %s, %s)""",
        (produto_id, gclid or '',
         phone_number_id or '', contact_phone or '', contact_name or '', email or '',
         campaignid or '', adgroupid or '', creative or '',
         matchtype or '', device or '', placement or '', video_id or '')
    )


def atualizar_pedido_solicitacao_bb(pedido_id: int, numero_solicitacao_bb: str,
                                    url_bbpay: str = '', qr_code_pix: str = '',
                                    expiracao: str = '') -> None:
    """Salva dados da solicitação BB Pay e avança estado para 1002 (Aguardando pagamento)."""
    db.execute_query(
        """UPDATE pedidos
           SET estado_id = 1002,
               numero_solicitacao_bb = %s,
               url_bbpay = %s,
               qr_code_pix = %s,
               expiracao_solicitacao_bb = %s,
               data_ultima_atualizacao = CURRENT_TIMESTAMP
           WHERE id = %s""",
        (numero_solicitacao_bb, url_bbpay or '', qr_code_pix or '',
         expiracao or None, pedido_id)
    )


def get_pedido_by_solicitacao_bb(numero_solicitacao_bb: str):
    """Retorna pedido pelo txid BB Pay ou None."""
    return db.execute_query(
        "SELECT * FROM pedidos WHERE numero_solicitacao_bb = %s",
        (numero_solicitacao_bb,), fetch_one=True
    )


def confirmar_pagamento_web(pedido_id: int, valor: float, nome_pagador: str = '') -> None:
    """Confirma pagamento web: avança para estado 1000 e registra dados do pagador."""
    db.execute_query(
        """UPDATE pedidos
           SET estado_id = 1000,
               valor_pago = %s,
               nome_pagador = %s,
               data_pagamento = CURRENT_TIMESTAMP,
               data_ultima_atualizacao = CURRENT_TIMESTAMP
           WHERE id = %s""",
        (valor, nome_pagador or '', pedido_id)
    )


def marcar_ebook_enviado(pedido_id: int) -> None:
    """Registra o momento em que o ebook foi enviado via WhatsApp."""
    db.execute_query(
        """UPDATE pedidos
           SET data_envio_ebook = CURRENT_TIMESTAMP,
               data_ultima_atualizacao = CURRENT_TIMESTAMP
           WHERE id = %s""",
        (pedido_id,)
    )
