-- Imagem com legenda nos fluxos do WhatsApp (09/11/2026).
-- A partir desta versão, em acao = 'enviar_imagem' a coluna `mensagem` é a LEGENDA da imagem (sai na mesma
-- mensagem). Antes ela não era usada nessa ação, mas o admin só ESCONDIA o campo — então uma ação que nasceu
-- como enviar_mensagem e virou enviar_imagem (ou texto digitado antes de escolher a ação) pode ter texto velho
-- guardado, que passaria a sair como legenda no deploy. Limpamos para o deploy não mudar nada do que já roda;
-- a legenda passa a ser preenchida de propósito, no admin.
-- O texto apagado fica guardado em backup_102_legenda_imagem (pode ser descartada depois de conferida).
-- Idempotente.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS backup_102_legenda_imagem (
    acao_id    INT          NOT NULL PRIMARY KEY,
    produto_id INT          NOT NULL,
    fluxo      VARCHAR(100) NOT NULL,
    mensagem   TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    criado_em  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Marcador acao_id = 0: gravado no fim. Se a migration rodar de novo (já com legendas preenchidas de
-- propósito no admin), o marcador existe e nada é copiado nem limpo.
INSERT IGNORE INTO backup_102_legenda_imagem (acao_id, produto_id, fluxo, mensagem)
SELECT a.id, a.produto_id, a.fluxo, a.mensagem
FROM acoes_fluxo_produto a
WHERE a.acao = 'enviar_imagem' AND a.mensagem IS NOT NULL AND a.mensagem <> ''
  AND NOT EXISTS (SELECT 1 FROM (SELECT acao_id FROM backup_102_legenda_imagem WHERE acao_id = 0) m);

UPDATE acoes_fluxo_produto a
JOIN backup_102_legenda_imagem b ON b.acao_id = a.id AND b.mensagem = a.mensagem
SET a.mensagem = NULL
WHERE a.acao = 'enviar_imagem'
  AND NOT EXISTS (SELECT 1 FROM (SELECT acao_id FROM backup_102_legenda_imagem WHERE acao_id = 0) m);

INSERT IGNORE INTO backup_102_legenda_imagem (acao_id, produto_id, fluxo, mensagem)
VALUES (0, 0, '_marcador', 'migration 102 aplicada');
