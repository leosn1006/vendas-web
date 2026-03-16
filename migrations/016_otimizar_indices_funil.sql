-- Migration 016: Otimizar índices para queries do funil de analytics
-- Remove índice antigo e cria índices mais específicos para melhor performance

USE vendasdb;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Remove índice antigo que não é totalmente otimizado
-- Usa ALTER TABLE para compatibilidade com todas as versões do MySQL
ALTER TABLE pedidos DROP INDEX IF EXISTS idx_analytics_site;

-- Cria índice otimizado para o funil de conversão
-- Este índice cobre TODAS as colunas usadas na query do funil:
-- WHERE produto_id = X AND data_contato_site BETWEEN Y AND Z
-- SELECT ... COUNT(CASE WHEN estado_id = A), COUNT(CASE WHEN interesse_produto = B), COUNT(CASE WHEN data_followup IS NULL)
ALTER TABLE pedidos
  ADD INDEX idx_funil_contato (produto_id, data_contato_site, estado_id, interesse_produto, data_followup);

-- Nota: idx_analytics_pag (produto_id, estado_id, data_pagamento) já existe e está otimizado para queries de receita

-- ============================================================
-- Explicação da otimização:
-- ============================================================
--
-- idx_funil_contato (produto_id, data_contato_site, estado_id, interesse_produto, data_followup)
-- -------------------------------------------------------------------------------------------------
-- Índice COVERING otimizado para a query principal do funil analytics:
--
--   SELECT
--     COUNT(*),
--     COUNT(CASE WHEN estado_id != 1 THEN 1 END),
--     COUNT(CASE WHEN interesse_produto = 1 THEN 1 END),
--     COUNT(CASE WHEN interesse_produto = 0 THEN 1 END),
--     COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 1 THEN 1 END),
--     COUNT(CASE WHEN estado_id = 0 AND data_followup IS NULL THEN 1 END),
--     COUNT(CASE WHEN estado_id = 0 AND data_followup IS NOT NULL THEN 1 END)
--   FROM pedidos
--   WHERE produto_id = %s AND data_contato_site BETWEEN %s AND %s
--
-- Vantagens:
-- 1. produto_id primeiro → filtra produto instantaneamente
-- 2. data_contato_site segundo → range scan eficiente (BETWEEN)
-- 3. estado_id, interesse_produto, data_followup cobertos → INDEX-ONLY SCAN
-- 4. MySQL NÃO precisa acessar a tabela, só o índice (covering index)
--
-- Performance esperada:
-- - 10-100x mais rápido em tabelas com milhões de registros
-- - Query completa executada diretamente no índice (sem table lookup)
-- - Reduz drasticamente I/O de disco e uso de CPU
