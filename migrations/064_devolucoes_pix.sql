-- Tabela de devoluções de PIX (estorno, total ou parcial, de um PIX já recebido).
-- Um pagamento_pix pode ter N devoluções, desde que a soma não ultrapasse o
-- valor original — essa regra é garantida pelo BB, não validada aqui.
CREATE TABLE devolucoes_pix (
  id                    INT AUTO_INCREMENT PRIMARY KEY,
  pagamento_pix_id      INT           NULL,
  e2e_id                VARCHAR(35)   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  rtr_id                VARCHAR(35)   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL UNIQUE,
  valor                 DECIMAL(10,2) NOT NULL,
  natureza              VARCHAR(20)   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  descricao             VARCHAR(255)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  motivo                VARCHAR(255)  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  status                VARCHAR(30)   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
  horario_solicitacao   DATETIME      NULL,
  horario_liquidacao    DATETIME      NULL,
  tenant_slug           VARCHAR(50)   NOT NULL DEFAULT 'lsn-livros',
  criado_em             DATETIME      DEFAULT NOW(),
  atualizado_em         DATETIME      DEFAULT NOW() ON UPDATE NOW(),
  INDEX idx_devol_horario_liquidacao (horario_liquidacao),
  FOREIGN KEY (pagamento_pix_id) REFERENCES pagamento_pix(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
