-- Migration 051: Variantes de conteúdo por passo de fluxo (anti-padrão-repetitivo)
-- Hoje todo cliente recebe o texto/áudio/arquivo idêntico em cada passo de cada
-- fluxo, o que cria um padrão repetitivo no número emissor que pode contribuir
-- para detecção de SPAM/automação pela Meta. Esta migration permite cadastrar
-- múltiplas variantes de conteúdo para o mesmo passo (produto_id+fluxo+condicao+
-- ordem) e adiciona um cursor de rodízio por número emissor (phone_number_id),
-- que guarda apenas a última variante enviada em cada passo — não um histórico
-- completo — para escolher a próxima em ordem cíclica (1→2→3→...→1).

USE vendasdb;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ------------------------------------------------------------
-- 1. Coluna 'variante' em acoes_fluxo_produto
--    Default 1 preserva automaticamente todas as linhas existentes.
-- ------------------------------------------------------------
ALTER TABLE acoes_fluxo_produto
    ADD COLUMN variante SMALLINT UNSIGNED NOT NULL DEFAULT 1
        COMMENT 'Número da variante de conteúdo para este passo. 1=única/padrão.'
        AFTER condicao;


-- ------------------------------------------------------------
-- 2. Troca a UNIQUE KEY para incluir 'variante'
--    Agora várias linhas podem coexistir no mesmo passo, desde que
--    com 'variante' diferente.
-- ------------------------------------------------------------
ALTER TABLE acoes_fluxo_produto
    DROP INDEX uk_afp,
    ADD UNIQUE KEY uk_afp (produto_id, fluxo, condicao, ordem, variante);


-- ------------------------------------------------------------
-- 3. Cursor de rodízio de variantes por número emissor + passo
--    1 linha fixa por (phone_number_id, produto_id, fluxo, condicao, ordem),
--    guardando só a última variante enviada — não um log que cresce a cada
--    envio. O risco de detecção de padrão é sobre o número que ENVIA, não
--    sobre o cliente que recebe, por isso o rodízio é por phone_number_id.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS variantes_fluxo_cursor (
    phone_number_id VARCHAR(20)  NOT NULL COMMENT 'Nosso número emissor (WhatsApp Business)',
    produto_id      INT          NOT NULL,
    fluxo           ENUM('introducao','pedido','comprovante','responder','followup',
                          'confirmacao_web','followup_interesse_1','followup_interesse_2')
                    NOT NULL,
    condicao        ENUM('sempre','interesse_sim','interesse_nao','pagamento_valido','pagamento_invalido')
                    NOT NULL DEFAULT 'sempre',
    ordem           TINYINT UNSIGNED NOT NULL,
    ultima_variante SMALLINT UNSIGNED NOT NULL,
    acao_id         INT NULL COMMENT 'Última linha de acoes_fluxo_produto enviada; referência informativa',
    atualizado_em   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (phone_number_id, produto_id, fluxo, condicao, ordem),
    CONSTRAINT fk_vfc_produto FOREIGN KEY (produto_id) REFERENCES produtos(id),
    CONSTRAINT fk_vfc_acao    FOREIGN KEY (acao_id) REFERENCES acoes_fluxo_produto(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Cursor de rodízio de variantes por número emissor+passo — guarda só a última variante enviada (não histórico), tamanho limitado ao nº de combinações número×passo';
