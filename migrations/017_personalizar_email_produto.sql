-- Migration 017: personalização de e-mail de entrega por produto
-- Adiciona campos para customizar nome do remetente e cores do template HTML

USE vendasdb;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE produtos
  ADD COLUMN email_nome_remetente VARCHAR(100) NULL
    COMMENT 'Nome usado no corpo e assinatura do e-mail (ex: Luiza, Luiza Carolina)',
  ADD COLUMN email_cor_primaria VARCHAR(7) NULL
    COMMENT 'Cor do header do e-mail em hexadecimal (ex: #2d6a1f verde, #ec4899 rosa)',
  ADD COLUMN email_cor_secundaria VARCHAR(7) NULL
    COMMENT 'Cor dos botões de download em hexadecimal (ex: #b45309 marrom, #3b82f6 azul)';

-- Seed: produto 1 (Pães Sem Glúten) - mantém visual atual
UPDATE produtos
SET
  email_nome_remetente = 'Luiza',
  email_cor_primaria = '#2d6a1f',
  email_cor_secundaria = '#b45309'
WHERE id = 1;

-- Seed: produto 7 (Dicas de Quimio) - cores rosa e azul
UPDATE produtos
SET
  email_nome_remetente = 'Luiza Carolina',
  email_cor_primaria = '#ec4899',
  email_cor_secundaria = '#3b82f6'
WHERE id = 7;
