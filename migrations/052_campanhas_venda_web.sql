-- Marca campanhas cujo tráfego é direcionado ao checkout web (BB Pay), não ao WhatsApp.
-- Default FALSE: hoje praticamente todas as campanhas existentes são para vendas via WhatsApp.
ALTER TABLE campanhas ADD COLUMN venda_web BOOLEAN NOT NULL DEFAULT FALSE;
