-- Analytics indexes para queries de funil e receita por produto/período
-- Executar uma vez em produção antes de usar o dashboard de analytics

ALTER TABLE pedidos
  ADD INDEX IF NOT EXISTS idx_analytics_site (produto_id, estado_id, data_contato_site),
  ADD INDEX IF NOT EXISTS idx_analytics_pag  (produto_id, estado_id, data_pagamento);
