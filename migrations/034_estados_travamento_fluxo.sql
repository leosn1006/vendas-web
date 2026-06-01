-- Estados intermediários de travamento de fluxo
-- Evitam que uma segunda mensagem re-dispare um fluxo já em andamento
INSERT IGNORE INTO estado_pedidos (id, descricao) VALUES
    (11, 'Introdução em andamento'),
    (12, 'Pedido em andamento'),
    (13, 'Comprovante em análise');
