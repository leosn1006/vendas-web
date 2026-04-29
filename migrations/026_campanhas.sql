CREATE TABLE IF NOT EXISTS campanhas (
    produto_id  INT          NOT NULL,
    campaignid  VARCHAR(255) NOT NULL,
    nome        VARCHAR(255) NOT NULL,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (produto_id, campaignid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
