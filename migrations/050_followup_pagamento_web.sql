-- Migration 050: Follow-up por e-mail do checkout web (Pix gerado, não pago)
-- Coluna dedicada, separada de `data_followup` (específica do fluxo WhatsApp) —
-- pedido web também coleta telefone, então reaproveitar `data_followup` arriscaria
-- bloquear indevidamente um futuro follow-up por WhatsApp só porque o e-mail já rodou.

ALTER TABLE pedidos
    ADD COLUMN data_followup_pagamento_web TIMESTAMP NULL DEFAULT NULL
        COMMENT 'Preenchido após envio do lembrete de pagamento por e-mail (checkout web, estado 1002)';
