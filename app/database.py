"""
Módulo de conexão com o banco de dados MySQL.
"""
import os
import time
import mysql.connector
from mysql.connector import Error, IntegrityError
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
            'pool_reset_session': True,
            'connection_timeout': 10,
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
                from whatsapp import notificar_admin_erro_sistema
                notificar_admin_erro_sistema(f"MYSQL | falha ao criar pool | {type(e).__name__}", log="log_app")
                raise

    def get_connection(self):
        if self._connection_pool is None:
            self._create_pool()

        for attempt in range(1, 4):
            try:
                return self._connection_pool.get_connection()
            except Error as e:
                if attempt < 3:
                    logger.warning(f"Erro ao obter conexão (tentativa {attempt}/3): {e}")
                    time.sleep(2 * attempt)
                    self._connection_pool = None
                    self._create_pool()
                else:
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

    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False, return_rowcount=False):
        """
        Executa uma query no banco de dados.

        Args:
            query: Query SQL a ser executada
            params: Parâmetros da query (opcional)
            fetch_one: Se True, retorna apenas um resultado
            fetch_all: Se True, retorna todos os resultados
            return_rowcount: Se True, retorna cursor.rowcount (útil para UPDATE/DELETE)

        Returns:
            Resultado da query ou None
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, params or ())

            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()
            elif return_rowcount:
                return cursor.rowcount

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
    wbraid: Optional[str]
    gbraid: Optional[str]
    data_ultima_atualizacao: Optional[str]
    mensagem_sugerida: Optional[str]
    emoji_sugerida: Optional[str]
    data_contato_site: Optional[str]
    interesse_produto: Optional[bool]
    phone_number_id: Optional[str]
    contact_phone: Optional[str]
    contact_name: Optional[str]
    bsuid: Optional[str]
    contact_to: Optional[str]
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
    dns_origem: Optional[str]

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
    wbraid = pedido.get('wbraid')
    gbraid = pedido.get('gbraid')
    mensagem_sugerida = (pedido.get('mensagem_sugerida') or '')[:255] or None
    emoji_sugerida = pedido.get('emoji_sugerida')
    phone_number_id = pedido.get('phone_number_id')
    contact_phone = pedido.get('contact_phone') or None
    contact_name = pedido.get('contact_name')
    bsuid = pedido.get('bsuid')
    contact_to = pedido.get('contact_to') or None
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
    dns_origem = pedido.get('dns_origem')


    query = """
        INSERT INTO pedidos (
             produto_id
           , valor_pago
           , estado_id
           , gclid
           , wbraid
           , gbraid
           , data_ultima_atualizacao
           , mensagem_sugerida
           , emoji_sugerida
           , data_contato_site
           , phone_number_id
           , contact_phone
           , contact_name
           , bsuid
           , contact_to
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
           , dns_origem
            )
        VALUES (
             %s
           , %s
           , %s
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
           , wbraid
           , gbraid
           , mensagem_sugerida
           , emoji_sugerida
           , phone_number_id
           , contact_phone
           , contact_name
           , bsuid
           , contact_to
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
           , dns_origem
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


def tentar_travar_fluxo(pedido_id, estado_atual, estado_travado):
    """Atomicamente move pedido de estado_atual → estado_travado.
    Retorna True se adquiriu o lock, False se já estava travado (0 rows afetadas)."""
    with db.get_cursor() as cursor:
        cursor.execute(
            "UPDATE pedidos SET estado_id = %s WHERE id = %s AND estado_id = %s",
            (estado_travado, pedido_id, estado_atual),
        )
        return cursor.rowcount > 0


def salvar_mensagem_recebida_simples(pedido_id, mensagem_whatsapp):
    """Extrai message_id e texto da payload WhatsApp e salva como mensagem recebida."""
    dados_msg = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]
    message_id = dados_msg['id']
    mensagem_txt = dados_msg.get('text', {}).get('body', '') or ''
    salvar_mensagem_pedido(message_id, pedido_id, mensagem_txt, tipo_mensagem='recebida')


def buscar_ultima_mensagem_recebida_por_pedido(pedido_id: int, minutos: int = 10):
    """Retorna o texto da última mensagem recebida neste pedido nos últimos N minutos."""
    query = """
        SELECT mensagem_json
        FROM mensagens_pedidos
        WHERE pedido_id = %s
          AND tipo_mensagem = 'recebida'
          AND data_mensagem >= NOW() - INTERVAL %s MINUTE
        ORDER BY data_mensagem DESC
        LIMIT 1
    """
    row = db.execute_query(query, (pedido_id, minutos), fetch_one=True)
    return row['mensagem_json'] if row else None


def contar_comprovantes_recebidos_recentes(pedido_id: int, minutos: int = 5) -> int:
    """Conta comprovantes (imagens/docs) recebidos neste pedido nos últimos N minutos."""
    query = """
        SELECT COUNT(*) AS total
        FROM mensagens_pedidos
        WHERE pedido_id = %s
          AND tipo_mensagem = 'recebida'
          AND mensagem_json LIKE 'Comprovante recebido:%'
          AND data_mensagem >= NOW() - INTERVAL %s MINUTE
    """
    row = db.execute_query(query, (pedido_id, minutos), fetch_one=True)
    return row['total'] if row else 0


def pedido_dentro_da_janela_24h(pedido_id: int) -> bool:
    """True se há mensagem RECEBIDA do cliente nas últimas 24h (comparação em SQL,
    usando NOW() do próprio MySQL — evita mismatch de timezone app/banco).
    Pedido sem nenhuma mensagem recebida retorna False (não há janela aberta)."""
    query = """
        SELECT COUNT(*) AS total
        FROM mensagens_pedidos
        WHERE pedido_id = %s
          AND tipo_mensagem = 'recebida'
          AND data_mensagem >= NOW() - INTERVAL 24 HOUR
    """
    row = db.execute_query(query, (pedido_id,), fetch_one=True)
    return bool(row and row['total'] > 0)


def buscar_data_ultima_mensagem_recebida_pedido(pedido_id: int):
    """Datetime da última mensagem recebida do cliente neste pedido, ou None
    se ele nunca enviou nada. Usado só para exibição no banner."""
    query = """
        SELECT MAX(data_mensagem) AS ultima
        FROM mensagens_pedidos
        WHERE pedido_id = %s AND tipo_mensagem = 'recebida'
    """
    row = db.execute_query(query, (pedido_id,), fetch_one=True)
    return row['ultima'] if row else None


def contar_total_mensagens_pedido(pedido_id: int) -> int:
    """Retorna o sequencial máximo de mensagens do pedido (equivale ao total acumulado)."""
    query = "SELECT COALESCE(MAX(sequencial_mensagem), 0) AS total FROM mensagens_pedidos WHERE pedido_id = %s"
    row = db.execute_query(query, (pedido_id,), fetch_one=True)
    return row['total'] if row else 0


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
    query_seq = """
        SELECT COALESCE(MAX(sequencial_mensagem), 0) + 1 as proximo_sequencial
        FROM mensagens_pedidos
        WHERE pedido_id = %s
    """
    query_insert = """
        INSERT INTO mensagens_pedidos (message_id, pedido_id, sequencial_mensagem, mensagem_json, tipo_mensagem)
        VALUES (%s, %s, %s, %s, %s)
    """
    for tentativa in range(5):
        result = db.execute_query(query_seq, (pedido_id,), fetch_one=True)
        sequencial = result['proximo_sequencial'] if result else 1
        try:
            db.execute_query(query_insert, (mensagem_id, pedido_id, sequencial, mensagem_json, tipo_mensagem))
            return mensagem_id
        except IntegrityError as e:
            if e.errno == 1062 and 'uk_pedido_sequencial' in str(e) and tentativa < 4:
                logger.warning(f"Colisão de sequencial para pedido {pedido_id} (tentativa {tentativa + 1}), retentar...")
                continue
            raise

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


def get_ultimo_pedido_by_phone(contact_phone, produto_id, phone_number_id=None):
    if phone_number_id is not None:
        query = """
            SELECT *
            FROM pedidos p
            WHERE p.contact_phone   = %s
            AND   p.produto_id      = %s
            AND   p.phone_number_id = %s
            ORDER BY p.data_pedido DESC
            LIMIT 1
        """
        return db.execute_query(query, (contact_phone, produto_id, phone_number_id), fetch_one=True)

    query = """
        SELECT *
        FROM pedidos p
        WHERE p.contact_phone = %s
        AND   p.produto_id    = %s
        ORDER BY p.data_pedido DESC
        LIMIT 1
    """
    return db.execute_query(query, (contact_phone, produto_id), fetch_one=True)

def get_ultimo_pedido_by_bsuid(bsuid, produto_id, phone_number_id=None):
    if not bsuid:
        return None
    if phone_number_id is not None:
        query = """
            SELECT *
            FROM pedidos p
            WHERE p.bsuid          = %s
            AND   p.produto_id     = %s
            AND   p.phone_number_id = %s
            ORDER BY p.data_pedido DESC
            LIMIT 1
        """
        return db.execute_query(query, (bsuid, produto_id, phone_number_id), fetch_one=True)
    query = """
        SELECT *
        FROM pedidos p
        WHERE p.bsuid      = %s
        AND   p.produto_id = %s
        ORDER BY p.data_pedido DESC
        LIMIT 1
    """
    return db.execute_query(query, (bsuid, produto_id), fetch_one=True)

def get_ultimo_pedido_por_mensagem_sugerida(mensagem_sugerida, produto_id, phone_number_id):
    """
    Busca o último pedido de um contato pelo telefone.
    -- filtra pedidos que estão nos estados Iniciado
    -- filtra pedidos com mensagem sugerida igual nas últimas 1 hora
    Args:
        mensagem_sugerida: Mensagem sugerida do pedido
        produto_id: ID do produto — evita vincular ao produto errado quando a mensagem é idêntica
        phone_number_id: ID do telefone que recebeu a mensagem — garante que o pedido foi direcionado para este telefone

    Returns:
        dict: Dados do pedido ou None
    """
    query = """
        SELECT *
        FROM pedidos p
        WHERE p.mensagem_sugerida = %s
          AND p.produto_id        = %s
          AND p.phone_number_id   = %s
          AND p.data_contato_site >= DATE_SUB(NOW(), INTERVAL 30 MINUTE)
          AND p.estado_id         =  1
        ORDER BY p.data_pedido DESC
        LIMIT 1
    """
    return db.execute_query(query, (mensagem_sugerida, produto_id, phone_number_id), fetch_one=True)

