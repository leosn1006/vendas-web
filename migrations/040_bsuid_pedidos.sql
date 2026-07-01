-- Suporte a BSUID (Business-Scoped User ID) do WhatsApp
-- A partir de junho/2026 usuários com username podem ocultar o telefone.
-- Nesses casos o webhook traz user_id (BSUID) em vez de um número de telefone.
-- contact_to guarda o identificador correto para responder: telefone ou BSUID.

ALTER TABLE pedidos
  ADD COLUMN bsuid       VARCHAR(200) NULL AFTER contact_name,
  ADD COLUMN contact_to  VARCHAR(200) NULL AFTER bsuid;

-- Pedidos existentes respondem pelo telefone
UPDATE pedidos SET contact_to = contact_phone WHERE contact_to IS NULL AND contact_phone IS NOT NULL;

CREATE INDEX idx_pedidos_bsuid ON pedidos(bsuid);
