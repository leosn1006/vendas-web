"""
Módulo de conexão com o banco de dados MySQL.
"""
import os
import mysql.connector
from mysql.connector import Error
from contextlib import contextmanager
import logging

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


def get_produtos_ativos():
    """
    Retorna todos os produtos ativos.

    Returns:
        list: Lista de produtos
    """
    query = "SELECT * FROM produtos WHERE ativo = TRUE ORDER BY nome"
    return db.execute_query(query, fetch_all=True)


def criar_pedido(mensagem_venda, produto_id, contact_name, contact_phone):
    """
    Cria um novo pedido.

    Args:
        mensagem_venda: Mensagem de venda
        produto_id: ID do produto
        contact_name: Nome do contato
        contact_phone: Telefone do contato

    Returns:
        int: ID do pedido criado
    """
    query = """
        INSERT INTO pedidos (mensagem_venda, produto_id, contact_name, contact_phone, estado_pedido_id)
        VALUES (%s, %s, %s, %s, 1)
    """
    return db.execute_query(query, (mensagem_venda, produto_id, contact_name, contact_phone))


def atualizar_estado_pedido(pedido_id, novo_estado_id):
    """
    Atualiza o estado de um pedido.

    Args:
        pedido_id: ID do pedido
        novo_estado_id: ID do novo estado

    Returns:
        int: ID do pedido
    """
    query = "UPDATE pedidos SET estado_pedido_id = %s WHERE id = %s"
    db.execute_query(query, (novo_estado_id, pedido_id))
    return pedido_id


def salvar_mensagem_pedido(mensagem_id, pedido_id, mensagem_json, tipo_mensagem='recebida'):
    """
    Salva uma mensagem relacionada a um pedido.

    Args:
        mensagem_id: ID da mensagem
        pedido_id: ID do pedido
        mensagem_json: JSON da mensagem
        tipo_mensagem: Tipo da mensagem (recebida ou enviada)

    Returns:
        str: ID da mensagem
    """
    query = """
        INSERT INTO mensagens_pedidos (id, pedido_id, mensagem_json, tipo_mensagem)
        VALUES (%s, %s, %s, %s)
    """
    db.execute_query(query, (mensagem_id, pedido_id, mensagem_json, tipo_mensagem))
    return mensagem_id


def get_pedido_by_phone(contact_phone):
    """
    Busca o último pedido de um contato pelo telefone.

    Args:
        contact_phone: Telefone do contato

    Returns:
        dict: Dados do pedido ou None
    """
    query = """
        SELECT p.*, ep.descricao as estado_descricao, prod.nome as produto_nome
        FROM pedidos p
        JOIN estado_pedidos ep ON p.estado_pedido_id = ep.id
        JOIN produtos prod ON p.produto_id = prod.id
        WHERE p.contact_phone = %s
        ORDER BY p.data_pedido DESC
        LIMIT 1
    """
    return db.execute_query(query, (contact_phone,), fetch_one=True)
