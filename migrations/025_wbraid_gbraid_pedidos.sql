-- Adiciona identificadores de conversão alternativos ao gclid.
-- wbraid: enviado pelo Google Ads para iOS/Safari (ITP) e usuários não logados.
-- gbraid: enviado em conversões app-to-web.
-- Apenas um dos três campos (gclid, wbraid, gbraid) é preenchido por pedido.

ALTER TABLE pedidos
    ADD COLUMN wbraid VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL AFTER gclid,
    ADD COLUMN gbraid VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL AFTER wbraid;