def vincula_pedido_com_contato(id_pedido, contact_phone, contact_name, phone_number_id,
                               bsuid=None, contact_to=None):
    """
    Vincula um pedido existente a um contato.
    Args:
        id_pedido: ID do pedido
        contact_phone: Telefone do contato (pode ser vazio se for usuário com username)
        contact_name: Nome do contato
        phone_number_id: ID do número de telefone
        bsuid: Business-Scoped User ID (quando telefone não está disponível)
        contact_to: Identificador para resposta — telefone ou BSUID
    Returns:
        Pedido atualizado ou None se não conseguiu vincular
    """
    query = """
        UPDATE pedidos
        SET contact_phone   = %s,
            contact_name    = %s,
            phone_number_id = %s,
            bsuid           = %s,
            contact_to      = %s,
            estado_id       = 1,
            data_pedido     = CURRENT_TIMESTAMP
        WHERE id = %s and estado_id = 1 -- só vincula se estiver no estado Iniciado
    """
    rows_affected = db.execute_query(query, (contact_phone or None, contact_name, phone_number_id,
                                              bsuid or None, contact_to or None, id_pedido),
                                     return_rowcount=True)
    if not rows_affected:
        return None
    return get_pedido(id_pedido)

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

def bloquear_followup_pedido(pedido_id: int) -> None:
    """Marca todas as datas de followup com o timestamp atual, impedindo que o beat scheduler
    envie qualquer followup para este pedido (o scheduler só processa pedidos com essas colunas NULL)."""
    db.execute_query(
        """UPDATE pedidos
           SET data_followup          = CURRENT_TIMESTAMP,
               data_followup_interesse_1 = CURRENT_TIMESTAMP,
               data_followup_interesse_2 = CURRENT_TIMESTAMP
           WHERE id = %s""",
        (pedido_id,),
    )


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
        AND contact_to IS NOT NULL
        AND interesse_produto = 1
    """
    return db.execute_query(query, (horas_sem_atualizacao,), fetch_all=True)

def buscar_pedidos_followup_pagamento_web(minutos_sem_atualizacao: int = 60) -> list:
    query = """
        SELECT *
        FROM pedidos
        WHERE estado_id = 1002 -- estado 'Aguardando pagamento BB Pay'
        AND email IS NOT NULL AND email != ''
        AND data_followup_pagamento_web IS NULL
        AND data_ultima_atualizacao <= NOW() - INTERVAL %s MINUTE
        AND expiracao_solicitacao_bb > NOW()
    """
    return db.execute_query(query, (minutos_sem_atualizacao,), fetch_all=True)

def marcar_followup_pagamento_web_enviado(pedido_id: int) -> None:
    db.execute_query(
        "UPDATE pedidos SET data_followup_pagamento_web = CURRENT_TIMESTAMP WHERE id = %s",
        (pedido_id,)
    )

def buscar_pedidos_followup_interesse_1() -> list:
    query = """
        SELECT *
        FROM pedidos
        WHERE estado_id = 2
          AND data_followup_interesse_1 IS NULL
          AND data_ultima_atualizacao <= NOW() - INTERVAL 15 MINUTE
          AND contact_to IS NOT NULL
    """
    return db.execute_query(query, fetch_all=True)

def buscar_pedidos_followup_interesse_2() -> list:
    query = """
        SELECT *
        FROM pedidos
        WHERE estado_id = 2
          AND data_followup_interesse_1 IS NOT NULL
          AND data_followup_interesse_2 IS NULL
          AND data_followup_interesse_1 <= NOW() - INTERVAL 90 MINUTE
          AND contact_to IS NOT NULL
    """
    return db.execute_query(query, fetch_all=True)

def marcar_followup_interesse_1(pedido_id):
    query = "UPDATE pedidos SET data_followup_interesse_1 = NOW() WHERE id = %s"
    db.execute_query(query, (pedido_id,))

def marcar_followup_interesse_2(pedido_id):
    query = "UPDATE pedidos SET data_followup_interesse_2 = NOW() WHERE id = %s"
    db.execute_query(query, (pedido_id,))

def buscar_pedidos_aguardando_bb_pay() -> list:
    """
    Retorna pedidos em estado 1002 (Aguardando BB Pay) com solicitação ainda não expirada.
    A expiração é definida como NOW() + 24h em gerar_pix(), portanto a varredura
    nunca acumula pedidos antigos não pagos.
    """
    query = """
        SELECT id, numero_solicitacao_bb
        FROM pedidos
        WHERE estado_id = 1002
          AND numero_solicitacao_bb IS NOT NULL
          AND expiracao_solicitacao_bb > NOW()
    """
    return db.execute_query(query, fetch_all=True)

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
          AND p.estado_id IN (0, 1000) -- Pago via WhatsApp (0) ou Pago via web (1000)
          AND p.data_envio_google_ads IS NULL
          AND pr.google_sheets_spreadsheet_id IS NOT NULL
        ORDER BY p.data_pagamento ASC
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

def busca_vendas_pendentes_google_por_dns() -> list:
    """
    Busca vendas com GCLID pendentes de envio usando a tabela google_ads_planilha_dns
    (mapeamento produto × DNS de origem). Pedidos sem dns_origem ou sem mapeamento
    cadastrado na nova tabela são ignorados silenciosamente.
    """
    query = """
        SELECT p.*,
               g.produto_id,
               g.google_sheets_spreadsheet_id,
               g.google_sheets_sheet_name,
               g.google_ads_conversion_name,
               g.google_sa_env_var
        FROM pedidos p
        JOIN google_ads_planilha_dns g
          ON g.produto_id = p.produto_id
         AND g.dns        = p.dns_origem
         AND g.ativo      = TRUE
        WHERE (
                (p.gclid  IS NOT NULL AND p.gclid  != '')
             OR (p.wbraid IS NOT NULL AND p.wbraid != '')
             OR (p.gbraid IS NOT NULL AND p.gbraid != '')
              )
          AND p.estado_id IN (0, 1000)
          AND p.data_envio_google_ads IS NULL
        ORDER BY p.data_pagamento ASC
    """
    result = db.execute_query(query, fetch_all=True)
    return result if result else []


# ── google_ads_planilha_dns ───────────────────────────────────────────────────

def listar_planilhas_dns_produto(produto_id) -> list:
    result = db.execute_query(
        "SELECT * FROM google_ads_planilha_dns WHERE produto_id = %s ORDER BY dns",
        (produto_id,), fetch_all=True)
    return result or []

def adicionar_planilha_dns(produto_id, dns, spreadsheet_id, sheet_name, conversion_name, sa_env_var):
    db.execute_query(
        """INSERT INTO google_ads_planilha_dns
               (produto_id, dns, google_sheets_spreadsheet_id, google_sheets_sheet_name,
                google_ads_conversion_name, google_sa_env_var)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (produto_id, dns, spreadsheet_id, sheet_name, conversion_name, sa_env_var))

def atualizar_planilha_dns(planilha_id, dns, spreadsheet_id, sheet_name, conversion_name, sa_env_var, ativo):
    db.execute_query(
        """UPDATE google_ads_planilha_dns
           SET dns=%s, google_sheets_spreadsheet_id=%s, google_sheets_sheet_name=%s,
               google_ads_conversion_name=%s, google_sa_env_var=%s, ativo=%s
           WHERE id=%s""",
        (dns, spreadsheet_id, sheet_name, conversion_name, sa_env_var, ativo, planilha_id))

def remover_planilha_dns(planilha_id):
    db.execute_query(
        "DELETE FROM google_ads_planilha_dns WHERE id = %s", (planilha_id,))


# ── orcamento_campanha (sheets) ───────────────────────────────────────────────

def buscar_produto_id_por_campaignid(campaignid) -> int | None:
    row = db.execute_query(
        "SELECT produto_id FROM campanhas WHERE campaignid = %s LIMIT 1",
        (campaignid,), fetch_one=True)
    return row['produto_id'] if row else None

def upsert_orcamento_campanha(produto_id, campaignid, data, valor_investido, cliques, impressoes):
    db.execute_query(
        """INSERT INTO orcamento_campanha
               (produto_id, campaignid, data, valor_investido, cliques, impressoes)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE
               valor_investido = VALUES(valor_investido),
               cliques         = VALUES(cliques),
               impressoes      = VALUES(impressoes)""",
        (produto_id, campaignid, data, valor_investido, cliques, impressoes))


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
        WHERE tp.api_phone_number_id = %s AND p.ativo = TRUE
        LIMIT 1
    """
    return db.execute_query(query, (phone_number_id,), fetch_one=True)


def listar_telefones_produto(produto_id):
    """
    Lista todos os telefones associados a um produto.

    Args:
        produto_id: ID do produto

    Returns:
        list: Lista de dicts com id, telefone, api_phone_number_id, token_env_key, created_at
    """
    query = """
        SELECT id, telefone, api_phone_number_id, token_env_key, created_at, contador_uso,
               quality_rating, status_api, name_status_api, qualidade_atualizada_em, qualidade_erro
        FROM telefones_produto
        WHERE produto_id = %s
        ORDER BY created_at ASC
    """
    return db.execute_query(query, (produto_id,), fetch_all=True) or []


def atualizar_telefone_produto(telefone_id, produto_id, telefone, api_phone_number_id, token_env_key, contador_uso=0):
    query = """
        UPDATE telefones_produto
        SET telefone = %s, api_phone_number_id = %s, token_env_key = %s, contador_uso = %s
        WHERE id = %s AND produto_id = %s
    """
    db.execute_query(query, (telefone, api_phone_number_id or None, token_env_key or 'WHATSAPP_ACCESS_TOKEN', contador_uso, telefone_id, produto_id))


def selecionar_telefone_produto(produto_id):
    """
    Seleciona o telefone do produto com menor contador_uso e o incrementa.
    Garante distribuição round-robin a partir do momento de implantação,
    ignorando o histórico de pedidos anteriores.

    Returns:
        dict com id, telefone, api_phone_number_id, token_env_key ou None se não houver telefones
    """
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT id, telefone, api_phone_number_id, token_env_key
            FROM telefones_produto
            WHERE produto_id = %s
            ORDER BY contador_uso ASC, created_at ASC
            LIMIT 1
        """, (produto_id,))
        telefone = cursor.fetchone()
        if telefone:
            cursor.execute("""
                UPDATE telefones_produto SET contador_uso = contador_uso + 1
                WHERE id = %s
            """, (telefone['id'],))
    return telefone


