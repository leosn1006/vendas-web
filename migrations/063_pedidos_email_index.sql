-- Migration 063: índice em pedidos.email pra suportar "Minha Estante" — agregar todos os
-- e-books pagos de um cliente (por e-mail e/ou telefone) na página /pedido/<guid>.
--
-- pedidos.email não tinha índice até agora (~263 mil linhas, full scan garantido em qualquer
-- WHERE email = ...). contact_phone já tem (idx_pedidos_phone). Composto com estado_id porque
-- o filtro real sempre é "email = X AND estado_id IN (0,1000)" — o índice fica index-only pra
-- essa parte, sem precisar tocar a tabela de dados só pra descartar pedidos não pagos.
CREATE INDEX idx_pedidos_email_estado ON pedidos(email, estado_id);
