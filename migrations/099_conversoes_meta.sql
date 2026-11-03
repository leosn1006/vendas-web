-- Conversões da Meta (Instagram), docs/META_CONVERSOES.md: o clique fica no pedido (fbc), como o gclid; a campanha diz o
-- canal e o destino (campanhas.plataforma, meta_dataset_id e meta_token_env_var). Idempotente.
SET NAMES utf8mb4;

SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pedidos' AND COLUMN_NAME = 'fbc');
SET @sql = IF(@tem = 0, 'ALTER TABLE pedidos
    ADD COLUMN fbc VARCHAR(600) NULL COMMENT ''Clique da Meta: fb.1.<timestamp em ms>.<fbclid>'' AFTER gbraid,
    ADD COLUMN client_ip VARCHAR(45) NULL COMMENT ''IP da cliente ao finalizar o pedido ou criar o lead'' AFTER fbc,
    ADD COLUMN client_user_agent VARCHAR(512) NULL COMMENT ''Navegador da cliente ao finalizar o pedido ou criar o lead'' AFTER client_ip,
    ADD COLUMN data_envio_meta DATETIME NULL COMMENT ''Quando a Meta aceitou a venda (events_received >= 1)'' AFTER data_envio_google_ads', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

SET @tem = (SELECT COUNT(*) FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'pedidos' AND INDEX_NAME = 'idx_pedidos_envio_meta');
SET @sql = IF(@tem = 0, 'ALTER TABLE pedidos ADD KEY idx_pedidos_envio_meta (data_envio_meta, estado_id, data_pagamento)', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'campanhas' AND COLUMN_NAME = 'plataforma');
SET @sql = IF(@tem = 0, 'ALTER TABLE campanhas
    ADD COLUMN plataforma VARCHAR(20) NOT NULL DEFAULT ''google'' COMMENT ''Canal da campanha: google ou meta'',
    ADD COLUMN meta_conta_id VARCHAR(50) NULL COMMENT ''Conta de anúncio da campanha, descoberta pelo token'',
    ADD COLUMN meta_dataset_id VARCHAR(30) NULL COMMENT ''Dataset para onde vão as vendas, descoberto nos conjuntos da campanha'',
    ADD COLUMN meta_token_env_var VARCHAR(100) NULL COMMENT ''Nome da env var do token que enxerga a campanha (META_TOKEN_...)''', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

SHOW COLUMNS FROM pedidos LIKE 'fbc';
