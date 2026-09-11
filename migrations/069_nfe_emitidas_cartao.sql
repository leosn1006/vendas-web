-- Migration 069: suporte a NF-e de pagamento por cartão.
-- pagamento_pix_id torna-se nullable (NF-e de cartão não tem PIX associado).
-- Adiciona pagamento_cartao_id com FK e índice único.

ALTER TABLE nfe_emitidas MODIFY pagamento_pix_id INT NULL;

ALTER TABLE nfe_emitidas
    ADD COLUMN pagamento_cartao_id INT NULL AFTER pagamento_pix_id,
    ADD CONSTRAINT fk_nfe_cartao FOREIGN KEY (pagamento_cartao_id) REFERENCES pagamento_cartao(id),
    ADD UNIQUE INDEX uq_nfe_cartao (pagamento_cartao_id);
