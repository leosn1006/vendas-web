-- Migration 111: o botão de compra da prévia vai para a oferta da Hotmart (Música do México). Ver docs/HOTMART.md.
--
-- hotmart_ofertas ganha o que é preciso para MONTAR o link (antes só servia para conferir o pagamento):
--   produto_hotmart  ID do produto na Hotmart (pay.hotmart.com/<id>?off=<codigo>)
--   preco + moeda    o preço que a prévia mostra (a Hotmart não informa na hora do clique)
--   uso              'botao' = a oferta do botão do plano (uma por plano) | 'popup' = a "última chance" com desconto |
--                    NULL = só confirma pagamento (não aparece em link)
-- Idempotente.

SET NAMES utf8mb4;

DROP PROCEDURE IF EXISTS _hotmart_111_coluna;
DELIMITER //
CREATE PROCEDURE _hotmart_111_coluna(IN nome VARCHAR(64), IN definicao VARCHAR(500))
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'hotmart_ofertas' AND COLUMN_NAME = nome) THEN
    SET @sql = CONCAT('ALTER TABLE hotmart_ofertas ADD COLUMN ', nome, ' ', definicao);
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END //
DELIMITER ;

CALL _hotmart_111_coluna('produto_hotmart', "BIGINT NULL COMMENT 'ID do produto na Hotmart (link pay.hotmart.com/<id>)'");
CALL _hotmart_111_coluna('preco', "DECIMAL(10,2) NULL COMMENT 'preço mostrado na prévia (na moeda abaixo)'");
CALL _hotmart_111_coluna('moeda', "CHAR(3) NULL");
CALL _hotmart_111_coluna('uso', "VARCHAR(10) NULL COMMENT 'botao | popup | NULL (só confirma pagamento)'");

DROP PROCEDURE _hotmart_111_coluna;

-- As ofertas da Canción de Regalo (México), produto Hotmart 9006872. O botão de "só a música" começa na oferta de
-- teste (valor baixo) para o teste de ponta a ponta; depois do teste, trocar para a tlaz6ojn (MX$ 149) no admin.
UPDATE hotmart_ofertas SET produto_hotmart = 9006872, preco = 50.00, moeda = 'MXN', uso = 'botao' WHERE codigo = 'sph9o75s';
UPDATE hotmart_ofertas SET produto_hotmart = 9006872, preco = 149.00, moeda = 'MXN', uso = NULL WHERE codigo = 'tlaz6ojn';
UPDATE hotmart_ofertas SET produto_hotmart = 9006872, preco = 229.00, moeda = 'MXN', uso = 'botao' WHERE codigo = 'cdr8fae7';
UPDATE hotmart_ofertas SET produto_hotmart = 9006872, preco = 199.00, moeda = 'MXN', uso = 'popup' WHERE codigo = '6wunkb5c';

SELECT codigo, produto_id, plano_id, produto_hotmart, preco, moeda, uso, ativo FROM hotmart_ofertas ORDER BY plano_id, codigo;
