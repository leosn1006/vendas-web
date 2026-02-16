-- Script de criação do banco de dados MySQL
-- Encoding: UTF-8

USE vendasdb;

-- Tabela de produtos
CREATE TABLE IF NOT EXISTS produtos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL UNIQUE,
    preco DECIMAL(10, 2) NOT NULL,
    descricao TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Índice adicional na tabela produtos
CREATE INDEX idx_produtos_ativo ON produtos(ativo);

-- Inserir produtos iniciais
INSERT IGNORE INTO produtos (nome, preco, descricao)
VALUES ('ebook celiaco', 10.00, 'E-book com receitas para celíacos');

-- Tabela de estados de pedidos
CREATE TABLE IF NOT EXISTS estado_pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    descricao VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Inserir estados de pedidos
INSERT IGNORE INTO estado_pedidos (id, descricao) VALUES
(1, 'Iniciado'),
(2, 'Enviado primeira mensagem'),
(3, 'Respondido com interesse'),
(4, 'Respondido sem interesse'),
(5, 'Enviado produto'),
(6, 'Enviado mensagem de contribuição'),
(7, 'Respondido com comprovante de pagamento'),
(8, 'Conferido comprovante de pagamento'),
(0, 'Pago');

-- Tabela de pedidos
CREATE TABLE IF NOT EXISTS pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    produto_id INT NOT NULL,
    valor_pago DECIMAL(6, 2) NOT NULL,
    estado_id INT NOT NULL DEFAULT 1,
    gclid VARCHAR(255),
    data_ultima_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    mensagem_sugerida varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    emoji_sugerida VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    data_contato_site TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    phone_number_id VARCHAR(20),
    contact_phone VARCHAR(20),
    contact_name VARCHAR(255),
    data_pedido TIMESTAMP,
    campaignid VARCHAR(255),
    adgroupid VARCHAR(255),
    creative VARCHAR(255),
    matchtype VARCHAR(255),
    device VARCHAR(255),
    placement VARCHAR(255),
    video_id VARCHAR(255),
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE RESTRICT,
    FOREIGN KEY (estado_id) REFERENCES estado_pedidos(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Índices na tabela pedidos
CREATE INDEX idx_pedidos_data_estado ON pedidos(data_pedido, estado_id);
CREATE INDEX idx_pedidos_contact ON pedidos(contact_name, data_pedido);
CREATE INDEX idx_pedidos_phone ON pedidos(contact_phone);

-- Tabela de mensagens dos pedidos
CREATE TABLE IF NOT EXISTS mensagens_pedidos (
    pedido_id INT NOT NULL,
    sequencial_mensagem INT AUTO_INCREMENT,
    id VARCHAR(100) NOT NULL,
    data_mensagem TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mensagem_json TEXT NOT NULL,
    tipo_mensagem ENUM('recebida', 'enviada') DEFAULT 'recebida',
    PRIMARY KEY (pedido_id, sequencial_mensagem),
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Índice na tabela mensagens_pedidos
CREATE INDEX idx_mensagens_pedido ON mensagens_pedidos(pedido_id, data_mensagem);
