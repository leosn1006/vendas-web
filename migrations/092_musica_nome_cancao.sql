-- Nome da marca da Música no site e nos e-mails: "Canção de Presente" (PR #1 do Bruno, 25/10/2026).
-- O site mostra produtos.email_nome_remetente (rotas._variaveis_das_paginas); o nome interno do produto
-- continua "Música de Presente" (as migrations e o admin acham o produto por ele).
-- Idempotente.
SET NAMES utf8mb4;

UPDATE produtos SET email_nome_remetente = 'Canção de Presente'
WHERE nome = 'Música de Presente' AND (email_nome_remetente IS NULL OR email_nome_remetente = 'Música de Presente');

SELECT id, nome, email_nome_remetente FROM produtos WHERE nome = 'Música de Presente';
