-- Migration 009: Adiciona configuração do Google Sheets por produto
-- Permite que cada produto envie GCLIDs para sua própria planilha no Google Drive
-- A credencial (Service Account JSON) fica no .env como GOOGLE_SA_JSON_P{produto_id}

ALTER TABLE produtos
  ADD COLUMN google_sheets_spreadsheet_id VARCHAR(255) NULL COMMENT 'ID da planilha no Google Drive (extraído da URL)',
  ADD COLUMN google_sheets_sheet_name     VARCHAR(100) NULL DEFAULT 'Página1' COMMENT 'Nome da aba na planilha',
  ADD COLUMN google_ads_conversion_name   VARCHAR(255) NULL COMMENT 'Nome da ação de conversão no painel do Google Ads';
