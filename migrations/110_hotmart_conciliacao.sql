-- Migration 110: conciliação da Hotmart pela API de vendas (fase 2b). Ver docs/HOTMART.md → "Conciliação".
--
-- pagamento_hotmart ganha o que a API diz de cada venda (colunas api_*), quando foi conciliada e a divergência
-- (NULL = webhook e API batem). hotmart_conciliacoes guarda cada execução (beat de hora em hora ou o botão).
-- Idempotente: cada coluna só é criada se ainda não existir.

SET NAMES utf8mb4;

DROP PROCEDURE IF EXISTS _hotmart_110_coluna;
DELIMITER //
CREATE PROCEDURE _hotmart_110_coluna(IN nome VARCHAR(64), IN definicao VARCHAR(500))
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pagamento_hotmart' AND COLUMN_NAME = nome) THEN
    SET @sql = CONCAT('ALTER TABLE pagamento_hotmart ADD COLUMN ', nome, ' ', definicao);
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END //
DELIMITER ;

CALL _hotmart_110_coluna('api_status', "VARCHAR(30) NULL COMMENT 'purchase.status na API de vendas'");
CALL _hotmart_110_coluna('api_total', "DECIMAL(12,2) NULL COMMENT 'valor cheio pago (com IVA), na moeda da cliente'");
CALL _hotmart_110_coluna('api_moeda', "CHAR(3) NULL");
CALL _hotmart_110_coluna('api_iva', "DECIMAL(12,2) NULL COMMENT 'price/details.vat (na moeda api_moeda_iva)'");
CALL _hotmart_110_coluna('api_moeda_iva', "CHAR(3) NULL");
CALL _hotmart_110_coluna('api_taxa', "DECIMAL(12,2) NULL COMMENT 'history.hotmart_fee.total'");
CALL _hotmart_110_coluna('api_moeda_taxa', "CHAR(3) NULL");
CALL _hotmart_110_coluna('api_taxa_percentual', "DECIMAL(6,2) NULL COMMENT 'hotmart_fee.percentage (ex.: 20 = 20%)'");
CALL _hotmart_110_coluna('api_taxa_fixa', "DECIMAL(12,2) NULL COMMENT 'hotmart_fee.fixed'");
CALL _hotmart_110_coluna('api_liquido', "DECIMAL(12,2) NULL COMMENT 'commissions[PRODUCER] na API'");
CALL _hotmart_110_coluna('api_moeda_liquido', "CHAR(3) NULL");
CALL _hotmart_110_coluna('api_garantia_ate', "DATETIME NULL COMMENT 'warranty_expire_date'");
CALL _hotmart_110_coluna('api_xcod', "VARCHAR(64) NULL COMMENT 'tracking.external_code (= xcod = guid do pedido)'");
CALL _hotmart_110_coluna('api_oferta', "VARCHAR(40) NULL");
CALL _hotmart_110_coluna('conciliado_em', "DATETIME NULL");
CALL _hotmart_110_coluna('divergencia', "VARCHAR(500) NULL COMMENT 'NULL = webhook e API batem'");

DROP PROCEDURE _hotmart_110_coluna;

CREATE TABLE IF NOT EXISTS hotmart_conciliacoes (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  origem        VARCHAR(10)   NOT NULL COMMENT 'beat | botao',
  periodo_de    DATETIME      NOT NULL,
  periodo_ate   DATETIME      NOT NULL,
  inicio        DATETIME      DEFAULT NOW(),
  fim           DATETIME      NULL,
  vendas_api    INT           NOT NULL DEFAULT 0,
  novas         INT           NOT NULL DEFAULT 0 COMMENT 'vendas que o webhook não tinha trazido',
  confirmadas   INT           NOT NULL DEFAULT 0 COMMENT 'pedidos pagos pela conciliação',
  divergentes   INT           NOT NULL DEFAULT 0,
  reentregas    INT           NOT NULL DEFAULT 0 COMMENT 'pedidos pagos sem entrega que tiveram a entrega reagendada',
  erro          VARCHAR(500)  NULL,
  INDEX idx_hotmart_conciliacoes_inicio (inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
