-- Migration 054: Histórico de mensagens de e-mail por pedido
-- Análoga a mensagens_pedidos (WhatsApp), mas sem sequencial_mensagem/janela 24h — conceitos
-- exclusivos da API do WhatsApp que não existem em e-mail. gmail_message_id único garante
-- idempotência do polling (não reprocessa a mesma mensagem em rodadas seguintes).
-- rfc_message_id guarda o header Message-ID (RFC 2822) — é o que vira In-Reply-To/References
-- na próxima resposta, o mecanismo real de threading de e-mail (threadId do Gmail sozinho não
-- basta se o assunto não bater exatamente).

CREATE TABLE IF NOT EXISTS mensagens_email_pedido (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id         INT NOT NULL,
    direcao           ENUM('recebida','enviada') NOT NULL,
    gmail_message_id  VARCHAR(255) NOT NULL UNIQUE,
    gmail_thread_id   VARCHAR(255) NOT NULL,
    rfc_message_id    VARCHAR(255) NULL,
    assunto           VARCHAR(500),
    remetente         VARCHAR(255),
    destinatario      VARCHAR(255),
    corpo_texto       TEXT,
    corpo_html        LONGTEXT,
    data_mensagem     TIMESTAMP NOT NULL,
    criado_em         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_pedido (pedido_id, data_mensagem),
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
);
