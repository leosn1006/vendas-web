-- Migration 053: vincula pagamento_pix ao pedido web correspondente.
-- pedido_id NULL = PIX orgânico/WhatsApp (sem pedido web associado)
-- pedido_id NOT NULL = PIX do QR estático do checkout web (inclui duplicatas rastreáveis)

ALTER TABLE pagamento_pix ADD COLUMN pedido_id INT NULL AFTER produto_id;
ALTER TABLE pagamento_pix ADD CONSTRAINT fk_pagamento_pix_pedido
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id);
ALTER TABLE pagamento_pix ADD INDEX idx_pix_pedido (pedido_id);
