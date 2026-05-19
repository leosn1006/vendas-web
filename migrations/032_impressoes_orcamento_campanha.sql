-- Migration 032: adiciona coluna impressoes em orcamento_campanha
-- NULL = não preenchido (distinto de 0 = zero impressões registradas)
ALTER TABLE orcamento_campanha
    ADD COLUMN impressoes INT NULL DEFAULT NULL;
