-- Limites de e-mail disparado pela cliente no site (09/11/2026, docs/CONTRIBUICAO_WEB.md).
-- Uma linha por e-mail que a própria cliente provoca: o "Reenviar o e-mail" da Estante 2 e o "seu livro chegou" da
-- entrega da contribuição (e-mail digitado na hora, sem verificação). Os limites (database.LIMITES_ENVIO_EMAIL)
-- protegem a cota de envio do Gmail do admin@: um disparo em massa faria o Google limitar a conta e parar as entregas
-- de todos os produtos. Idempotente.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS envios_email_site (
    id         INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    tipo       VARCHAR(30) NOT NULL COMMENT 'reenvio_estante | entrega_contribuicao',
    pedido_id  INT NOT NULL COMMENT 'O e-mail vai para pedidos.email deste pedido',
    ip         VARCHAR(45) NULL COMMENT 'IP de quem provocou o envio (X-Real-IP do nginx)',
    criado_em  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_envio_pedido (tipo, pedido_id, criado_em),
    KEY idx_envio_ip (tipo, ip, criado_em),
    KEY idx_envio_criado (tipo, criado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
