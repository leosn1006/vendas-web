-- Tabela de chaves PIX por produto (suporta múltiplas chaves e histórico)
CREATE TABLE chaves_pix_produto (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  produto_id  INT          NOT NULL,
  chave_pix   VARCHAR(77)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  ativo       TINYINT(1)   NOT NULL DEFAULT 1,
  criado_em   DATETIME     DEFAULT NOW(),
  UNIQUE KEY uk_produto_chave (produto_id, chave_pix),
  FOREIGN KEY (produto_id) REFERENCES produtos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Tabela de pagamentos PIX recebidos
CREATE TABLE pagamento_pix (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  e2e_id        VARCHAR(35)   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL UNIQUE,
  produto_id    INT           NULL,
  chave_pix     VARCHAR(77)   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  valor         DECIMAL(10,2) NOT NULL,
  horario       DATETIME      NOT NULL,
  cpf_cnpj      VARCHAR(14)   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  nome_pagador  VARCHAR(255)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  txid          VARCHAR(35)   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  criado_em     DATETIME      DEFAULT NOW(),
  FOREIGN KEY (produto_id) REFERENCES produtos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
