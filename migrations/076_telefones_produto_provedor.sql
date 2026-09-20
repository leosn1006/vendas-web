-- Provedor de envio por número: API oficial da Meta ('meta', padrão) ou gateway WhatsApp Web
-- ('wpp_web', projeto api-wpp-web, que imita a Cloud API). Coluna default = 'meta' mantém o
-- comportamento atual de todos os números já cadastrados.
ALTER TABLE telefones_produto
    ADD COLUMN provedor ENUM('meta','wpp_web') NOT NULL DEFAULT 'meta'
        COMMENT 'meta = Graph API oficial; wpp_web = gateway WhatsApp Web (api-wpp-web)'
        AFTER token_env_key;

-- O gateway usa phone_number_id = 'web-<numero>' (17 chars com DDI+DDD+9 dígitos); o VARCHAR(20) atual
-- estoura com número de 16+ dígitos. Alinha com telefones_produto.api_phone_number_id (VARCHAR(50)).
ALTER TABLE pedidos
    MODIFY COLUMN phone_number_id VARCHAR(50) NULL DEFAULT NULL;

ALTER TABLE variantes_fluxo_cursor
    MODIFY COLUMN phone_number_id VARCHAR(50) NOT NULL COMMENT 'Nosso número emissor (WhatsApp Business)';
