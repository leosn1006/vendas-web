-- Migration 072: registra cada rodada da rotina diária de NF-e (tasks.emitir_nfe_diaria_lbe)
-- para exibir um relatório consolidado no admin (/admin/fiscal/nfe/execucoes), sem depender
-- de vasculhar log linha a linha.

CREATE TABLE nfe_execucoes (
  id                      INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  tenant_id               INT NOT NULL,
  iniciado_em             DATETIME NOT NULL,
  finalizado_em           DATETIME NULL,
  pix_elegiveis           INT NOT NULL DEFAULT 0,
  pix_disparados          INT NOT NULL DEFAULT 0,
  pix_limite_atingido     TINYINT NOT NULL DEFAULT 0,
  cartao_elegiveis        INT NOT NULL DEFAULT 0,
  cartao_disparados       INT NOT NULL DEFAULT 0,
  cartao_limite_atingido  TINYINT NOT NULL DEFAULT 0,
  qtd_autorizada_100      INT NULL,
  qtd_autorizada_150      INT NULL,
  qtd_rejeitada           INT NULL,
  qtd_erro                INT NULL,
  qtd_ja_emitida          INT NULL,
  valor_total_autorizado  DECIMAL(10,2) NULL,
  ultimo_numero_nfe_final INT NULL,
  detalhe_rejeicoes_json  TEXT NULL,
  status                  ENUM('em_andamento', 'concluido', 'erro') NOT NULL DEFAULT 'em_andamento',
  FOREIGN KEY (tenant_id) REFERENCES nfe_configuracao(id),
  INDEX idx_tenant_data (tenant_id, iniciado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
