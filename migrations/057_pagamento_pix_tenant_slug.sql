-- Migration 057: marca de qual conta BB (tenant) cada PIX foi recebido.
-- Necessário porque a empresa está migrando gradualmente de lsn-livros para
-- lbe-livros: as duas contas vão coexistir, e cada consulta BB só retorna
-- PIX das próprias chaves — a origem já é conhecida no momento da coleta,
-- não precisa ser inferida depois pela chave_pix.
--
-- Default 'lsn-livros': todo o histórico gravado até hoje veio exclusivamente
-- da conta lsn-livros (única integrada em produção antes desta migration).

SET @col_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'pagamento_pix'
      AND COLUMN_NAME  = 'tenant_slug'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE pagamento_pix ADD COLUMN tenant_slug VARCHAR(50) NOT NULL DEFAULT ''lsn-livros'' AFTER chave_pix',
    'SELECT ''tenant_slug ja existe, pulando ALTER''' );

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'pagamento_pix'
      AND INDEX_NAME    = 'idx_pix_tenant'
);

SET @sql_idx = IF(@idx_exists = 0,
    'ALTER TABLE pagamento_pix ADD INDEX idx_pix_tenant (tenant_slug, horario)',
    'SELECT ''idx_pix_tenant ja existe, pulando ALTER''' );

PREPARE stmt2 FROM @sql_idx;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;
