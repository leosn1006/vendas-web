-- ============================================================
-- Migration 029: Adiciona telefone e unicidade na tabela usuarios
-- Permite associar o número WhatsApp de teste ao usuário
-- e garante isolamento por usuário na exclusão de pedidos
-- ============================================================

ALTER TABLE usuarios
    ADD COLUMN telefone VARCHAR(50) NULL DEFAULT NULL
        COMMENT 'Número WhatsApp do usuário (ex: 556181163324), usado para excluir pedidos de teste',
    ADD CONSTRAINT uk_usuarios_telefone UNIQUE (telefone);
