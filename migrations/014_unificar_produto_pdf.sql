-- Migration 014: completa unificação produto_web → produtos
-- Move url_pdf, url_pdf_bonus, email_remetente para a tabela produtos
-- e dropa as tabelas legadas produto_web e pedido_web

ALTER TABLE produtos
  ADD COLUMN url_pdf         VARCHAR(255) NULL COMMENT 'Arquivo principal do e-book (ex: guia-paes.pdf)',
  ADD COLUMN url_pdf_bonus   VARCHAR(255) NULL COMMENT 'Bônus opcional (ex: bolos-fofinhos.pdf)',
  ADD COLUMN email_remetente VARCHAR(120) NULL COMMENT 'Endereço De: usado no envio do e-book. Ex: paes@lsnlivros.com.br';

-- Copia dados do produto_web id=1 para produtos id=1
UPDATE produtos p
JOIN produto_web pw ON pw.id = 1
SET
  p.url_pdf         = pw.url_pdf,
  p.url_pdf_bonus   = pw.url_pdf_bonus,
  p.email_remetente = pw.email_remetente
WHERE p.id = 1;

-- Remove tabelas legadas (ambiente de testes — sem dados de produção)
DROP TABLE IF EXISTS pedido_web;
DROP TABLE IF EXISTS produto_web;
