-- Estado de qualidade do número WhatsApp, atualizado de hora em hora pela task
-- tasks.verificar_qualidade_whatsapp (minuto :20). Substitui a checagem manual via script.
ALTER TABLE telefones_produto
    ADD COLUMN quality_rating          ENUM('GREEN','YELLOW','RED','UNKNOWN') NOT NULL DEFAULT 'UNKNOWN',
    ADD COLUMN status_api              VARCHAR(50)  NULL,
    ADD COLUMN name_status_api         VARCHAR(50)  NULL,
    ADD COLUMN qualidade_atualizada_em TIMESTAMP NULL,
    ADD COLUMN qualidade_erro          VARCHAR(255) NULL;

CREATE INDEX idx_telefones_produto_quality ON telefones_produto (produto_id, quality_rating);
