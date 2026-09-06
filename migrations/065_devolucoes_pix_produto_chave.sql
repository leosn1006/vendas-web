-- Migration 065: denormaliza produto_id e chave_pix em devolucoes_pix.
--
-- Antes, o financeiro só conseguia atribuir uma devolução a um produto via JOIN
-- com pagamento_pix — se o PIX original não tivesse sido persistido ainda (ou
-- sua chave_pix não estivesse mapeada em chaves_pix_produto no momento em que
-- foi recebido), a devolução ficava invisível pra sempre em qualquer tela por
-- produto, mesmo sendo dinheiro real já devolvido. Agora produto_id é resolvido
-- também por fallback via chaves_pix_produto (mesma lógica já usada pro PIX
-- normal em fluxo_pix_bb.py), usando a própria chave que vem no payload da
-- devolução — não depende mais só do pagamento_pix já existir.

SET @col_produto = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'devolucoes_pix'
      AND COLUMN_NAME  = 'produto_id'
);
SET @sql_produto = IF(@col_produto = 0,
    'ALTER TABLE devolucoes_pix ADD COLUMN produto_id INT NULL AFTER pagamento_pix_id',
    'SELECT ''produto_id ja existe, pulando ALTER''' );
PREPARE stmt1 FROM @sql_produto;
EXECUTE stmt1;
DEALLOCATE PREPARE stmt1;

SET @col_chave = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'devolucoes_pix'
      AND COLUMN_NAME  = 'chave_pix'
);
SET @sql_chave = IF(@col_chave = 0,
    'ALTER TABLE devolucoes_pix ADD COLUMN chave_pix VARCHAR(77) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL AFTER e2e_id',
    'SELECT ''chave_pix ja existe, pulando ALTER''' );
PREPARE stmt2 FROM @sql_chave;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

SET @idx_produto = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'devolucoes_pix'
      AND INDEX_NAME   = 'idx_devol_produto'
);
SET @sql_idx = IF(@idx_produto = 0,
    'ALTER TABLE devolucoes_pix ADD INDEX idx_devol_produto (produto_id, horario_liquidacao)',
    'SELECT ''idx_devol_produto ja existe, pulando ALTER''' );
PREPARE stmt3 FROM @sql_idx;
EXECUTE stmt3;
DEALLOCATE PREPARE stmt3;
