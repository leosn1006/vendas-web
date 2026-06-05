-- Índice em campanhas(campaignid) para lookup rápido por campaignid sem produto_id
ALTER TABLE campanhas ADD INDEX idx_campaignid (campaignid);
