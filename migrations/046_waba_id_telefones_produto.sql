-- waba_id descoberto via health_status durante o polling de qualidade (a resposta de
-- health_status já traz a WABA na cadeia de entidades) — usado pra filtrar
-- notificacoes_conta_whatsapp (nível WABA) por produto, já que esses eventos não trazem
-- api_phone_number_id no payload.
ALTER TABLE telefones_produto
    ADD COLUMN waba_id VARCHAR(50) NULL;

CREATE INDEX idx_telefones_produto_waba ON telefones_produto (waba_id);
