-- Admin → Músicas vendidas → "Refazer a música" (29/10/2026, docs/MUSICA.md "Refazer a música de uma compra"): o admin
-- faz um RASCUNHO (uma música nova, sem e-mail nem pedido, com as escolhas da original editáveis), gera, ouve e só então
-- troca o conteúdo da música da cliente — mesmo token, link, QR code, pedido e presente. Idempotente.
SET NAMES utf8mb4;

SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'musicas' AND COLUMN_NAME = 'rascunho_de');
SET @sql = IF(@tem = 0, 'ALTER TABLE musicas
    ADD COLUMN rascunho_de INT NULL COMMENT ''Rascunho do admin para refazer esta música (id da original, já paga)'' AFTER pedido_origem_id,
    ADD COLUMN rascunho_usado_em DATETIME NULL COMMENT ''Quando o rascunho entrou no lugar da original'' AFTER rascunho_de,
    ADD COLUMN refeita_em DATETIME NULL COMMENT ''Última vez que o admin trocou o conteúdo desta música por um rascunho'' AFTER rascunho_usado_em,
    ADD KEY idx_musicas_rascunho (rascunho_de)', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

SHOW COLUMNS FROM musicas LIKE 'r%';
