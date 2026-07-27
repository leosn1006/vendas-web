-- Migration 049: vincula produtos ao tenant de NF-e (nfe_configuracao)
-- Necessário para filtrar quais PIX pertencem a cada empresa emissora.
-- Sem essa coluna, reprocessar_nfe_pendentes emite NF-e com CNPJ errado.

ALTER TABLE produtos
    ADD COLUMN nfe_config_id INT NULL AFTER updated_at,
    ADD CONSTRAINT fk_produtos_nfe_config
        FOREIGN KEY (nfe_config_id) REFERENCES nfe_configuracao(id);

-- Produtos confirmados como LBE LIVROS LTDA (CNPJ 68184503000106).
-- Demais produtos (nfe_config_id NULL) usam a configuração ativa padrão (LSN).
UPDATE produtos
SET nfe_config_id = (SELECT id FROM nfe_configuracao WHERE tenant_slug = 'lbe-livros')
WHERE id IN (8, 10, 11, 12);