def adicionar_telefone_produto(telefone, produto_id, api_phone_number_id=None, token_env_key='WHATSAPP_ACCESS_TOKEN'):
    """
    Adiciona um mapeamento telefone → produto.

    Args:
        telefone: display phone do WhatsApp (ex: 5561982155687), usado para lookup de produto
        produto_id: ID do produto
        api_phone_number_id: ID da API Meta (ex: 492584860944948), usado para enviar mensagens
        token_env_key: nome da variável de ambiente com o token desta conta (ex: 'WHATSAPP_ACCESS_TOKEN_2')

    Returns:
        int: ID do registro criado
    """
    query = "INSERT INTO telefones_produto (telefone, produto_id, api_phone_number_id, token_env_key) VALUES (%s, %s, %s, %s)"
    return db.execute_query(query, (telefone, produto_id, api_phone_number_id, token_env_key))


def remover_telefone_produto(telefone_id, produto_id):
    query = "DELETE FROM telefones_produto WHERE id = %s AND produto_id = %s"
    db.execute_query(query, (telefone_id, produto_id))


def listar_telefones_com_token(produto_id=None):
    """
    Números com api_phone_number_id preenchido, para a task de checagem de qualidade horária.

    Args:
        produto_id: se informado, restringe a um produto. Se None, lista de todos.

    Returns:
        list: dicts com id, produto_id, telefone, api_phone_number_id, token_env_key
    """
    query = """
        SELECT id, produto_id, telefone, api_phone_number_id, token_env_key,
               quality_rating, status_api, waba_id
        FROM telefones_produto
        WHERE api_phone_number_id IS NOT NULL AND api_phone_number_id != ''
    """
    params = ()
    if produto_id is not None:
        query += " AND produto_id = %s"
        params = (produto_id,)
    return db.execute_query(query, params, fetch_all=True) or []


_QUALITY_RATINGS_VALIDOS = {'GREEN', 'YELLOW', 'RED'}


def normalizar_quality_rating(quality_rating):
    """Mapeia qualquer valor fora de GREEN/YELLOW/RED (None, 'NA', valor futuro inesperado
    da API) para 'UNKNOWN'. A coluna é um ENUM restrito a essas 4 opções, mas a Graph API
    documenta outros valores possíveis (ex: 'NA' para número sem rating calculado ainda),
    que sem essa normalização fariam o UPDATE falhar e o número ficar preso mostrando erro
    de checagem."""
    return quality_rating if quality_rating in _QUALITY_RATINGS_VALIDOS else 'UNKNOWN'


def atualizar_qualidade_telefone(telefone_id, quality_rating, status_api=None, name_status_api=None, waba_id=None):
    """Grava o resultado bem-sucedido de uma checagem de qualidade. Limpa qualidade_erro.
    waba_id usa COALESCE pra não apagar um valor já conhecido caso a resposta não traga
    health_status por algum motivo pontual."""
    quality_rating = normalizar_quality_rating(quality_rating)
    db.execute_query(
        """UPDATE telefones_produto
           SET quality_rating = %s, status_api = %s, name_status_api = %s,
               waba_id = COALESCE(%s, waba_id),
               qualidade_atualizada_em = NOW(), qualidade_erro = NULL
           WHERE id = %s""",
        (quality_rating, status_api, name_status_api, waba_id, telefone_id)
    )


def registrar_erro_qualidade_telefone(telefone_id, erro_msg):
    """Grava falha da checagem (token inválido, número deletado, etc.) sem sobrescrever
    o último quality_rating conhecido — só marca que a checagem falhou."""
    db.execute_query(
        "UPDATE telefones_produto SET qualidade_erro = %s, qualidade_atualizada_em = NOW() WHERE id = %s",
        (erro_msg[:255], telefone_id)
    )


def contar_telefones_por_qualidade(produto_id):
    """Retorna dict {'RED': n, 'YELLOW': n, 'GREEN': n, 'UNKNOWN': n} para o produto — usado no badge do menu."""
    rows = db.execute_query(
        """SELECT quality_rating, COUNT(*) AS total
           FROM telefones_produto
           WHERE produto_id = %s AND api_phone_number_id IS NOT NULL AND api_phone_number_id != ''
           GROUP BY quality_rating""",
        (produto_id,), fetch_all=True
    ) or []
    contagem = {'RED': 0, 'YELLOW': 0, 'GREEN': 0, 'UNKNOWN': 0}
    for r in rows:
        contagem[r['quality_rating']] = r['total']
    return contagem


def get_telefone_produto_by_phone_number_id(api_phone_number_id):
    """Busca o registro de telefones_produto (id, produto_id, telefone) por api_phone_number_id.
    Usado para associar eventos de webhook de nível-número (qualidade, nome) ao telefone cadastrado."""
    return db.execute_query(
        "SELECT id, produto_id, telefone FROM telefones_produto WHERE api_phone_number_id = %s LIMIT 1",
        (api_phone_number_id,), fetch_one=True
    )


# ── notificacoes_telefone ─────────────────────────────────────────────────────

def criar_notificacao_telefone(telefone_id, produto_id, tipo_evento, mensagem, payload_raw=None):
    """Persiste um evento de webhook de nível-número (quality_update, name_update)."""
    import json as _json
    query = """
        INSERT INTO notificacoes_telefone (telefone_id, produto_id, tipo_evento, mensagem, payload_raw)
        VALUES (%s, %s, %s, %s, %s)
    """
    return db.execute_query(
        query,
        (telefone_id, produto_id, tipo_evento, mensagem,
         _json.dumps(payload_raw, ensure_ascii=False) if payload_raw is not None else None)
    )


def listar_notificacoes_telefone(telefone_id, limit=100):
    """Lista notificações de um número, mais recentes primeiro."""
    return db.execute_query(
        """SELECT id, telefone_id, tipo_evento, mensagem, created_at
           FROM notificacoes_telefone
           WHERE telefone_id = %s
           ORDER BY created_at DESC
           LIMIT %s""",
        (telefone_id, limit), fetch_all=True
    ) or []


def contar_notificacoes_telefone_recentes(produto_id, horas=24):
    """Retorna {telefone_id: total} de notificações nas últimas N horas, por telefone do produto.
    Usado para decidir o badge amarelo no botão 'Consultar histórico' de cada linha da listagem."""
    rows = db.execute_query(
        """SELECT telefone_id, COUNT(*) AS total
           FROM notificacoes_telefone
           WHERE produto_id = %s AND created_at >= NOW() - INTERVAL %s HOUR
           GROUP BY telefone_id""",
        (produto_id, horas), fetch_all=True
    ) or []
    return {r['telefone_id']: r['total'] for r in rows}


# ── notificacoes_conta_whatsapp (captura crua, sem UI nesta fase) ─────────────

def criar_notificacao_conta_whatsapp(tipo_evento, waba_id=None, business_id=None, payload_raw=None, mensagem=None):
    """Persiste evento de nível WABA/Business Manager (account_update, account_review_update,
    account_alerts, business_capability_update) — ex: aviso de spam/revisão de conta."""
    import json as _json
    return db.execute_query(
        """INSERT INTO notificacoes_conta_whatsapp (tipo_evento, waba_id, business_id, payload_raw, mensagem)
           VALUES (%s, %s, %s, %s, %s)""",
        (tipo_evento, waba_id, business_id, _json.dumps(payload_raw, ensure_ascii=False), mensagem)
    )


def listar_notificacoes_conta_whatsapp(waba_id=None, limit=200):
    """Lista eventos de nível WABA/Business Manager, mais recentes primeiro. Sem filtro
    por produto — usar listar_notificacoes_conta_whatsapp_produto pra isso."""
    query = "SELECT id, tipo_evento, mensagem, waba_id, business_id, payload_raw, created_at FROM notificacoes_conta_whatsapp"
    params = ()
    if waba_id is not None:
        query += " WHERE waba_id = %s"
        params = (waba_id,)
    query += " ORDER BY created_at DESC LIMIT %s"
    params = params + (limit,)
    return db.execute_query(query, params, fetch_all=True) or []


def listar_notificacoes_conta_whatsapp_produto(produto_id, limit=200):
    """Notificações de nível WABA/BM para as WABAs que sustentam os números deste produto
    (join indireto via waba_id, já que o evento não carrega produto_id/telefone_id)."""
    return db.execute_query(
        """SELECT id, tipo_evento, mensagem, waba_id, business_id, payload_raw, created_at
           FROM notificacoes_conta_whatsapp
           WHERE waba_id IN (
               SELECT DISTINCT waba_id FROM telefones_produto
               WHERE produto_id = %s AND waba_id IS NOT NULL
           )
           ORDER BY created_at DESC
           LIMIT %s""",
        (produto_id, limit), fetch_all=True
    ) or []


