-- Migration 059: cache de bandeira por BIN (6 primeiros dígitos do cartão),
-- alimentado pela Consulta BIN da Cielo (GET /1/cardBin/{BIN}).
--
-- Cache-aside sem expiração: BIN reatribuído de bandeira é raríssimo. Se um
-- dia acontecer, a correção é um DELETE manual na linha pra forçar nova
-- consulta na próxima vez que esse BIN aparecer.
--
-- bandeira = NULL é um resultado válido de cache: significa que a Cielo
-- respondeu, mas a bandeira não é uma das que temos ícone (visa/mastercard/
-- elo/amex/hipercard) — evita bater na Cielo de novo pro mesmo BIN.
CREATE TABLE IF NOT EXISTS bandeira_bin (
  bin            VARCHAR(6)   NOT NULL PRIMARY KEY,
  bandeira       VARCHAR(20)  NULL COMMENT 'visa|mastercard|elo|amex|hipercard — NULL se não é bandeira com ícone',
  card_type      VARCHAR(20)  NULL COMMENT 'Payment.CardType da Cielo: Crédito | Débito | Múltiplo',
  issuer         VARCHAR(100) NULL,
  foreign_card   TINYINT(1)   NULL,
  corporate_card TINYINT(1)   NULL,
  prepaid        TINYINT(1)   NULL,
  criado_em      DATETIME     DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
