-- Integração NF-e Modelo 55 — SVRS/DF
-- pagamento_pix.nfe_emitida_id: NULL = NF-e pendente, NOT NULL = NF-e gerada
-- Sem FK constraint aqui para evitar referência circular com nfe_emitidas
ALTER TABLE pagamento_pix
  ADD COLUMN nfe_emitida_id INT NULL,
  ADD INDEX idx_nfe_pendente (nfe_emitida_id);

-- Configuração do emitente (multi-tenant: 1 linha por CNPJ)
-- Hoje: 1 registro (a própria empresa). No futuro: 1 por cliente do serviço.
CREATE TABLE nfe_configuracao (
  id                    INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  tenant_slug           VARCHAR(50)  NOT NULL UNIQUE,
  api_key               CHAR(64)     NOT NULL UNIQUE,
  cnpj                  CHAR(14)     NOT NULL,
  ie                    VARCHAR(14)  NULL,
  crt                   TINYINT      NOT NULL DEFAULT 3,        -- 3 = Lucro Presumido
  razao_social          VARCHAR(60)  NOT NULL,
  nome_fantasia         VARCHAR(60)  NULL,
  logradouro            VARCHAR(60)  NOT NULL,
  numero                VARCHAR(60)  NOT NULL,
  complemento           VARCHAR(60)  NULL,
  bairro                VARCHAR(60)  NOT NULL,
  c_mun                 INT          NOT NULL,                  -- IBGE (Brasília = 5300108)
  x_mun                 VARCHAR(60)  NOT NULL,
  uf                    CHAR(2)      NOT NULL DEFAULT 'DF',
  cep                   CHAR(8)      NOT NULL,
  fone                  VARCHAR(15)  NULL,
  email                 VARCHAR(60)  NULL,
  serie_padrao          CHAR(3)      NOT NULL DEFAULT '001',
  ultimo_numero_nfe     INT          NOT NULL DEFAULT 0,
  certificado_path      VARCHAR(255) NOT NULL,
  certificado_senha_env VARCHAR(100) NOT NULL,                  -- nome da env var, nunca a senha
  x_prod                VARCHAR(120) NOT NULL DEFAULT 'Livro Digital',
  ncm                   VARCHAR(8)   NULL,                      -- definir com contador
  cfop                  VARCHAR(4)   NULL,                      -- definir com contador
  cst_icms              VARCHAR(3)   NULL,
  cst_pis               VARCHAR(2)   NULL,
  cst_cofins            VARCHAR(2)   NULL,
  ambiente              TINYINT      NOT NULL DEFAULT 2,        -- 1=produção, 2=homologação
  ativo                 TINYINT      NOT NULL DEFAULT 1,
  criado_em             DATETIME     DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- NF-e emitidas — uma por pagamento PIX (UNIQUE em pagamento_pix_id)
CREATE TABLE nfe_emitidas (
  id                INT     NOT NULL AUTO_INCREMENT PRIMARY KEY,
  tenant_id         INT     NOT NULL,
  pagamento_pix_id  INT     NOT NULL,
  external_ref      VARCHAR(100) NULL,                          -- referência do sistema cliente externo
  chave_acesso      CHAR(44)     UNIQUE,
  numero            VARCHAR(9)   NULL,
  serie             CHAR(3)      NULL,
  ambiente          TINYINT      NULL,
  c_stat            VARCHAR(3)   NULL,
  x_motivo          TEXT         NULL,
  n_prot            VARCHAR(15)  NULL,
  dh_recbto         DATETIME     NULL,
  n_rec             VARCHAR(15)  NULL,                          -- recibo para NfeRetAutorizacao (cStat=103)
  xml_assinado      LONGTEXT     NULL,
  xml_nfe_proc      LONGTEXT     NULL,
  status_emissao    ENUM('pendente','enviando','autorizada','rejeitada','cancelada','erro')
                    NOT NULL DEFAULT 'pendente',
  tentativas        TINYINT      NOT NULL DEFAULT 0,
  ultimo_erro       TEXT         NULL,
  criado_em         DATETIME     DEFAULT CURRENT_TIMESTAMP,
  atualizado_em     DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (tenant_id) REFERENCES nfe_configuracao(id),
  UNIQUE KEY uq_pagamento_pix (pagamento_pix_id),
  INDEX idx_tenant   (tenant_id),
  INDEX idx_status   (status_emissao),
  INDEX idx_ext_ref  (tenant_id, external_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Log de comunicação SOAP com a SEFAZ (sem senha do certificado)
CREATE TABLE nfe_log_comunicacao (
  id            INT     NOT NULL AUTO_INCREMENT PRIMARY KEY,
  nfe_id        INT     NOT NULL,
  operacao      VARCHAR(50)  NULL,  -- status_servico, autorizacao, ret_autorizacao, consulta
  url           VARCHAR(255) NULL,
  soap_request  LONGTEXT     NULL,
  soap_response LONGTEXT     NULL,
  status_http   SMALLINT     NULL,
  duracao_ms    INT          NULL,
  criado_em     DATETIME     DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (nfe_id) REFERENCES nfe_emitidas(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
