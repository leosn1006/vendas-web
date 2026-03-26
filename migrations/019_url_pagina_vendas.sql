-- Migration 019: Adiciona url_pagina_vendas aos produtos
-- Permite exibir cada produto no portfólio com link direto para sua página de vendas

ALTER TABLE produtos
    ADD COLUMN url_pagina_vendas VARCHAR(255) DEFAULT NULL
        COMMENT 'URL da página de vendas do produto (ex: /pudim). Exibida no portfólio quando disponivel_web=TRUE.';
