-- Novos estados de funil web: registram a visita ANTES de qualquer identidade do cliente
-- (mesmo padrão já usado no fluxo WhatsApp, onde um pedido é criado no clique do botão,
-- antes de qualquer conversa — estado 1).
-- 1004 = chegou na página de vendas (landing); 1003 = chegou no checkout.
-- Não reaproveita 1001/1002/1000, que já têm significado hoje e são lidos por
-- buscar_pedidos_aguardando_bb_pay() e pelos dashboards de analytics web.

INSERT INTO estado_pedidos (id, descricao) VALUES
    (1004, 'Chegou na página de vendas'),
    (1003, 'Chegou no checkout web');
