-- Migration 048: adiciona colunas de parametrizacao fiscal a nfe_configuracao
-- c_benef ja existe; adiciona apenas as colunas que faltam

ALTER TABLE nfe_configuracao
    ADD COLUMN nat_op          VARCHAR(60)  NULL AFTER c_benef,
    ADD COLUMN aliq_icms_deson DECIMAL(5,4) NULL AFTER nat_op,
    ADD COLUMN mot_des_icms    CHAR(2)      NULL AFTER aliq_icms_deson,
    ADD COLUMN cst_ibs_cbs     VARCHAR(3)   NULL AFTER mot_des_icms,
    ADD COLUMN c_class_trib    VARCHAR(10)  NULL AFTER cst_ibs_cbs,
    ADD COLUMN ca_bundle_path  VARCHAR(255) NULL AFTER c_class_trib;

-- Popula os valores atuais (que eram hardcoded no XML builder)

UPDATE nfe_configuracao SET
    nat_op          = 'VENDA DE PRODUTO DIGITAL',
    aliq_icms_deson = 0.1200,
    mot_des_icms    = '90',
    cst_ibs_cbs     = '410',
    c_class_trib    = '410009'
WHERE tenant_slug = 'lsn-livros';

UPDATE nfe_configuracao SET
    c_benef         = 'DF811004',
    nat_op          = 'VENDA DE PRODUTO DIGITAL',
    aliq_icms_deson = 0.1200,
    mot_des_icms    = '90',
    cst_ibs_cbs     = '410',
    c_class_trib    = '410009'
WHERE tenant_slug = 'lbe-livros';
