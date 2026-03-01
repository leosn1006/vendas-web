-- Migração 003: Tabela de mapeamento telefone → produto
-- Permite identificar o produto pelo número WhatsApp que recebe o contato,
-- servindo como fallback quando os dados de rastreamento do Google Ads (gclid/campaignid) não chegam.

USE vendasdb;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS telefones_produto (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    telefone    VARCHAR(50)  NOT NULL COMMENT 'phone_number_id do WhatsApp Business (número do vendedor)',
    produto_id  INT          NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tp_produto FOREIGN KEY (produto_id) REFERENCES produtos(id),
    CONSTRAINT uk_telefone   UNIQUE KEY (telefone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Mapeia número WhatsApp do vendedor ao produto correspondente';
