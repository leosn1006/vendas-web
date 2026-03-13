-- Migration 012: campos de pagamento BB Pay na tabela pedidos
-- CPF/CNPJ formatado (CNPJ pode ser alfanumérico a partir de jun/2026)

ALTER TABLE pedidos
  ADD COLUMN cpf_cnpj_pagador        VARCHAR(20)   NULL COMMENT 'CPF ou CNPJ formatado do pagador (BB Pay)'  AFTER nome_pagador,
  ADD COLUMN valor_liquido_pagamento DECIMAL(10,2) NULL COMMENT 'valorLiquidoRecebedor BB Pay'               AFTER valor_pago,
  ADD COLUMN data_repasse            DATE          NULL COMMENT 'dataRepassePagamento BB Pay'                 AFTER data_pagamento,
  ADD COLUMN e2e_id                  VARCHAR(100)  NULL COMMENT 'e2eId PIX (BB Pay)'                         AFTER data_repasse;
