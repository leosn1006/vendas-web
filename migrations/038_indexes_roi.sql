-- Índices para otimizar queries de ROI por período
-- Beneficiam tanto roi_produto quanto roi_todos_produtos

-- Ordem: equality (estado_id) → range (data_pagamento) → cobertura (produto_id, valor_pago)
-- Serve à query consolidada (sem filtro produto_id no WHERE) e à query por produto
ALTER TABLE pedidos
    ADD INDEX idx_pedidos_estado_pagamento_produto (estado_id, data_pagamento, produto_id, valor_pago);

-- Ordem: range (horario) → cobertura (produto_id, valor)
-- Otimiza a query consolidada WHERE horario BETWEEN ... GROUP BY produto_id
ALTER TABLE pagamento_pix
    ADD INDEX idx_pix_horario_produto (horario, produto_id, valor);
