-- Migration 007: Tabelas independentes para o fluxo de venda pelo site (web checkout)
-- Desacopla completamente do fluxo WhatsApp (tabela pedidos)
-- Inclui colunas nome_cliente e email (consolida 008)

SET NAMES utf8mb4;

-- Remove tabelas antigas na ordem inversa (FK)
DROP TABLE IF EXISTS pagamento_web;
DROP TABLE IF EXISTS pedido_web;
DROP TABLE IF EXISTS produto_web;


CREATE TABLE produto_web (
  id              INT                                                  NOT NULL AUTO_INCREMENT,
  descricao       VARCHAR(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  numero_convenio BIGINT                                               NOT NULL  COMMENT 'Número do convênio BB Pay para este produto',
  preco           DECIMAL(8,2)                                         NOT NULL,
  url_pdf         VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'Arquivo principal entregue após pagamento',
  url_pdf_bonus   VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'Brinde enviado junto (ex: bolos-sem-gluten.pdf)',
  ativo           TINYINT(1)                                           NOT NULL DEFAULT 1,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Seed: Guia de Pães Sem Glúten
INSERT INTO produto_web (descricao, numero_convenio, preco, url_pdf, url_pdf_bonus)
VALUES ('Guia Pães Sem Glúten', 275513, 19.90, 'paes-sem-gluten.pdf', 'bolos-sem-gluten.pdf');


CREATE TABLE pedido_web (
  id                 INT                                                          NOT NULL AUTO_INCREMENT,
  data               TIMESTAMP                                                    NOT NULL DEFAULT NOW(),
  estado             TINYINT                                                      NOT NULL DEFAULT 1 COMMENT '0=Pago, 1=Pedido criado, 2=Aguardando pagamento',
  valor              DECIMAL(8,2)                                                 NOT NULL,
  remetente_id       VARCHAR(20)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  gclid              VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  campaignid         VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  adgroupid          VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  creative           VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  matchtype          VARCHAR(50)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  device             VARCHAR(50)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  placement          VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  video_id           VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  phone_contact      VARCHAR(20)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  nome_cliente       VARCHAR(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  email              VARCHAR(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  phone_name         VARCHAR(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'Preenchido após entrega via WhatsApp',
  numero_solicitacao VARCHAR(50)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'txid BB Pay',
  PRIMARY KEY (id),
  INDEX idx_pedido_web_txid   (numero_solicitacao),
  INDEX idx_pedido_web_phone  (phone_contact),
  INDEX idx_pedido_web_email  (email),
  INDEX idx_pedido_web_estado (estado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE pagamento_web (
  id             INT                                                          NOT NULL AUTO_INCREMENT,
  pedido_web_id  INT                                                          NOT NULL,
  valor          DECIMAL(8,2)                                                 NOT NULL,
  valor_tarifa   DECIMAL(5,2)                                                 NOT NULL COMMENT 'Taxa cobrada (ex: 0.80 BB Pay)',
  data_pagamento TIMESTAMP                                                    NOT NULL,
  tipo_pagamento ENUM('Pix', 'Cartao de Credito', 'Boleto')                  NOT NULL DEFAULT 'Pix',
  id_pagador     VARCHAR(20)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  nome_pagador   VARCHAR(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  e2e_pix        VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT 'End-to-end ID da transação PIX',
  data_repasse   DATE                                                         NULL COMMENT 'Data prevista de repasse pelo banco',
  PRIMARY KEY (id),
  CONSTRAINT fk_pagamento_web_pedido FOREIGN KEY (pedido_web_id) REFERENCES pedido_web(id),
  INDEX idx_pagamento_web_pedido (pedido_web_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
