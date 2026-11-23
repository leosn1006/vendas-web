-- Migration 109: webhook da Hotmart (checkout de fora do Brasil, começa pela Música do México). Ver docs/HOTMART.md.
--
-- O pedido continua o nosso (criado antes de mandar a cliente para a Hotmart, com xcod = guid do pedido); a Hotmart
-- avisa por webhook e o pedido vai para o 1000 (pago via web) como no PIX e no cartão — com valor_pago,
-- valor_liquido_pagamento e data_repasse em REAIS, para ROI, Financeiro e Ads não mudarem. O que é só da Hotmart
-- (moeda original, comissão, situação, previsão de repasse) fica nas tabelas abaixo.
-- Idempotente.

SET NAMES utf8mb4;

INSERT IGNORE INTO estado_pedidos (id, descricao) VALUES
    (1010, 'Aguardando pagamento Hotmart (OXXO/SPEI)'),
    (1011, 'Hotmart: compra cancelada/expirada');

-- De-para oferta da Hotmart → plano nosso. Um plano pode ter mais de uma oferta (ex.: videoclipe cheio e com o
-- desconto do popup). O webhook só confirma o pedido se a oferta paga for de um plano igual ao do pedido.
CREATE TABLE IF NOT EXISTS hotmart_ofertas (
  codigo       VARCHAR(40)   NOT NULL PRIMARY KEY COMMENT 'código da oferta na Hotmart (off=...)',
  produto_id   INT           NOT NULL,
  plano_id     INT           NOT NULL,
  descricao    VARCHAR(120)  NULL,
  ativo        TINYINT(1)    NOT NULL DEFAULT 1,
  criado_em    DATETIME      DEFAULT NOW(),
  INDEX idx_hotmart_ofertas_plano (plano_id),
  FOREIGN KEY (produto_id) REFERENCES produtos(id),
  FOREIGN KEY (plano_id) REFERENCES produto_planos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Uma linha por compra da Hotmart (transação), com a última situação. Valores sempre com a moeda ao lado.
CREATE TABLE IF NOT EXISTS pagamento_hotmart (
  id                   INT AUTO_INCREMENT PRIMARY KEY,
  transacao            VARCHAR(40)   NOT NULL UNIQUE COMMENT 'purchase.transaction, ex.: HP17715690036014',
  pedido_id            INT           NULL COMMENT 'NULL = órfão (sem xcod ou guid desconhecido): conferir à mão',
  produto_id_hotmart   BIGINT        NULL,
  oferta               VARCHAR(40)   NULL,
  status               VARCHAR(30)   NULL COMMENT 'purchase.status da Hotmart',
  ultimo_evento        VARCHAR(40)   NULL,
  tipo_pagamento       VARCHAR(30)   NULL COMMENT 'purchase.payment.type (CREDIT_CARD, CASH_PAYMENT...)',
  pais                 CHAR(2)       NULL,
  email_comprador      VARCHAR(150)  NULL,
  valor                DECIMAL(12,2) NULL COMMENT 'purchase.price, na moeda da cliente',
  moeda                CHAR(3)       NULL,
  valor_cheio          DECIMAL(12,2) NULL COMMENT 'purchase.full_price',
  taxa_hotmart         DECIMAL(12,2) NULL COMMENT 'commissions[MARKETPLACE] — pode não vir (a doc lista só PRODUCER/COPRODUCER/AFFILIATE/ADDON)',
  moeda_taxa           CHAR(3)       NULL,
  liquido              DECIMAL(12,2) NULL COMMENT 'commissions[PRODUCER]: o que é nosso',
  moeda_liquido        CHAR(3)       NULL,
  taxa_brl             DECIMAL(14,6) NULL COMMENT 'reais por 1 unidade da moeda da cliente',
  fonte_taxa           VARCHAR(10)   NULL COMMENT 'brl | hotmart | ptax | bce | ultima | pendente',
  valor_brl            DECIMAL(10,2) NULL,
  liquido_brl          DECIMAL(10,2) NULL,
  order_bump           TINYINT(1)    NOT NULL DEFAULT 0,
  transacao_principal  VARCHAR(40)   NULL,
  nota_fiscal_por      VARCHAR(10)   NULL COMMENT 'purchase.invoice_by: HOTMART | SELLER (quem emite a nota)',
  modelo_fiscal        CHAR(1)       NULL COMMENT 'purchase.business_model: R (Hotmart emite) | A (nós, pela Hotmart no exterior) | I (nós, pela Hotmart no Brasil)',
  aprovado_em          DATETIME      NULL,
  garantia_ate         DATETIME      NULL,
  previsao_repasse     DATE          NULL COMMENT 'estimativa: aprovação + HOTMART_DIAS_REPASSE (ou a garantia)',
  liberado_em          DATETIME      NULL COMMENT 'chegou o PURCHASE_COMPLETE (fim da garantia)',
  criado_em            DATETIME      DEFAULT NOW(),
  atualizado_em        DATETIME      DEFAULT NOW() ON UPDATE NOW(),
  INDEX idx_pagamento_hotmart_pedido (pedido_id),
  INDEX idx_pagamento_hotmart_aprovado (aprovado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Todo aviso recebido, cru (o evento_id UNIQUE evita processar duas vezes o mesmo aviso).
CREATE TABLE IF NOT EXISTS pagamento_hotmart_eventos (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  evento_id    VARCHAR(64)   NOT NULL UNIQUE,
  transacao    VARCHAR(40)   NULL,
  evento       VARCHAR(40)   NULL,
  payload      JSON          NOT NULL,
  resultado    VARCHAR(20)   NULL COMMENT 'processando | ok | ignorado | oferta_divergente | sem_pedido | erro',
  detalhe      VARCHAR(255)  NULL,
  recebido_em  DATETIME      DEFAULT NOW(),
  INDEX idx_hotmart_eventos_transacao (transacao),
  INDEX idx_hotmart_eventos_resultado (resultado)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE pedidos MODIFY COLUMN metodo_pagamento VARCHAR(10) NOT NULL DEFAULT 'pix' COMMENT 'pix | cartao | hotmart';
