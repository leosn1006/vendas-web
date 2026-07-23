-- Notificações de nível-número recebidas via webhook do WhatsApp (hoje descartadas).
-- Cobre phone_number_quality_update e phone_number_name_update.
CREATE TABLE IF NOT EXISTS notificacoes_telefone (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    telefone_id INT NOT NULL,
    produto_id  INT NOT NULL,
    tipo_evento VARCHAR(50)  NOT NULL,   -- 'phone_number_quality_update' | 'phone_number_name_update'
    mensagem    TEXT NOT NULL,           -- resumo legível, ex: "Qualidade mudou de GREEN para RED"
    payload_raw JSON NULL,               -- corpo bruto do webhook (changes[i]), para investigação futura
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telefone_id) REFERENCES telefones_produto(id) ON DELETE CASCADE,
    FOREIGN KEY (produto_id)  REFERENCES produtos(id),
    INDEX idx_telefone_created (telefone_id, created_at),
    INDEX idx_produto_created  (produto_id, created_at)
);
