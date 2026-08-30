-- Migration 061: liga pedido_itens à nova base de e-books (ebooks_produto).
--
-- Coluna nova, nullable — pedidos antigos (criados antes desta migration, ainda referenciando
-- produto_bonus_id/produto_bump_id) ficam com ela NULL; pedidos novos passam a gravar aqui o
-- ebooks_produto.id de origem (principal, bônus ou bump), agora que o checkout web lê o
-- catálogo de ebooks em vez de produtos/produto_bonus/produto_bump.
--
-- produto_bonus_id/produto_bump_id NÃO são removidas nem alteradas — continuam servindo de
-- histórico pros pedidos antigos, só param de ser preenchidas daqui pra frente.
ALTER TABLE pedido_itens
    ADD COLUMN ebook_produto_id INT NULL AFTER produto_bump_id,
    ADD CONSTRAINT fk_pedido_itens_ebook_produto
        FOREIGN KEY (ebook_produto_id) REFERENCES ebooks_produto(id);
