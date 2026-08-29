-- Migration 058: pagamento com cartão de crédito via Cielo (checkout web).
--
-- Novos estados 1005/1006: 1001 ("Pedido web criado") continua método-agnóstico
-- e serve tanto Pix quanto Cartão — não recriamos um gêmeo só pra cartão.
-- 1005 marca "estou prestes a chamar a Cielo", gravado ANTES da chamada HTTP,
-- pra o sweep de reconciliação achar pedidos presos mesmo se a chamada travar
-- antes de qualquer resposta. 1006 é "negado nesta tentativa" — cliente pode
-- tentar outro cartão (volta pra 1005) ou trocar pra Pix. Aprovado reaproveita
-- o 1000 já existente ("pago via web"), que já é tratado como método-agnóstico
-- em todo o código (liberação de download, analytics, e-mail de entrega).
INSERT IGNORE INTO estado_pedidos (id, descricao) VALUES
    (1005, 'Aguardando autorização Cielo (cartão)'),
    (1006, 'Cartão negado pela operadora');

-- config_cartao_produto: 1 linha por produto, configuração (não histórico).
-- max_parcelas funciona como teto de custo de MDR (sobe com nº de parcelas);
-- o nº de parcelas realmente oferecido ao cliente é sempre
-- min(max_parcelas, valor_total // 5), porque a Cielo exige mínimo de
-- R$ 5,00 por parcela em juros ByMerchant.
CREATE TABLE IF NOT EXISTS config_cartao_produto (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  produto_id          INT           NOT NULL UNIQUE,
  ativo               TINYINT(1)    NOT NULL DEFAULT 1,
  max_parcelas        TINYINT       NOT NULL DEFAULT 1,
  parcelas_sem_juros  TINYINT       NOT NULL DEFAULT 1,
  taxa_juros_mensal   DECIMAL(5,2)  NOT NULL DEFAULT 0.00 COMMENT 'percentual ao mês, ex: 2.99',
  soft_descriptor     VARCHAR(13)   NOT NULL COMMENT 'nome na fatura do cliente',
  criado_em           DATETIME      DEFAULT NOW(),
  atualizado_em       DATETIME      DEFAULT NOW() ON UPDATE NOW(),
  FOREIGN KEY (produto_id) REFERENCES produtos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- pagamento_cartao: auditoria/contestação — 1 linha por TENTATIVA de
-- autorização (não por pedido; um pedido pode ter várias tentativas, ex.
-- negado + tentou outro cartão). Criada ANTES de chamar a Cielo, com
-- payment_id NULL, e completada depois — garante rastro mesmo em timeout.
-- NUNCA gravar CardNumber/SecurityCode crus em request_json.
CREATE TABLE IF NOT EXISTS pagamento_cartao (
  id                  INT AUTO_INCREMENT PRIMARY KEY,
  pedido_id           INT           NOT NULL,
  merchant_order_id   VARCHAR(36)   NOT NULL COMMENT 'sempre = pedido_id em texto',
  payment_id          VARCHAR(36)   NULL COMMENT 'preenchido só se a Cielo respondeu',
  tid                 VARCHAR(50)   NULL,
  authorization_code  VARCHAR(20)   NULL,
  status_cielo        SMALLINT      NULL COMMENT 'Payment.Status — 2=aprovado, 3=negado; NULL=sem resposta',
  return_code         VARCHAR(10)   NULL COMMENT 'técnico — nunca exibir ao cliente',
  return_message      VARCHAR(255)  NULL COMMENT 'técnico — nunca exibir ao cliente',
  categoria_erro      VARCHAR(30)   NULL COMMENT 'recusa_generica | cartao_problema | instabilidade | NULL se aprovado',
  valor_original      DECIMAL(10,2) NOT NULL,
  valor               DECIMAL(10,2) NOT NULL COMMENT 'Amount enviado à Cielo, já com juros embutidos',
  parcelas            TINYINT       NOT NULL,
  bandeira            VARCHAR(20)   NULL,
  cartao_mascarado    VARCHAR(20)   NULL COMMENT 'ex: 999999******9999 — nunca PAN completo',
  nome_titular        VARCHAR(100)  NULL,
  request_json        JSON          NOT NULL COMMENT 'payload enviado, SEM CardNumber/SecurityCode',
  response_json       JSON          NULL COMMENT 'resposta crua da Cielo — já vem com CardNumber mascarado por eles',
  criado_em           DATETIME      DEFAULT NOW(),
  atualizado_em       DATETIME      DEFAULT NOW() ON UPDATE NOW(),
  INDEX idx_pedido (pedido_id),
  FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- pedidos.metodo_pagamento: evita JOIN em todo relatório pra saber o método.
-- Default 'pix': todo pedido pago até hoje (inclusive WhatsApp, estado_id=0)
-- foi via Pix — o DEFAULT do ALTER TABLE retroage pras linhas existentes,
-- nenhum backfill manual é necessário.
SET @col_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME   = 'pedidos'
      AND COLUMN_NAME  = 'metodo_pagamento'
);

SET @sql = IF(@col_exists = 0,
    'ALTER TABLE pedidos ADD COLUMN metodo_pagamento VARCHAR(10) NOT NULL DEFAULT ''pix'' COMMENT ''pix | cartao'' AFTER estado_id',
    'SELECT ''metodo_pagamento ja existe, pulando ALTER''' );

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
