-- Captura bruta de eventos de nível WABA/Business Manager, sem UI dedicada ainda (fase 2).
-- account_update, account_review_update, account_alerts, business_capability_update
-- não trazem api_phone_number_id no payload (só waba_id/business_id), por isso não
-- cabem em notificacoes_telefone (FK telefone_id NOT NULL). Tabela separada de propósito.
-- Evita perder histórico de incidentes tipo "14 WABAs banidas simultaneamente" enquanto
-- a modelagem de WABA/Business como entidades não é feita.
CREATE TABLE IF NOT EXISTS notificacoes_conta_whatsapp (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    tipo_evento  VARCHAR(50) NOT NULL,   -- account_update | account_review_update | account_alerts | business_capability_update
    waba_id      VARCHAR(50) NULL,
    business_id  VARCHAR(50) NULL,
    payload_raw  JSON NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_waba (waba_id, created_at),
    INDEX idx_tipo (tipo_evento, created_at)
);
