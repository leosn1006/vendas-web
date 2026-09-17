-- Migration 075: vínculo explícito entre pedidos do mesmo cliente, pro cross-sell da estante v2.
--
-- O checkout v2 pré-preenche nome/e-mail/whatsapp mas deixa editável de propósito — se o
-- cliente edita e-mail ou telefone no meio do cross-sell, a busca por "pedidos relacionados"
-- (listar_pedidos_pagos_relacionados, só por e-mail/telefone batendo) deixa de encontrar o
-- vínculo, e a estante do pedido antigo para de mostrar o produto novo comprado.
--
-- pedidos_vinculados grava o vínculo no momento em que ele é conhecido de verdade — o clique
-- em "Comprar" a partir de uma estante específica (?ref=<guid>) — sem depender do que o
-- cliente digitar depois no formulário. Soma ao heurístico de e-mail/telefone existente, não
-- substitui: a maioria das compras (funil orgânico, WhatsApp) nunca passa por um ref conhecido.
--
-- Por pedido, não por produto: o vínculo é sempre de uma pessoa específica, não uma regra
-- geral entre dois produtos (ver plano peaceful-seeking-pizza.md, seção "Adendo").
CREATE TABLE pedidos_vinculados (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id_origem    INT NOT NULL,
    pedido_id_adquirido INT NOT NULL,
    criado_em           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pedidos_vinculados_origem    FOREIGN KEY (pedido_id_origem)    REFERENCES pedidos(id),
    CONSTRAINT fk_pedidos_vinculados_adquirido FOREIGN KEY (pedido_id_adquirido) REFERENCES pedidos(id),
    UNIQUE KEY uk_pedidos_vinculados (pedido_id_origem, pedido_id_adquirido)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_pedidos_vinculados_adquirido ON pedidos_vinculados(pedido_id_adquirido);
