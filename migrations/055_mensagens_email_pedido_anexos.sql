-- Migration 055: Anexos de mensagens de e-mail
-- Aceita qualquer tipo de arquivo recebido do cliente (decisão de produto) — servidos sempre
-- como download forçado pelo admin, nunca executados/pré-visualizados no servidor.

CREATE TABLE IF NOT EXISTS mensagens_email_pedido_anexos (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    mensagem_id     INT NOT NULL,
    nome_arquivo    VARCHAR(255) NOT NULL,
    caminho_arquivo VARCHAR(500) NOT NULL,
    mime_type       VARCHAR(150),
    tamanho_bytes   INT,
    FOREIGN KEY (mensagem_id) REFERENCES mensagens_email_pedido(id) ON DELETE CASCADE
);
