-- Migration 056: Imagens no checkout (produto principal + order bumps)
-- Campo dedicado ao checkout, independente de url_imagem_complementar (usado no site/portfólio).
-- Guarda apenas o nome do arquivo em static/images/, não uma URL completa.

ALTER TABLE produtos
    ADD COLUMN imagem_checkout VARCHAR(255) NULL AFTER url_imagem_complementar;

ALTER TABLE produto_bump
    ADD COLUMN imagem_checkout VARCHAR(255) NULL AFTER descricao;
