-- Migration 030: Followup de interesse (estado 2)
-- Dois followups para clientes que receberam a introdução mas ainda não responderam
-- sobre interesse no produto: 15 min (quente) e 2h (recuperação).

-- 1. Colunas de controle de envio em pedidos
ALTER TABLE pedidos
    ADD COLUMN data_followup_interesse_1 TIMESTAMP NULL DEFAULT NULL,
    ADD COLUMN data_followup_interesse_2 TIMESTAMP NULL DEFAULT NULL;

-- 2. Retrocompatibilidade: clientes já em estado 2 não recebem followup
--    (evita disparar mensagens com horas/dias de atraso após o deploy)
UPDATE pedidos
    SET data_followup_interesse_1 = NOW(),
        data_followup_interesse_2 = NOW()
    WHERE estado_id = 2;

-- 3. Novos valores no ENUM do fluxo
ALTER TABLE acoes_fluxo_produto
    MODIFY COLUMN fluxo ENUM(
        'introducao',
        'pedido',
        'comprovante',
        'responder',
        'followup',
        'confirmacao_web',
        'followup_interesse_1',
        'followup_interesse_2'
    ) NOT NULL;
