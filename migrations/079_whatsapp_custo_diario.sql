-- Custo das mensagens da API oficial da Meta (cobrança por mensagem desde 01/10/2026), lido do
-- pricing_analytics de cada WABA pela task tasks.coletar_custo_whatsapp (a cada 30 min o dia D,
-- às 05h55 o fechamento do D-1). Valor e moeda ficam como a Meta devolve (USD ou BRL, conforme a
-- WABA) — a conversão para Real é só na tela (app/cotacao.py).
-- produto_id fica FORA da chave de propósito: a Meta devolve o total acumulado do dia por número,
-- então se o número trocar de produto a próxima coleta criaria outra linha do mesmo dia e o custo
-- seria contado em dobro. O produto é gravado na 1ª coleta do dia e o upsert nunca o sobrescreve.
CREATE TABLE IF NOT EXISTS whatsapp_custo_diario (
    data              DATE          NOT NULL COMMENT 'Dia em horário de Brasília (fuso da WABA)',
    telefone          VARCHAR(20)   NOT NULL COMMENT 'Número como a Meta devolve (= telefones_produto.telefone)',
    pricing_category  VARCHAR(30)   NOT NULL COMMENT 'SERVICE, MARKETING, UTILITY, AUTHENTICATION...',
    produto_id        INT           NOT NULL COMMENT 'Dono do número na 1ª coleta do dia; não muda depois',
    waba_id           VARCHAR(50)   NOT NULL,
    moeda             CHAR(3)       NOT NULL COMMENT 'Moeda da WABA (USD/BRL)',
    custo             DECIMAL(12,4) NOT NULL DEFAULT 0,
    msgs_cobradas     INT           NOT NULL DEFAULT 0 COMMENT 'pricing_type REGULAR',
    msgs_gratis       INT           NOT NULL DEFAULT 0 COMMENT 'pricing_type FREE_*',
    fonte             ENUM('intradia','fechamento') NOT NULL COMMENT 'intradia = parcial do dia; fechamento = releitura do D-1',
    atualizado_em     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (data, telefone, pricing_category),
    KEY idx_whatsapp_custo_produto_data (produto_id, data)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
