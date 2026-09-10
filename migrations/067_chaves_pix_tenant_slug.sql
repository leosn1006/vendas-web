-- Adiciona tenant_slug em chaves_pix_produto — fonte de verdade do tenant BB para cada chave PIX.
-- O tenant_slug indica em qual conta BB a chave está cadastrada, independente da config de NF-e.
ALTER TABLE chaves_pix_produto
    ADD COLUMN tenant_slug VARCHAR(50) NOT NULL DEFAULT 'lsn-livros' AFTER para_venda_web;

-- Corrige as chaves atualmente cadastradas que estão na conta LBE (lbe-livros).
UPDATE chaves_pix_produto SET tenant_slug = 'lbe-livros'
WHERE chave_pix IN (
    'pudim@lsnlivros.com.br',
    'tempero@lsnlivros.com.br',
    'fatia@lsnlivros.com.br'
);
