-- Migration 105: origem da credencial do cartão em cada tentativa (pagamento_cartao).
--
-- Até aqui o checkout mandava o número do cartão e o CVV para o nosso backend ('digitado').
-- Com o Silent Order Post da Cielo, o navegador tokeniza o cartão e o backend só recebe o
-- PaymentToken ('sop'). As wallets entram depois como 'google_pay' / 'apple_pay' — a coluna
-- já serve para comparar a conversão de cada uma.
--
-- O DEFAULT do ALTER retroage para as linhas existentes: todas são 'digitado'.
SET @col_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'pagamento_cartao'
      AND COLUMN_NAME  = 'origem'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE pagamento_cartao ADD COLUMN origem VARCHAR(20) NOT NULL DEFAULT ''digitado'' COMMENT ''digitado | sop | google_pay | apple_pay'' AFTER parcelas',
    'SELECT ''origem ja existe, pulando ALTER''');

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