def contar_notificacoes_conta_recentes(produto_id, horas=24):
    """Total de notificações de conta/WABA nas últimas N horas pras WABAs deste produto —
    usado no badge do botão 'Notificações'."""
    row = db.execute_query(
        """SELECT COUNT(*) AS total FROM notificacoes_conta_whatsapp
           WHERE created_at >= NOW() - INTERVAL %s HOUR
           AND waba_id IN (
               SELECT DISTINCT waba_id FROM telefones_produto
               WHERE produto_id = %s AND waba_id IS NOT NULL
           )""",
        (horas, produto_id), fetch_one=True
    )
    return (row or {}).get('total', 0)


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
    """Retorna todas as ações de um fluxo para um produto, ordenadas por condicao, ordem e variante."""
    return db.execute_query(
        "SELECT * FROM acoes_fluxo_produto WHERE produto_id = %s AND fluxo = %s ORDER BY condicao, ordem, variante",
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
                          param1=None, param2=None, variante=1):
    """Insere uma nova ação de fluxo. Retorna o ID criado."""
    return db.execute_query(
        """INSERT INTO acoes_fluxo_produto
               (produto_id, fluxo, ordem, condicao, acao,
                url, mensagem, caption, nome_arquivo, delay_inicial, delay_final,
                param1, param2, variante)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (produto_id, fluxo, ordem, condicao, acao,
         url or None, mensagem or None, caption or None, nome_arquivo or None,
         delay_inicial, delay_final,
         param1 or None, param2 or None, variante or 1)
    )


def atualizar_acao_fluxo(acao_id, ordem, condicao, acao,
                          url, mensagem, caption, nome_arquivo,
                          delay_inicial, delay_final,
                          param1=None, param2=None, variante=1):
    """Atualiza uma ação existente pelo ID."""
    db.execute_query(
        """UPDATE acoes_fluxo_produto SET
               ordem=%s, condicao=%s, acao=%s,
               url=%s, mensagem=%s, caption=%s, nome_arquivo=%s,
               delay_inicial=%s, delay_final=%s,
               param1=%s, param2=%s, variante=%s
           WHERE id=%s""",
        (ordem, condicao, acao,
         url or None, mensagem or None, caption or None, nome_arquivo or None,
         delay_inicial, delay_final,
         param1 or None, param2 or None, variante or 1,
         acao_id)
    )


def remover_acao_fluxo(acao_id):
    """Remove uma ação de fluxo pelo ID."""
    db.execute_query("DELETE FROM acoes_fluxo_produto WHERE id = %s", (acao_id,))


def tipo_acao_variantes_existentes(produto_id, fluxo, condicao, ordem, excluir_acao_id=None):
    """
    Retorna o tipo de ação (coluna 'acao') já usado pelas variantes existentes
    deste passo (produto_id+fluxo+condicao+ordem), ou None se o passo ainda não
    tiver nenhuma linha. Usado para impedir que duas variantes do mesmo passo
    tenham tipos de conteúdo diferentes (ex: variante 1 = texto, variante 2 =
    imagem), o que faria o rodízio alternar o TIPO de mensagem enviada, não só o
    texto/mídia.
    """
    query = """SELECT acao FROM acoes_fluxo_produto
               WHERE produto_id=%s AND fluxo=%s AND condicao=%s AND ordem=%s"""
    params = [produto_id, fluxo, condicao, ordem]
    if excluir_acao_id:
        query += " AND id != %s"
        params.append(excluir_acao_id)
    query += " LIMIT 1"
    row = db.execute_query(query, tuple(params), fetch_one=True)
    return row['acao'] if row else None


# ============================================================
# Cursor de rodízio de variantes por número emissor (tabela variantes_fluxo_cursor)
# ============================================================

def selecionar_e_avancar_variante(phone_number_id, produto_id, fluxo, condicao, ordem, variantes_disponiveis):
    """
    Escolhe atomicamente a próxima variante em rodízio cíclico (a seguinte à
    última reservada) e já avança o cursor na MESMA transação, com lock de linha
    (SELECT ... FOR UPDATE) — evita que dois workers Celery concorrentes, processando
    pedidos diferentes para o mesmo phone_number_id+passo, leiam o mesmo estado e
    escolham a mesma variante (race condition).

    Deve ser chamada exatamente 1 vez por envio real (dentro de executar_acao(),
    no momento do envio) — nunca numa pré-varredura da lista de ações que pode
    rodar mais de uma vez por cliente (ex: fluxos com múltiplos retomadas via
    apply_async), senão o cursor avança múltiplas vezes por cliente e o rodízio
    pode "cancelar" (ex: 4 avanços com período 2 = nenhum avanço líquido).

    variantes_disponiveis: lista de linhas de acoes_fluxo_produto (dicts com pelo
    menos 'variante' e 'id') deste passo, em qualquer ordem.

    Retorna o número da variante escolhida.
    """
    numeros = sorted(v['variante'] for v in variantes_disponiveis)
    ids_por_variante = {v['variante']: v['id'] for v in variantes_disponiveis}

    with db.get_cursor() as cursor:
        # Garante que a linha do cursor exista antes de travar (idempotente).
        # ultima_variante=0 é um sentinel de "nunca enviado" — variantes reais
        # começam em 1, então nunca colide com um número de variante real.
        cursor.execute(
            """INSERT IGNORE INTO variantes_fluxo_cursor
                   (phone_number_id, produto_id, fluxo, condicao, ordem, ultima_variante)
               VALUES (%s, %s, %s, %s, %s, 0)""",
            (phone_number_id, produto_id, fluxo, condicao, ordem)
        )
        cursor.execute(
            """SELECT ultima_variante FROM variantes_fluxo_cursor
               WHERE phone_number_id=%s AND produto_id=%s AND fluxo=%s AND condicao=%s AND ordem=%s
               FOR UPDATE""",
            (phone_number_id, produto_id, fluxo, condicao, ordem)
        )
        ultima = cursor.fetchone()['ultima_variante']

        if ultima in numeros:
            proximo = numeros[(numeros.index(ultima) + 1) % len(numeros)]
        else:
            proximo = numeros[0]

        cursor.execute(
            """UPDATE variantes_fluxo_cursor SET ultima_variante=%s, acao_id=%s
               WHERE phone_number_id=%s AND produto_id=%s AND fluxo=%s AND condicao=%s AND ordem=%s""",
            (proximo, ids_por_variante[proximo], phone_number_id, produto_id, fluxo, condicao, ordem)
        )
    return proximo


# ============================================================
# Bônus e Order Bumps por produto (venda web)
# ============================================================

def listar_bonus_produto(produto_id):
    """Lista os bônus configurados para um produto, ordenados por ordem."""
    return db.execute_query(
        "SELECT * FROM produto_bonus WHERE produto_id = %s ORDER BY ordem, id",
        (produto_id,), fetch_all=True
    ) or []


def adicionar_bonus_produto(produto_id, nome, path_arquivo, nome_arquivo, descricao=None, ordem=1):
    """Adiciona um bônus a um produto. Retorna o ID criado."""
    return db.execute_query(
        """INSERT INTO produto_bonus (produto_id, nome, path_arquivo, nome_arquivo, descricao, ordem)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (produto_id, nome, path_arquivo, nome_arquivo, descricao or None, ordem)
    )


def remover_bonus_produto(bonus_id, produto_id):
    """Remove um bônus pelo ID, restrito ao produto informado (evita apagar item de outro produto)."""
    db.execute_query(
        "DELETE FROM produto_bonus WHERE id = %s AND produto_id = %s", (bonus_id, produto_id)
    )


def listar_bump_produto(produto_id):
    """Lista os order bumps configurados para um produto, ordenados por ordem."""
    return db.execute_query(
        "SELECT * FROM produto_bump WHERE produto_id = %s ORDER BY ordem, id",
        (produto_id,), fetch_all=True
    ) or []


def get_bump_produto(bump_id, produto_id):
    """Retorna um order bump pelo ID, restrito ao produto informado (evita editar/ver item de outro produto)."""
    return db.execute_query(
        "SELECT * FROM produto_bump WHERE id = %s AND produto_id = %s",
        (bump_id, produto_id), fetch_one=True
    )


