-- Migration 074: adiciona a FK que faltava em nfe_emitidas.pagamento_pix_id.
--
-- migrations/069_nfe_emitidas_cartao.sql adicionou fk_nfe_cartao (pagamento_cartao_id
-- -> pagamento_cartao.id), mas o lado do PIX nunca teve FK — só a UNIQUE KEY
-- uq_pagamento_pix já existente (039_nfe.sql). Isso permitia apagar um pagamento_pix
-- que já tinha uma NF-e emitida (ex: DELETE FROM pagamento_pix em
-- admin.apagar_pedido_usuario, numa race condition com a emissão assíncrona da NF-e)
-- sem erro nenhum, deixando o registro fiscal em nfe_emitidas órfão silenciosamente.
--
-- Não cria referência circular: pagamento_pix.nfe_emitida_id continua sem FK
-- (decisão original de 039_nfe.sql), só nfe_emitidas.pagamento_pix_id passa a ter —
-- mesmo padrão unidirecional que já existe pro cartão.
--
-- Pré-requisito: rodar antes desta migration
--   SELECT COUNT(*) FROM nfe_emitidas ne
--   LEFT JOIN pagamento_pix pp ON pp.id = ne.pagamento_pix_id
--   WHERE ne.pagamento_pix_id IS NOT NULL AND pp.id IS NULL;
-- Se der > 0, a ALTER TABLE abaixo falha — investigar e resolver os órfãos antes.

ALTER TABLE nfe_emitidas
  ADD CONSTRAINT fk_nfe_pix FOREIGN KEY (pagamento_pix_id) REFERENCES pagamento_pix(id);
