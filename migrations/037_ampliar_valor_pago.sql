-- Amplia valor_pago de DECIMAL(6,2) para DECIMAL(10,2)
-- Motivo: comprovantes com valor >= 10000 causavam crash antes de criar a
-- notificacao de "pagamento_alto", impedindo o fluxo de revisao humana.
ALTER TABLE pedidos
    MODIFY COLUMN valor_pago DECIMAL(10, 2) NOT NULL DEFAULT 0.00;