def adicionar_bump_produto(produto_id, nome, path_arquivo, nome_arquivo, preco_original,
                            preco_promocional, descricao=None, ordem=1, imagem_checkout=None):
    """Adiciona um order bump a um produto. Retorna o ID criado."""
    return db.execute_query(
        """INSERT INTO produto_bump
               (produto_id, nome, path_arquivo, nome_arquivo, descricao,
                preco_original, preco_promocional, ordem, imagem_checkout)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (produto_id, nome, path_arquivo, nome_arquivo, descricao or None,
         preco_original, preco_promocional, ordem, imagem_checkout or None)
    )


def atualizar_bump_produto(bump_id, produto_id, nome, path_arquivo, nome_arquivo, preco_original,
                            preco_promocional, descricao=None, ordem=1, imagem_checkout=None):
    """Atualiza um order bump existente pelo ID, restrito ao produto informado."""
    db.execute_query(
        """UPDATE produto_bump SET
               nome=%s, path_arquivo=%s, nome_arquivo=%s, descricao=%s,
               preco_original=%s, preco_promocional=%s, ordem=%s, imagem_checkout=%s
           WHERE id=%s AND produto_id=%s""",
        (nome, path_arquivo, nome_arquivo, descricao or None,
         preco_original, preco_promocional, ordem, imagem_checkout or None, bump_id, produto_id)
    )


def remover_bump_produto(bump_id, produto_id):
    """Remove um order bump pelo ID, restrito ao produto informado (evita apagar item de outro produto)."""
    db.execute_query(
        "DELETE FROM produto_bump WHERE id = %s AND produto_id = %s", (bump_id, produto_id)
    )


def listar_bumps_validos(produto_id, bump_ids):
    """
    Retorna as linhas de `produto_bump` cujo `id` esteja em `bump_ids` E que pertençam a
    `produto_id` — nunca confie em preço/nome vindo do cliente, sempre releia do banco a
    partir só dos ids escolhidos.
    """
    bump_ids = [int(b) for b in (bump_ids or []) if str(b).isdigit()]
    if not bump_ids:
        return []
    placeholders = ','.join(['%s'] * len(bump_ids))
    return db.execute_query(
        f"SELECT * FROM produto_bump WHERE produto_id = %s AND id IN ({placeholders})",
        (produto_id, *bump_ids), fetch_all=True
    ) or []


def listar_itens_pedido(pedido_id):
    """Lista os itens gravados em `pedido_itens` para um pedido, em ordem de criação."""
    return db.execute_query(
        "SELECT * FROM pedido_itens WHERE pedido_id = %s ORDER BY id",
        (pedido_id,), fetch_all=True
    ) or []


def get_item_pedido(item_id, pedido_id):
    """Retorna um item de `pedido_itens` pelo ID, restrito ao pedido informado (evita baixar
    arquivo de outro pedido via manipulação de URL)."""
    return db.execute_query(
        "SELECT * FROM pedido_itens WHERE id = %s AND pedido_id = %s",
        (item_id, pedido_id), fetch_one=True
    )


def criar_itens_pedido_web(pedido_id, produto, valor_principal, bump_rows=None):
    """
    Grava em `pedido_itens` o snapshot do que foi incluído no pedido web no momento da
    compra: uma linha 'principal' (o produto comprado, pelo valor efetivamente cobrado por
    ele) + uma linha 'bonus' para cada bônus configurado em `produto_bonus` + uma linha
    'bump' para cada order bump aceito (já validado pelo chamador via listar_bumps_validos).

    Recebe `produto` (dict já carregado pelo chamador, ex: get_produto_disponivel_web) e
    `valor_principal` (o valor do produto principal realmente cobrado, sem os bumps) em vez
    de reconsultar o banco — evita uma query redundante e garante que o valor gravado bate
    com o que foi de fato cobrado (que pode divergir do produtos.preco por causa do override
    CHECKOUT_VALOR_TESTE_PRODUTO_<id>).

    Se o produto não tiver `url_pdf` configurado, não grava nada e apenas loga um aviso
    — evita satisfazer a coluna NOT NULL de `path_arquivo` com uma string vazia.

    Nota para quem for somar `pedido_itens.valor` em relatórios: esta função grava o item
    assim que o lead é criado (estado 1001), antes da confirmação de pagamento — pedidos
    nunca pagos também geram linhas aqui. Para receita real, sempre faça JOIN com
    `pedidos.estado_id` (só conta pago quando estado_id = 1000).
    """
    if not produto or not produto.get('url_pdf'):
        logger.warning(
            f"[PEDIDO-ITENS] ⚠️ Produto sem url_pdf configurado — pedido #{pedido_id} "
            f"ficará sem registro em pedido_itens."
        )
        return

    url_pdf = produto['url_pdf']
    nome_arquivo = os.path.basename(url_pdf)
    db.execute_query(
        """INSERT INTO pedido_itens (pedido_id, tipo, nome, path_arquivo, nome_arquivo, valor)
           VALUES (%s, 'principal', %s, %s, %s, %s)""",
        (pedido_id, produto['nome'], url_pdf, nome_arquivo, valor_principal)
    )

    bonus_rows = listar_bonus_produto(produto['id'])
    if bonus_rows:
        db.execute_many(
            """INSERT INTO pedido_itens
                   (pedido_id, tipo, produto_bonus_id, nome, path_arquivo, nome_arquivo, valor)
               VALUES (%s, 'bonus', %s, %s, %s, %s, 0.00)""",
            [(pedido_id, bonus['id'], bonus['nome'], bonus['path_arquivo'], bonus['nome_arquivo'])
             for bonus in bonus_rows]
        )

    if bump_rows:
        db.execute_many(
            """INSERT INTO pedido_itens
                   (pedido_id, tipo, produto_bump_id, nome, path_arquivo, nome_arquivo, valor)
               VALUES (%s, 'bump', %s, %s, %s, %s, %s)""",
            [(pedido_id, bump['id'], bump['nome'], bump['path_arquivo'], bump['nome_arquivo'],
              bump['preco_promocional'])
             for bump in bump_rows]
        )


def buscar_todas_mensagens_pedido(pedido_id: int) -> list:
    """Retorna todas as mensagens de um pedido em ordem cronológica."""
    rows = db.execute_query(
        "SELECT tipo_mensagem, mensagem_json, sequencial_mensagem, data_mensagem "
        "FROM mensagens_pedidos WHERE pedido_id = %s ORDER BY sequencial_mensagem ASC",
        (pedido_id,), fetch_all=True
    )
    return rows if rows else []


def buscar_pedido_por_nome(contact_name: str, produto_id: int, canal_web: bool = None):
    """Busca o pedido mais recente de um cliente pelo nome (contact_name).
    canal_web=True restringe a pedidos web (estado_id>=1000), False a pedidos WhatsApp
    (estado_id<1000); None (padrão) não filtra por canal — usado em telas canal-agnósticas
    como Acertar Valor. Sem esse filtro na própria query, um cliente com pedido em ambos os
    canais podia ter o pedido do canal errado encontrado (o mais recente) e descartado por
    uma checagem posterior, mesmo havendo um pedido do canal certo mais antigo."""
    condicao_canal = ""
    if canal_web is True:
        condicao_canal = " AND estado_id >= 1000"
    elif canal_web is False:
        condicao_canal = " AND estado_id < 1000"
    return db.execute_query(
        f"SELECT * FROM pedidos WHERE contact_name LIKE %s AND produto_id = %s{condicao_canal} "
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
# Funções do fluxo Web Checkout Unificado (tabela pedidos)
# Usam estados 1001/1002/1003 para não conflitar com o fluxo WhatsApp (0-4).
# ============================================================

def get_produto_disponivel_web(produto_id: int):
    """Retorna produto de `produtos` habilitado para venda web ou None."""
    return db.execute_query(
        "SELECT * FROM produtos WHERE id = %s AND disponivel_web = TRUE AND ativo = TRUE",
        (produto_id,), fetch_one=True
    )


def busca_produtos_disponiveis_web():
    """Retorna lista de produtos visíveis no portfólio (disponivel_web=TRUE e url_pagina_vendas preenchida)."""
    return db.execute_query(
        """SELECT id, nome, preco, descricao, url_pagina_vendas, url_imagem_complementar
           FROM produtos
           WHERE disponivel_web = TRUE AND ativo = TRUE AND url_pagina_vendas IS NOT NULL AND preco IS NOT NULL
           ORDER BY id""",
        fetch_one=False
    ) or []


_whatsapp_token_cache: dict = {}  # api_phone_number_id -> token string resolvido


def get_whatsapp_token(api_phone_number_id: str) -> str:
    """Retorna o token WhatsApp correto para o phone_number_id dado, com cache em memória.
    Lança ValueError com mensagem clara se o número não estiver cadastrado ou o token não estiver no .env.
    """
    if not api_phone_number_id:
        token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')
        if not token:
            raise ValueError("[WHATSAPP-TOKEN] ❌ WHATSAPP_ACCESS_TOKEN não está configurado no .env")
        return token

    if api_phone_number_id not in _whatsapp_token_cache:
        row = db.execute_query(
            "SELECT token_env_key FROM telefones_produto WHERE api_phone_number_id = %s LIMIT 1",
            (api_phone_number_id,), fetch_one=True
        )
        if not row:
            raise ValueError(
                f"[WHATSAPP-TOKEN] ❌ phone_number_id '{api_phone_number_id}' não encontrado em telefones_produto. "
                f"Cadastre o número no admin (produto → Números WhatsApp) e preencha o campo API phone_number_id."
            )
        key = row.get('token_env_key') or 'WHATSAPP_ACCESS_TOKEN'
        token = os.getenv(key)
        if not token:
            raise ValueError(
                f"[WHATSAPP-TOKEN] ❌ Variável de ambiente '{key}' não está definida no .env. "
                f"Configure o token da conta WhatsApp associada ao número {api_phone_number_id}."
            )
        _whatsapp_token_cache[api_phone_number_id] = token

    return _whatsapp_token_cache[api_phone_number_id]


def phone_number_id_cadastrado(api_phone_number_id: str) -> bool:
    """Verifica se o phone_number_id está registrado em telefones_produto, sem resolver o token.
    Em caso de falha no banco, loga o erro e retorna False (fail-safe: bloqueia a mensagem).
    """
    if not api_phone_number_id:
        return False
    try:
        row = db.execute_query(
            "SELECT 1 FROM telefones_produto WHERE api_phone_number_id = %s LIMIT 1",
            (api_phone_number_id,), fetch_one=True
        )
        return row is not None
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(
            f"[WHATSAPP-TOKEN] ❌ Falha ao verificar phone_number_id '{api_phone_number_id}' no banco: {e}"
        )
        return False


def buscar_status_numero_empresa(api_phone_number_id: str):
    """Telefone e status_api do chip cadastrado em telefones_produto pelo api_phone_number_id.
    None se api_phone_number_id vazio ou não cadastrado (excluído da base)."""
    if not api_phone_number_id:
        return None
    query = """
        SELECT telefone, status_api
        FROM telefones_produto
        WHERE api_phone_number_id = %s
        LIMIT 1
    """
    return db.execute_query(query, (api_phone_number_id,), fetch_one=True)


def numero_empresa_operacional(api_phone_number_id: str) -> bool:
    """True se o chip ainda está cadastrado em telefones_produto e sem status de problema
    (mesmo critério do badge em numeros_whatsapp.html: status_api preenchido e != 'CONNECTED'
    bloqueia; status_api NULL — nunca checado — não bloqueia)."""
    info = buscar_status_numero_empresa(api_phone_number_id)
    if info is None:
        return False
    status = info.get('status_api')
    return not status or status == 'CONNECTED'


def get_phone_number_id_produto(produto_id: int):
    """Retorna o api_phone_number_id (ID da API Meta) associado ao produto ou None."""
    row = db.execute_query(
        "SELECT api_phone_number_id FROM telefones_produto WHERE produto_id = %s AND api_phone_number_id IS NOT NULL LIMIT 1",
        (produto_id,), fetch_one=True
    )
    return row['api_phone_number_id'] if row else None


def criar_pedido_web_inicial(produto_id: int, estado_id: int, dns_origem: str = '',
                             gclid: str = '', campaignid: str = '', adgroupid: str = '',
                             creative: str = '', matchtype: str = '',
                             device: str = '', placement: str = '',
                             video_id: str = '') -> int:
    """
    Cria um pedido em `pedidos` numa etapa anterior à identificação do cliente
    (estado_id 1004 = chegou na página de vendas, ou 1003 = chegou no checkout) — sem
    contact_phone/contact_name/email, só dados de campanha. Mesma ideia de `criar_pedido`
    (fluxo WhatsApp, que cria o pedido no clique do botão, antes de qualquer conversa).
    Retorna o id.
    """
    return db.execute_query(
        """INSERT INTO pedidos
             (produto_id, valor_pago, estado_id, gclid,
              data_ultima_atualizacao, data_contato_site,
              dns_origem, campaignid, adgroupid, creative, matchtype, device, placement, video_id)
           VALUES (%s, 0.0, %s, %s,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                   %s, %s, %s, %s, %s, %s, %s, %s)""",
        (produto_id, estado_id, gclid or '',
         dns_origem or '', campaignid or '', adgroupid or '', creative or '',
         matchtype or '', device or '', placement or '', video_id or '')
    )


def get_pedido_nao_finalizado(pedido_id: int, produto_id: int):
    """Retorna o pedido se ele ainda estiver numa etapa pré-identificação (1004 ou 1003),
    restrito ao produto informado — evita reaproveitar/atualizar pedido de outro produto ou
    um pedido que já foi finalizado (protege a troca de order bump após já ter finalizado:
    ver `finalizar_pedido_web`)."""
    return db.execute_query(
        "SELECT * FROM pedidos WHERE id = %s AND produto_id = %s AND estado_id IN (1004, 1003)",
        (pedido_id, produto_id), fetch_one=True
    )


def avancar_pedido_web(pedido_id: int, estado_id: int) -> None:
    """Avança um pedido ainda não finalizado (1004→1003) sem recriar a linha."""
    db.execute_query(
        """UPDATE pedidos SET estado_id = %s, data_ultima_atualizacao = CURRENT_TIMESTAMP
           WHERE id = %s AND estado_id IN (1004, 1003)""",
        (estado_id, pedido_id)
    )


def finalizar_pedido_web(pedido_id: int, phone_number_id: str, contact_phone: str,
                         contact_name: str, email: str) -> bool:
    """
    Preenche a identidade do cliente num pedido já existente (1004/1003) e avança pra 1001
    (Pedido web criado) — usado quando o cliente chegou na landing/checkout antes de finalizar.
    Só atualiza se o pedido ainda estiver em 1004/1003 (WHERE protege contra reaproveitar um
    pedido que já foi adiante, ex: cliente quer trocar de order bump depois de já ter gerado um
    PIX — nesse caso o caminho correto é criar um pedido novo via `criar_pedido_web_unificado`).
    Retorna True se atualizou alguma linha, False caso o pedido não estivesse mais em 1004/1003.
    """
    _contact_phone = contact_phone or ''
    linhas = db.execute_query(
        """UPDATE pedidos
           SET phone_number_id = %s, contact_phone = %s, contact_name = %s, contact_to = %s,
               email = %s, estado_id = 1001, data_pedido = CURRENT_TIMESTAMP,
               data_ultima_atualizacao = CURRENT_TIMESTAMP
           WHERE id = %s AND estado_id IN (1004, 1003)""",
        (phone_number_id or '', _contact_phone, contact_name or '', _contact_phone or None,
         email or '', pedido_id),
        return_rowcount=True
    )
    return bool(linhas)


def criar_pedido_web_unificado(produto_id: int, phone_number_id: str,
                               contact_phone: str, contact_name: str,
                               dns_origem: str = '',
                               email: str = '', gclid: str = '',
                               campaignid: str = '', adgroupid: str = '',
                               creative: str = '', matchtype: str = '',
                               device: str = '', placement: str = '',
                               video_id: str = '') -> int:
    """Cria pedido em `pedidos` com estado 1001 (Pedido web criado). Retorna o id."""
    _contact_phone = contact_phone or ''
    return db.execute_query(
        """INSERT INTO pedidos
             (produto_id, valor_pago, estado_id, gclid,
              data_ultima_atualizacao, data_contato_site, data_pedido,
              phone_number_id, contact_phone, contact_name, contact_to, email,
                dns_origem,
              campaignid, adgroupid, creative, matchtype, device, placement, video_id)
           VALUES (%s, 0.0, 1001, %s,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                   %s, %s, %s, %s, %s,
                    %s,
                   %s, %s, %s, %s, %s, %s, %s)""",
        (produto_id, gclid or '',
         phone_number_id or '', _contact_phone, contact_name or '', _contact_phone or None, email or '',
            dns_origem or '',
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


def confirmar_pagamento_web(pedido_id: int, valor: float, nome_pagador: str = '',
                            cpf_cnpj_pagador: str = '', valor_liquido: float = None,
                            data_repasse: str = None, e2e_id: str = '') -> bool:
    """
    Confirma pagamento web: avança para estado 1000 e registra dados do pagador.

    O `WHERE ... AND estado_id != 1000` torna a operação atômica (compare-and-swap): se duas
    chamadas concorrentes (ex: polling do cliente e o sweep de resiliência) tentarem confirmar
    o mesmo pedido ao mesmo tempo, só uma delas efetivamente atualiza a linha. Retorna True só
    para quem "ganhou" — quem chama deve usar isso pra decidir se dispara a entrega (evita
    e-mail duplicado).
    """
    linhas = db.execute_query(
        """UPDATE pedidos
           SET estado_id = 1000,
               valor_pago = %s,
               nome_pagador = %s,
               cpf_cnpj_pagador = %s,
               valor_liquido_pagamento = %s,
               data_repasse = %s,
               e2e_id = %s,
               data_pagamento = CURRENT_TIMESTAMP,
               data_ultima_atualizacao = CURRENT_TIMESTAMP
           WHERE id = %s AND estado_id != 1000""",
        (valor, nome_pagador or '', cpf_cnpj_pagador or '',
         valor_liquido, data_repasse, e2e_id or '', pedido_id),
        return_rowcount=True
    )
    return bool(linhas)


def marcar_ebook_enviado(pedido_id: int) -> None:
    """Registra o momento em que o ebook foi enviado via WhatsApp."""
    db.execute_query(
        """UPDATE pedidos
           SET data_envio_ebook = CURRENT_TIMESTAMP,
               data_ultima_atualizacao = CURRENT_TIMESTAMP
           WHERE id = %s""",
        (pedido_id,)
    )


# ── pagamento_pix ─────────────────────────────────────────────────────────────

def listar_chaves_pix_produto(produto_id) -> list:
    """Lista todas as chaves PIX de um produto (ativas e inativas)."""
    return db.execute_query(
        "SELECT id, chave_pix, ativo, criado_em FROM chaves_pix_produto WHERE produto_id = %s ORDER BY criado_em DESC",
        (produto_id,),
        fetch_all=True,
    ) or []


def adicionar_chave_pix_produto(produto_id, chave_pix: str) -> int:
    """Insere uma chave PIX para o produto. INSERT IGNORE evita duplicata."""
    return db.execute_query(
        "INSERT IGNORE INTO chaves_pix_produto (produto_id, chave_pix) VALUES (%s, %s)",
        (produto_id, chave_pix.strip()),
    )


def desativar_chave_pix_produto(chave_id: int):
    """Soft-delete: marca a chave como inativa (mantém histórico)."""
    db.execute_query(
        "UPDATE chaves_pix_produto SET ativo = 0 WHERE id = %s",
        (chave_id,),
    )


def busca_financeiro_pix(produto_id, data_ini, data_fim) -> dict:
    """
    Retorna resumo e lista de transações (PIX + vendas web confirmadas) do
    produto no período, com origem ('whatsapp' ou 'web') por transação.

    Pagamentos PIX já vinculados a um pedido web confirmado (mesmo e2e_id)
    são excluídos do lado PIX para não contar a mesma venda duas vezes —
    aparecem só como linha 'web'.

    Returns:
        dict com keys 'resumo' (total_valor, qtd_transacoes, ticket_medio)
                   e 'transacoes' (lista unificada, ordenada por horario DESC)
    """
    transacoes = db.execute_query(
        """SELECT pp.horario, pp.valor, pp.chave_pix, pp.cpf_cnpj, pp.nome_pagador,
                  pp.txid, pp.e2e_id,
                  pp.nfe_emitida_id,
                  ne.c_stat       AS nfe_c_stat,
                  ne.chave_acesso AS nfe_chave_acesso,
                  'whatsapp'      AS origem
           FROM pagamento_pix pp
           LEFT JOIN nfe_emitidas ne ON ne.id = pp.nfe_emitida_id
           WHERE pp.produto_id = %s AND pp.horario BETWEEN %s AND %s
             AND NOT EXISTS (
                 SELECT 1 FROM pedidos ped
                 WHERE ped.estado_id = 1000
                   AND ped.e2e_id = pp.e2e_id
                   AND ped.e2e_id != ''
             )

           UNION ALL

           SELECT ped.data_pagamento AS horario, ped.valor_pago AS valor,
                  NULL AS chave_pix,
                  REPLACE(REPLACE(REPLACE(ped.cpf_cnpj_pagador, '.', ''), '-', ''), '/', '') AS cpf_cnpj,
                  ped.nome_pagador,
                  NULL AS txid, ped.e2e_id,
                  NULL AS nfe_emitida_id,
                  NULL AS nfe_c_stat,
                  NULL AS nfe_chave_acesso,
                  'web' AS origem
           FROM pedidos ped
           WHERE ped.produto_id = %s AND ped.estado_id = 1000
             AND ped.data_pagamento BETWEEN %s AND %s

           ORDER BY horario DESC""",
        (produto_id, data_ini, data_fim, produto_id, data_ini, data_fim),
        fetch_all=True,
    ) or []

    total = float(sum(t['valor'] for t in transacoes))
    qtd   = len(transacoes)
    return {
        'resumo': {
            'total_valor':     total,
            'qtd_transacoes':  qtd,
            'ticket_medio':    round(total / qtd, 2) if qtd > 0 else 0.0,
        },
        'transacoes': transacoes,
    }


def busca_chaves_pix_produtos() -> dict:
    """
    Retorna dict {chave_pix: produto_id} com todas as chaves PIX ativas.
    Um produto pode ter múltiplas chaves (tabela chaves_pix_produto).
    """
    rows = db.execute_query(
        "SELECT chave_pix, produto_id FROM chaves_pix_produto WHERE ativo = 1",
        fetch_all=True,
    )
    return {row['chave_pix']: row['produto_id'] for row in (rows or [])}


def salvar_pagamento_pix(pix: dict, produto_id, tenant_slug: str = 'lsn-livros') -> bool:
    """
    Persiste uma transação PIX recebida, marcando de qual conta BB (tenant) veio.
    Usa INSERT IGNORE para evitar duplicatas (unicidade garantida por e2e_id).

    Retorna True se inseriu (novo), False se já existia.
    """
    from datetime import datetime

    # Horário vem como ISO 8601 com offset, ex: "2026-03-31T06:59:38.00-03:00"
    horario_str = pix.get('horario', '')
    try:
        horario = datetime.fromisoformat(horario_str).replace(tzinfo=None)
    except (ValueError, TypeError):
        horario = None

    pagador  = pix.get('pagador') or {}
    cpf_cnpj = pagador.get('cpf') or pagador.get('cnpj') or None
    txid     = pix.get('txid') or None

    with db.get_cursor() as cursor:
        cursor.execute(
            """INSERT IGNORE INTO pagamento_pix
               (e2e_id, produto_id, chave_pix, tenant_slug, valor, horario, cpf_cnpj, nome_pagador, txid)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                pix.get('endToEndId'),
                produto_id,
                pix.get('chave', ''),
                tenant_slug,
                float(pix.get('valor', 0)),
                horario,
                cpf_cnpj,
                pagador.get('nome'),
                txid,
            ),
        )
        return cursor.lastrowid if cursor.rowcount > 0 else None


