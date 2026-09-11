-- Migration 070: identifica qual conta BB (tenant) recebeu cada PIX.
-- tenant_slug = 'lsn-livros' (integração antiga) ou 'lbe-livros' (integração atual).
-- Back-fill via API do BB necessário para registros de 2026-08-20 em diante
-- (ver scripts/backfill_pix_tenant_slug.py).

ALTER TABLE pagamento_pix
    ADD COLUMN tenant_slug VARCHAR(50) NULL AFTER produto_id,
    ADD INDEX idx_pix_tenant (tenant_slug);

-- Antes de 20/08/2026: certeza que era LSN
UPDATE pagamento_pix
SET tenant_slug = 'lsn-livros'
WHERE horario < '2026-08-20 00:00:00';

-- Após rodar scripts/backfill_pix_tenant_slug.py, executar:
-- UPDATE pagamento_pix SET tenant_slug = 'lsn-livros' WHERE tenant_slug IS NULL;
-- ALTER TABLE pagamento_pix MODIFY COLUMN tenant_slug VARCHAR(50) NOT NULL DEFAULT 'lsn-livros';
