-- Migration 013: adiciona email_remetente em produto_web
-- Cada produto pode ter seu próprio endereço de envio (ex: paes@lsnlivros.com.br)
-- Fallback: variável SMTP_USER do .env

ALTER TABLE produto_web
  ADD COLUMN email_remetente VARCHAR(120) NULL
    COMMENT 'Endereço De: usado no envio do e-book. Ex: paes@lsnlivros.com.br';

-- Seed: preencher o produto 1 com o e-mail padrão
UPDATE produto_web SET email_remetente = 'paes@lsnlivros.com.br' WHERE id = 1;