# ============================================================
# Notificações de pedido (substitui WhatsApp ao admin)
# ============================================================

def criar_notificacao_pedido(pedido_id: int, produto_id: int, motivo: str, mensagem: str = '') -> bool:
    """Cria notificação se não houver uma em_analise para o pedido. Retorna True se inseriu.
    Ignora notificações com motivo='sugestao_resposta_email' na checagem de duplicidade — um
    rascunho de e-mail aguardando aprovação não é um alerta que deva bloquear uma escalação
    (WhatsApp ou e-mail) nova para o mesmo pedido."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO notificacoes_pedido (pedido_id, produto_id, motivo, mensagem)
               SELECT %s, %s, %s, %s
               WHERE NOT EXISTS (
                   SELECT 1 FROM notificacoes_pedido
                   WHERE pedido_id = %s AND estado = 'em_analise' AND motivo != 'sugestao_resposta_email'
               )""",
            (pedido_id, produto_id, motivo, mensagem, pedido_id),
        )
        return cursor.rowcount > 0


def tem_notificacao_em_analise(pedido_id: int) -> bool:
    """Retorna True se houver notificação em_analise (que exige atenção humana) para o pedido.
    Exclui sugestao_resposta_email — um rascunho de e-mail aguardando aprovação não deve
    silenciar o agente (WhatsApp ou escalonamento de e-mail) para esse pedido."""
    row = db.execute_query(
        "SELECT 1 FROM notificacoes_pedido WHERE pedido_id = %s AND estado = 'em_analise' "
        "AND motivo != 'sugestao_resposta_email' LIMIT 1",
        (pedido_id,),
        fetch_one=True,
    )
    return row is not None


