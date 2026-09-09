-- Migration 052: indica qual chave PIX usar para gerar o QR estático no checkout web.
-- para_venda_web=1 → chave embarcada no QR estático gerado em gerar_pix().
-- Cada produto deve ter no máximo 1 chave com para_venda_web=1 (validado no servidor).

SET @col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'chaves_pix_produto'
      AND COLUMN_NAME  = 'para_venda_web'
);
SET @sql = IF(@col = 0,
    'ALTER TABLE chaves_pix_produto ADD COLUMN para_venda_web TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''Se 1, esta chave e usada no QR estatico do checkout web''',
    'SELECT ''para_venda_web ja existe, pulando ALTER'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Marcar a chave email de cada produto como chave da venda web
UPDATE chaves_pix_produto SET para_venda_web = 1 WHERE id = 3;  -- produto  6: pascoa@lsnlivros.com.br
UPDATE chaves_pix_produto SET para_venda_web = 1 WHERE id = 1;  -- produto  8: pudim@lsnlivros.com.br
UPDATE chaves_pix_produto SET para_venda_web = 1 WHERE id = 11; -- produto 10: semacucar@lsnlivros.com.br
UPDATE chaves_pix_produto SET para_venda_web = 1 WHERE id = 8;  -- produto 11: tempero@lsnlivros.com.br
UPDATE chaves_pix_produto SET para_venda_web = 1 WHERE id = 9;  -- produto 12: fatia@lsnlivros.com.br
