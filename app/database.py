"""
Módulo de conexão com o banco de dados MySQL.
"""
import os
import mysql.connector
from mysql.connector import Error
from contextlib import contextmanager
import logging
from typing import TypedDict, Optional

# Configuração de logging
logging.basicConfig(level=logging.INFO)
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
    campaignid = pedido.get('campaignid')
    adgroupid = pedido.get('adgroupid')
    creative = pedido.get('creative')
    matchtype = pedido.get('matchtype')
    device = pedido.get('device')
    placement = pedido.get('placement')
    video_id = pedido.get('video_id')
    path_comprovante = pedido.get('path_comprovante'), None

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
           , campaignid
           , adgroupid
           , creative
           , matchtype
           , device
           , placement
           , video_id
           , path_comprovante
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
           , campaignid
           , adgroupid
           , creative
           , matchtype
           , device
           , placement
           , video_id
           , path_comprovante
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
def atualizar_pedido_com_pagamento(pedido_id, valor_pago):
    """
    Atualiza um pedido com o valor pago e estado de pago.

    Args:
        pedido_id: ID do pedido
        valor_pago: Valor pago

    Returns:
        int: ID do pedido
    """
    query = "UPDATE pedidos SET valor_pago = %s, estado_id = 0 WHERE id = %s"
    db.execute_query(query, (valor_pago, pedido_id))
    return pedido_id