def contar_notificacoes_em_analise(produto_id: int, motivo: str = None) -> int:
    """Retorna quantidade de notificações em_analise para o produto (usado no badge).
    Por padrão exclui sugestões de resposta de e-mail — badge próprio, ver
    contar_notificacoes_em_analise(produto_id, motivo='sugestao_resposta_email')."""
    if motivo:
        condicao_motivo, params = "AND motivo = %s", (produto_id, motivo)
    else:
        condicao_motivo, params = "AND motivo != 'sugestao_resposta_email'", (produto_id,)
    row = db.execute_query(
        f"SELECT COUNT(*) AS total FROM notificacoes_pedido WHERE produto_id = %s AND estado = 'em_analise' {condicao_motivo}",
        params,
        fetch_one=True,
    )
    return int(row['total']) if row else 0


def listar_notificacoes_em_analise(produto_id: int, motivo: str = None) -> list:
    """Lista notificações em_analise do produto, mais antigas primeiro, com dados do pedido.
    Por padrão exclui sugestões de resposta de e-mail (têm tela própria — ver
    notificacoes_web_produto); passe motivo='sugestao_resposta_email' para listar só essas."""
    if motivo:
        condicao_motivo, params = "AND n.motivo = %s", (produto_id, motivo)
    else:
        condicao_motivo, params = "AND n.motivo != 'sugestao_resposta_email'", (produto_id,)
    return db.execute_query(
        f"""SELECT n.id, n.pedido_id, n.motivo, n.mensagem, n.created_at,
                  p.contact_name, p.contact_phone, p.email
           FROM notificacoes_pedido n
           JOIN pedidos p ON p.id = n.pedido_id
           WHERE n.produto_id = %s AND n.estado = 'em_analise' {condicao_motivo}
           ORDER BY n.created_at ASC""",
        params,
        fetch_all=True,
    ) or []


def marcar_notificacao_respondida(notificacao_id: int, produto_id: int) -> None:
    """Marca a notificação como respondida, garantindo que pertence ao produto."""
    db.execute_query(
        "UPDATE notificacoes_pedido SET estado = 'respondido' WHERE id = %s AND produto_id = %s",
        (notificacao_id, produto_id),
    )


def buscar_notificacao_por_id(notificacao_id: int, produto_id: int):
    """Pedido_id e motivo da notificação — usado pra decidir de volta pra onde redirecionar
    depois de marcar como respondida (tela de notificações do WhatsApp vs conversa de e-mail)."""
    return db.execute_query(
        "SELECT id, pedido_id, motivo FROM notificacoes_pedido WHERE id = %s AND produto_id = %s",
        (notificacao_id, produto_id), fetch_one=True,
    )


def buscar_notificacao_em_analise_pedido(pedido_id: int):
    """Retorna a notificação em_analise ativa do pedido (exclui sugestao_resposta_email — tem
    banner/tela própria, ver buscar_notificacao_email_pedido), ou None."""
    return db.execute_query(
        "SELECT id FROM notificacoes_pedido WHERE pedido_id = %s AND estado = 'em_analise' "
        "AND motivo != 'sugestao_resposta_email' LIMIT 1",
        (pedido_id,), fetch_one=True
    )


def bloquear_pedido(pedido_id: int) -> None:
    """Marca pedido como bloqueado (WhatsApp) e resolve notificações em_analise do WhatsApp
    (atômico) — não mexe numa sugestão de e-mail pendente, que é de outro canal e o admin ainda
    não viu."""
    with db.get_cursor() as cursor:
        cursor.execute("UPDATE pedidos SET bloqueado = 1 WHERE id = %s", (pedido_id,))
        cursor.execute(
            "UPDATE notificacoes_pedido SET estado = 'respondido' "
            "WHERE pedido_id = %s AND estado = 'em_analise' AND motivo != 'sugestao_resposta_email'",
            (pedido_id,),
        )


def criar_sugestao_resposta_email(pedido_id: int, produto_id: int, mensagem: str) -> bool:
    """Cria notificação de sugestão de resposta de e-mail. Dedupe restrito ao próprio motivo
    (diferente de criar_notificacao_pedido, que dedupe por QUALQUER notificação em_analise do
    pedido) — um pedido web pode ter uma notificação do WhatsApp aberta e ainda assim precisa
    da sugestão de e-mail visível, senão o rascunho da IA seria descartado silenciosamente."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """INSERT INTO notificacoes_pedido (pedido_id, produto_id, motivo, mensagem)
               SELECT %s, %s, 'sugestao_resposta_email', %s
               WHERE NOT EXISTS (
                   SELECT 1 FROM notificacoes_pedido
                   WHERE pedido_id = %s AND estado = 'em_analise' AND motivo = 'sugestao_resposta_email'
               )""",
            (pedido_id, produto_id, mensagem, pedido_id),
        )
        return cursor.rowcount > 0


def buscar_notificacao_email_pedido(pedido_id: int):
    """Retorna a notificação de sugestão de resposta de e-mail em_analise do pedido, ou None."""
    return db.execute_query(
        "SELECT id, mensagem FROM notificacoes_pedido "
        "WHERE pedido_id = %s AND estado = 'em_analise' AND motivo = 'sugestao_resposta_email' LIMIT 1",
        (pedido_id,), fetch_one=True,
    )


def bloquear_pedido_email(pedido_id: int) -> None:
    """Marca pedido como email_bloqueado e resolve notificações de sugestão de e-mail em_analise
    (atômico). Independente de pedidos.bloqueado — não mexe nas notificações do WhatsApp."""
    with db.get_cursor() as cursor:
        cursor.execute("UPDATE pedidos SET email_bloqueado = 1 WHERE id = %s", (pedido_id,))
        cursor.execute(
            "UPDATE notificacoes_pedido SET estado = 'respondido' "
            "WHERE pedido_id = %s AND estado = 'em_analise' AND motivo = 'sugestao_resposta_email'",
            (pedido_id,),
        )


# ============================================================
# Conversas por e-mail (pedidos web 1000-1004)
# ============================================================

def definir_gmail_thread_pedido(pedido_id: int, thread_id: str) -> None:
    """Ancora o pedido à thread do Gmail — usado tanto no envio da entrega quanto no fallback
    por assunto durante o polling, para as próximas mensagens da mesma thread baterem direto."""
    db.execute_query(
        "UPDATE pedidos SET gmail_thread_id = %s WHERE id = %s",
        (thread_id, pedido_id),
    )


def resolver_pedido_por_thread_gmail(thread_id: str):
    """Busca o pedido dono de uma thread do Gmail (match direto, caminho preferencial do polling)."""
    return db.execute_query(
        "SELECT * FROM pedidos WHERE gmail_thread_id = %s LIMIT 1",
        (thread_id,), fetch_one=True,
    )


def salvar_mensagem_email_pedido(pedido_id: int, direcao: str, gmail_message_id: str,
                                  gmail_thread_id: str, assunto: str, remetente: str,
                                  destinatario: str, corpo_texto: str, corpo_html: str,
                                  data_mensagem, rfc_message_id: str = None) -> int | None:
    """Persiste uma mensagem de e-mail do pedido. Retorna o id inserido, ou None se
    gmail_message_id já existir — dedupe/idempotência do polling (roda a cada 10min e pode
    revisitar a mesma mensagem). rfc_message_id (header Message-ID) é o que ancora o threading
    da próxima resposta — ver buscar_ultima_mensagem_email_pedido."""
    try:
        return db.execute_query(
            """INSERT INTO mensagens_email_pedido
               (pedido_id, direcao, gmail_message_id, gmail_thread_id, rfc_message_id, assunto,
                remetente, destinatario, corpo_texto, corpo_html, data_mensagem)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (pedido_id, direcao, gmail_message_id, gmail_thread_id, rfc_message_id, assunto,
             remetente, destinatario, corpo_texto, corpo_html, data_mensagem),
        )
    except IntegrityError as e:
        if e.errno == 1062:
            logger.info(f"[EMAIL] Mensagem {gmail_message_id} já persistida — ignorando duplicata")
            return None
        raise


def buscar_mensagens_email_pedido(pedido_id: int) -> list:
    """Timeline de mensagens de e-mail do pedido, mais antiga primeiro."""
    return db.execute_query(
        "SELECT * FROM mensagens_email_pedido WHERE pedido_id = %s ORDER BY data_mensagem ASC",
        (pedido_id,), fetch_all=True,
    ) or []


