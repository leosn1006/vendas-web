-- Migration 031: adiciona coluna cliques em orcamento_campanha
-- NULL = não preenchido (distinto de 0 = zero cliques registrados)
ALTER TABLE orcamento_campanha
    ADD COLUMN cliques INT NULL DEFAULT NULL;
