CREATE TABLE IF NOT EXISTS orcamento_campanha (
    produto_id       INT             NOT NULL,
    campaignid       VARCHAR(255)    NOT NULL,
    data             DATE            NOT NULL,
    valor_investido  DECIMAL(10,2)   NOT NULL,
    updated_at       TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (produto_id, campaignid, data)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