def buscar_ultima_mensagem_email_pedido(pedido_id: int):
    """Última mensagem de e-mail (qualquer direção) do pedido — usada pra threading da próxima
    resposta: rfc_message_id vira In-Reply-To/References, assunto vira base do 'Re: ...'."""
    return db.execute_query(
        "SELECT assunto, rfc_message_id FROM mensagens_email_pedido "
        "WHERE pedido_id = %s ORDER BY data_mensagem DESC LIMIT 1",
        (pedido_id,), fetch_one=True,
    )


def buscar_historico_email_conversa(pedido_id: int, limite: int = 10) -> list:
    """Últimas mensagens de e-mail do pedido formatadas para a OpenAI (mesmo formato de
    buscar_historico_conversa, usado no WhatsApp). Respostas do admin (direcao='enviada') só têm
    corpo_html — nesse caso extrai o texto das tags pra não perder o histórico do que já foi
    dito ao cliente."""
    import re as _re
    query = """
        SELECT direcao, corpo_texto, corpo_html
        FROM mensagens_email_pedido
        WHERE pedido_id = %s
        ORDER BY data_mensagem DESC
        LIMIT %s
    """
    mensagens = db.execute_query(query, (pedido_id, limite), fetch_all=True)
    if not mensagens:
        return []
    mensagens = list(reversed(mensagens))
    resultado = []
    for msg in mensagens:
        conteudo = msg['corpo_texto']
        if not conteudo and msg.get('corpo_html'):
            conteudo = _re.sub('<[^>]+>', ' ', msg['corpo_html'])
        resultado.append({
            "role": "assistant" if msg['direcao'] == 'enviada' else "user",
            "content": (conteudo or '').strip(),
        })
    return resultado


def salvar_anexo_email_mensagem(mensagem_id: int, nome_arquivo: str, caminho_arquivo: str,
                                 mime_type: str, tamanho_bytes: int) -> int:
    return db.execute_query(
        """INSERT INTO mensagens_email_pedido_anexos
           (mensagem_id, nome_arquivo, caminho_arquivo, mime_type, tamanho_bytes)
           VALUES (%s, %s, %s, %s, %s)""",
        (mensagem_id, nome_arquivo, caminho_arquivo, mime_type, tamanho_bytes),
    )


def buscar_anexos_email_pedido(pedido_id: int) -> list:
    """Todos os anexos de todas as mensagens de e-mail do pedido (agrupar por mensagem_id no
    template/view)."""
    return db.execute_query(
        """SELECT a.* FROM mensagens_email_pedido_anexos a
           JOIN mensagens_email_pedido m ON m.id = a.mensagem_id
           WHERE m.pedido_id = %s""",
        (pedido_id,), fetch_all=True,
    ) or []


def buscar_anexo_email_por_id(anexo_id: int):
    """Anexo de e-mail + pedido_id da mensagem dona (para checagem de acesso na view)."""
    return db.execute_query(
        """SELECT a.*, m.pedido_id FROM mensagens_email_pedido_anexos a
           JOIN mensagens_email_pedido m ON m.id = a.mensagem_id
           WHERE a.id = %s""",
        (anexo_id,), fetch_one=True,
    )


def buscar_pedido_web_por_email(termo: str, produto_id: int):
    """Pedido web (estado_id 1000-1004) mais recente cujo e-mail bate com o termo — equivalente
    web de get_ultimo_pedido_by_phone (WhatsApp), usado na busca da tela "Conversas Web"."""
    if not termo:
        return None
    return db.execute_query(
        """SELECT * FROM pedidos
           WHERE produto_id = %s AND estado_id IN (1000, 1001, 1002, 1003, 1004)
             AND email LIKE %s
           ORDER BY data_pedido DESC LIMIT 1""",
        (produto_id, f'%{termo}%'), fetch_one=True,
    )


# ─── NF-e ────────────────────────────────────────────────────────────────────

def buscar_nfe_configuracao_ativa() -> dict | None:
    """Retorna a configuração NF-e ativa (primeiro registro ativo)."""
    return db.execute_query(
        "SELECT * FROM nfe_configuracao WHERE ativo = 1 LIMIT 1",
        fetch_one=True,
    )


def buscar_nfe_configuracao_por_slug(slug: str) -> dict | None:
    """Retorna a configuração NF-e de um tenant específico pelo slug."""
    return db.execute_query(
        "SELECT * FROM nfe_configuracao WHERE tenant_slug = %s AND ativo = 1",
        (slug,),
        fetch_one=True,
    )


def buscar_tenant_slug_produto(produto_id: int) -> str:
    """
    Retorna o tenant_slug (conta BB Pix) associado ao produto, via
    produtos.nfe_config_id -> nfe_configuracao.tenant_slug.
    Produtos sem nfe_config_id (NULL) usam a conta default 'lsn-livros'.
    """
    row = db.execute_query(
        """SELECT nc.tenant_slug
           FROM produtos p
           LEFT JOIN nfe_configuracao nc ON nc.id = p.nfe_config_id
           WHERE p.id = %s""",
        (produto_id,), fetch_one=True,
    )
    return (row or {}).get('tenant_slug') or 'lsn-livros'


def buscar_pagamento_pix_por_id(pagamento_pix_id: int) -> dict | None:
    return db.execute_query(
        """SELECT pp.*, p.nome AS x_prod
           FROM pagamento_pix pp
           LEFT JOIN produtos p ON p.id = pp.produto_id
           WHERE pp.id = %s""",
        (pagamento_pix_id,), fetch_one=True,
    )


def incrementar_numero_nfe(config_id: int) -> int:
    """Incrementa e retorna o próximo número de NF-e com lock de linha."""
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT ultimo_numero_nfe FROM nfe_configuracao WHERE id = %s FOR UPDATE",
            (config_id,),
        )
        row = cursor.fetchone()
        novo = row['ultimo_numero_nfe'] + 1
        cursor.execute(
            "UPDATE nfe_configuracao SET ultimo_numero_nfe = %s WHERE id = %s",
            (novo, config_id),
        )
    return novo


def criar_nfe_pendente(
    tenant_id: int,
    pagamento_pix_id: int,
    chave_acesso: str,
    numero: str,
    serie: str,
    ambiente: int,
    xml_assinado: str,
) -> int:
    """INSERT em nfe_emitidas com status=enviando. Retorna o id gerado."""
    return db.execute_query(
        """INSERT INTO nfe_emitidas
           (tenant_id, pagamento_pix_id, chave_acesso, numero, serie, ambiente,
            xml_assinado, status_emissao, tentativas)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'enviando', 1)""",
        (tenant_id, pagamento_pix_id, chave_acesso, numero, serie, ambiente, xml_assinado),
    )


def vincular_nfe_ao_pagamento_pix(pagamento_pix_id: int, nfe_id: int) -> None:
    db.execute_query(
        "UPDATE pagamento_pix SET nfe_emitida_id = %s WHERE id = %s",
        (nfe_id, pagamento_pix_id),
    )


def atualizar_nfe_autorizada(
    nfe_id: int,
    c_stat: str,
    x_motivo: str,
    n_prot: str,
    dh_recbto: str,
    xml_nfe_proc: str,
) -> None:
    db.execute_query(
        """UPDATE nfe_emitidas
           SET c_stat=%s, x_motivo=%s, n_prot=%s, dh_recbto=%s,
               xml_nfe_proc=%s, status_emissao='autorizada', ultimo_erro=NULL
           WHERE id=%s""",
        (c_stat, x_motivo, n_prot, dh_recbto, xml_nfe_proc, nfe_id),
    )


def atualizar_nfe_rejeitada(nfe_id: int, c_stat: str, x_motivo: str) -> None:
    db.execute_query(
        """UPDATE nfe_emitidas
           SET c_stat=%s, x_motivo=%s, status_emissao='rejeitada'
           WHERE id=%s""",
        (c_stat, x_motivo, nfe_id),
    )


def atualizar_nfe_aguardando_retorno(nfe_id: int, n_rec: str) -> None:
    """Salva nRec para consulta assíncrona posterior."""
    db.execute_query(
        "UPDATE nfe_emitidas SET n_rec=%s, status_emissao='aguardando_retorno' WHERE id=%s",
        (n_rec, nfe_id),
    )


def atualizar_nfe_erro(nfe_id: int, erro_msg: str) -> None:
    db.execute_query(
        """UPDATE nfe_emitidas
           SET status_emissao='erro', ultimo_erro=%s, tentativas=tentativas+1
           WHERE id=%s""",
        (erro_msg[:2000], nfe_id),
    )


def gravar_log_soap(
    nfe_id: int,
    operacao: str,
    url: str,
    soap_request: str,
    soap_response: str,
    status_http: int,
    duracao_ms: float,
) -> None:
    db.execute_query(
        """INSERT INTO nfe_log_comunicacao
           (nfe_id, operacao, url, soap_request, soap_response, status_http, duracao_ms)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (nfe_id, operacao, url, soap_request, soap_response, status_http, int(duracao_ms)),
    )


def buscar_pagamentos_pix_sem_nfe(
    limite: int = 500,
    dias_atras: int = 1,
    config_id: int | None = None,
) -> list[int]:
    """
    IDs de pagamento_pix dos últimos N dias sem NF-e autorizada.
    Inclui: sem tentativa alguma (ne.id IS NULL) ou com tentativa em erro (para retry).
    Exclui: rejeitadas (precisam de intervenção humana) e enviando (em progresso).
    config_id filtra pelo tenant via produtos.nfe_config_id (evita emitir NF-e com CNPJ errado).
    """
    sql = """SELECT pp.id
             FROM pagamento_pix pp
             LEFT JOIN produtos p ON p.id = pp.produto_id
             LEFT JOIN nfe_emitidas ne ON ne.pagamento_pix_id = pp.id
             WHERE pp.nfe_emitida_id IS NULL
               AND (ne.id IS NULL OR ne.status_emissao = 'erro')
               AND pp.horario >= NOW() - INTERVAL %s DAY"""
    params: list = [dias_atras]
    if config_id is not None:
        sql += " AND p.nfe_config_id = %s"
        params.append(config_id)
    sql += " ORDER BY pp.id ASC LIMIT %s"
    params.append(limite)
    rows = db.execute_query(sql, params, fetch_all=True)
    return [r['id'] for r in rows] if rows else []
