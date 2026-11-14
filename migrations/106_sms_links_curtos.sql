-- SMS (Comtele) e link curto, genéricos para o sistema todo; o primeiro uso são os lembretes da Música (14/11/2026,
-- docs/SMS.md). Idempotente.
SET NAMES utf8mb4;

-- Link curto /m/<codigo>: 7 caracteres, maiúscula ≠ minúscula (por isso o código em utf8mb4_bin).
CREATE TABLE IF NOT EXISTS links_curtos (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    codigo             VARCHAR(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    url_destino        VARCHAR(1000) COLLATE utf8mb4_unicode_ci NOT NULL,
    origem             VARCHAR(40) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Quem criou, ex.: musica_lembrete',
    ref_tipo           VARCHAR(20) COLLATE utf8mb4_unicode_ci NULL COMMENT 'musica | pedido | ...',
    ref_id             INT NULL,
    criado_em          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_em          DATETIME NULL COMMENT 'NULL = não expira',
    cliques_humanos    INT NOT NULL DEFAULT 0 COMMENT 'Sem robôs (pré-visualização, verificador de e-mail)',
    primeiro_clique_em DATETIME NULL,
    UNIQUE KEY uq_links_curtos_codigo (codigo),
    KEY idx_links_curtos_ref (ref_tipo, ref_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Cada acesso a /m/<codigo>, existente ou não, para avaliar o risco de alguém chutar códigos. IP é dado pessoal:
-- apagado depois de 90 dias (links_curtos.limpar_acessos, na limpeza diária).
CREATE TABLE IF NOT EXISTS links_curtos_acessos (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    codigo_tentado     VARCHAR(40) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    link_id            INT NULL COMMENT 'NULL = código inexistente ou expirado',
    ip                 VARCHAR(45) COLLATE utf8mb4_unicode_ci NULL,
    user_agent         VARCHAR(300) COLLATE utf8mb4_unicode_ci NULL,
    robo               TINYINT(1) NOT NULL DEFAULT 0,
    criado_em          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_links_curtos_acessos_criado (criado_em),
    KEY idx_links_curtos_acessos_link (link_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sms_envios (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    produto_id         INT NULL,
    origem             VARCHAR(40) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'ex.: musica_lembrete',
    etapa              VARCHAR(20) COLLATE utf8mb4_unicode_ci NULL COMMENT 'Detalhe da origem, ex.: previa 1',
    ref_tipo           VARCHAR(20) COLLATE utf8mb4_unicode_ci NULL COMMENT 'musica | pedido | ...',
    ref_id             INT NULL,
    telefone           VARCHAR(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Com DDI, só dígitos',
    texto              VARCHAR(480) COLLATE utf8mb4_unicode_ci NOT NULL,
    partes             TINYINT NOT NULL DEFAULT 1,
    link_id            INT NULL COMMENT 'links_curtos: o clique vem de lá',
    status             VARCHAR(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pendente'
        COMMENT 'pendente | enviando | enviado | entregue | falhou | ignorado_dev',
    provedor           VARCHAR(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'comtele',
    provedor_id        VARCHAR(64) COLLATE utf8mb4_unicode_ci NULL COMMENT 'requestId da Comtele',
    erro               VARCHAR(500) COLLATE utf8mb4_unicode_ci NULL,
    criado_em          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    enviado_em         DATETIME NULL,
    entregue_em        DATETIME NULL,
    KEY idx_sms_envios_ref (ref_tipo, ref_id),
    KEY idx_sms_envios_produto (produto_id, criado_em),
    KEY idx_sms_envios_telefone (telefone, criado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
