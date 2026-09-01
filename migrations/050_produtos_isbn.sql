-- Migration 050: adiciona ISBN e nome_nfe por produto para NF-e.
-- isbn  → cEAN / cEANTrib (ISBN-13 com ou sem hífens; hífens removidos no código)
-- nome_nfe → xProd na NF-e; separado do nome comercial usado no app/mobile.
--            NULL = usa nome da tabela como fallback.

SET @col_isbn = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'produtos'
      AND COLUMN_NAME  = 'isbn'
);
SET @sql_isbn = IF(@col_isbn = 0,
    'ALTER TABLE produtos ADD COLUMN isbn VARCHAR(20) NULL AFTER nome',
    'SELECT ''isbn ja existe, pulando ALTER''' );
PREPARE stmt FROM @sql_isbn; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_nome_nfe = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'produtos'
      AND COLUMN_NAME  = 'nome_nfe'
);
SET @sql_nome = IF(@col_nome_nfe = 0,
    'ALTER TABLE produtos ADD COLUMN nome_nfe VARCHAR(120) NULL AFTER isbn',
    'SELECT ''nome_nfe ja existe, pulando ALTER''' );
PREPARE stmt FROM @sql_nome; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Produto  8: E-book Receitas de Pudim Sem Forno
UPDATE produtos SET isbn = '978-65-976357-0-2', nome_nfe = 'E-book Receitas de Pudim Sem Forno'          WHERE id = 8;
-- Produto 11: Receitas Caseiras de Temperos no Pote
UPDATE produtos SET isbn = '978-65-976357-2-6', nome_nfe = 'E-book Receitas Caseiras de Temperos no Pote'       WHERE id = 11;
-- Produto 12: Receita Caseiras de Fatia de Bolos de Feira
UPDATE produtos SET isbn = '978-65-976357-1-9', nome_nfe = 'E-book Receita Caseiras de Fatia de Bolos de Feira' WHERE id = 12;
