-- Migration 016: dns_origem em pedidos + tabela google_ads_planilha_dns
-- Objetivo: permitir múltiplas planilhas Google Ads por produto, separadas por domínio de origem do lead.

-- 1. Coluna dns_origem em pedidos (registra qual domínio gerou o lead)
ALTER TABLE pedidos
  ADD COLUMN dns_origem VARCHAR(255) NULL
  COMMENT 'Domínio de origem do lead (ex: deliciasdalu.online)';

-- 2. Tabela de config Google Ads/Sheets por produto × DNS
CREATE TABLE IF NOT EXISTS google_ads_planilha_dns (
    id                           INT AUTO_INCREMENT PRIMARY KEY,
    produto_id                   INT          NOT NULL,
    dns                          VARCHAR(255) NOT NULL  COMMENT 'Ex: deliciasdalu.online',
    google_sheets_spreadsheet_id VARCHAR(255) NOT NULL,
    google_sheets_sheet_name     VARCHAR(100) NOT NULL DEFAULT 'Página1',
    google_ads_conversion_name   VARCHAR(255) NOT NULL,
    google_sa_env_var            VARCHAR(100) NOT NULL COMMENT 'Nome da env var com o JSON da Service Account (ex: GOOGLE_SA_JSON_DELICIAS)',
    ativo                        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at                   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_produto_dns (produto_id, dns),
    FOREIGN KEY (produto_id) REFERENCES produtos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
