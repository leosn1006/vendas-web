-- Migration 071: estado terminal para pedidos de cartão sem resposta definitiva da Cielo.
-- Distinto de 1006 (negado pela operadora) — aqui a autorização nunca foi obtida.
-- Pedidos em 1005 com mais de 7 dias sem resposta são movidos para 1007 pelo sweep.

INSERT IGNORE INTO estado_pedidos (id, descricao)
VALUES (1007, 'Cartão não processado — autorização não obtida');
