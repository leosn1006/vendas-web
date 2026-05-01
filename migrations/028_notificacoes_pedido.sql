-- Notificações de pedido para o admin (substitui WhatsApp ao admin)
-- Quando a IA escalaria um atendimento, cria uma notificação aqui.
-- Enquanto em_analise, a IA silencia para aquele pedido.
CREATE TABLE IF NOT EXISTS notificacoes_pedido (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id  INT NOT NULL,
    produto_id INT NOT NULL,
    motivo     VARCHAR(100) NOT NULL,
    mensagem   TEXT,
    estado     ENUM('em_analise','respondido') NOT NULL DEFAULT 'em_analise',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (pedido_id)  REFERENCES pedidos(id),
    FOREIGN KEY (produto_id) REFERENCES produtos(id),
    INDEX idx_pedido_estado  (pedido_id, estado),
    INDEX idx_produto_estado (produto_id, estado, created_at)
);
