-- Adiciona coluna faq diretamente na tabela de produtos
-- Substitui a leitura de arquivo via url_faq_produto
ALTER TABLE produtos
    ADD COLUMN faq TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci AFTER prompt_vendas;
