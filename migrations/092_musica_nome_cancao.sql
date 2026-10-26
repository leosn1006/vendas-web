-- Nome da marca da Música no site e nos e-mails: "Canção de Presente" (PR #1 do Bruno, 25/10/2026).
-- O site mostra produtos.email_nome_remetente (rotas._variaveis_das_paginas); o nome interno do produto
-- continua "Música de Presente" (as migrations e o admin acham o produto por ele).
-- Idempotente.
SET NAMES utf8mb4;

UPDATE produtos SET email_nome_remetente = 'Canção de Presente'
WHERE nome = 'Música de Presente' AND NOT (email_nome_remetente <=> 'Canção de Presente');

-- Conferência: tem que sair 1 linha com "Canção de Presente". Nenhuma linha = o produto foi renomeado no admin.
SELECT id, nome, email_nome_remetente FROM produtos WHERE nome = 'Música de Presente';
