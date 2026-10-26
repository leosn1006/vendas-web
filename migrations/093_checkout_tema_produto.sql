-- Checkout com a cara da página de origem (26/10/2026): as landings e a Estante são escuras e o checkout era
-- cinza claro com a faixa azul do BB — para a cliente 35+ parecia "saí do site". Agora:
--   produtos.checkout_cor_fundo / checkout_cor_destaque / checkout_marca → moldura escura, botão e destaques
--     na cor do produto e o nome da marca no topo (web/tema_checkout.py). Vazio = checkout claro de sempre.
--   produto_planos.checkout_destaques → "o que você recebe" com ícones logo abaixo do preço (uma linha por item).
--   produto_planos.checkout_texto_botao → texto do botão de finalizar (vazio = "FINALIZAR COMPRA").
-- Idempotente.
SET NAMES utf8mb4;

SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'produtos' AND COLUMN_NAME = 'checkout_cor_fundo');
SET @sql = IF(@tem = 0, 'ALTER TABLE produtos
    ADD COLUMN checkout_cor_fundo VARCHAR(7) NULL COMMENT ''Fundo do checkout (#RRGGBB, o da landing); vazio = checkout claro padrão'',
    ADD COLUMN checkout_cor_destaque VARCHAR(7) NULL COMMENT ''Botão e destaques do checkout (#RRGGBB)'',
    ADD COLUMN checkout_marca VARCHAR(80) NULL COMMENT ''Nome da marca no topo do checkout''', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'produto_planos' AND COLUMN_NAME = 'checkout_destaques');
SET @sql = IF(@tem = 0, 'ALTER TABLE produto_planos
    ADD COLUMN checkout_destaques TEXT NULL COMMENT ''O que ela recebe, abaixo do preço no checkout: uma linha por item, com emoji'',
    ADD COLUMN checkout_texto_botao VARCHAR(60) NULL COMMENT ''Texto do botão de finalizar; vazio = FINALIZAR COMPRA''', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

-- Cores das landings: Música (musica_base.html), Fatia (fatia2-e.html, o "berry") e Tempero (tempero-e.html).
UPDATE produtos SET checkout_cor_fundo = '#0F0E0D', checkout_cor_destaque = '#FB7185', checkout_marca = 'Canção de Presente'
WHERE nome = 'Música de Presente' AND checkout_cor_fundo IS NULL;
UPDATE produtos SET checkout_cor_fundo = '#0F0C0A', checkout_cor_destaque = '#D7473C', checkout_marca = 'Fatia de Bolo'
WHERE id = 12 AND checkout_cor_fundo IS NULL;
UPDATE produtos SET checkout_cor_fundo = '#0C0A09', checkout_cor_destaque = '#10B981', checkout_marca = 'Temperos Caseiros'
WHERE id = 11 AND checkout_cor_fundo IS NULL;

UPDATE produto_planos pp JOIN produtos p ON p.id = pp.produto_id
SET pp.checkout_destaques = CONCAT_WS('\n',
        '🎶 2 versões completas para escolher',
        '📝 Letra escrita com a história de vocês',
        '📥 MP3 para baixar e guardar',
        '📲 Entrega na hora, no seu e-mail (e no WhatsApp, se você informar)'),
    pp.checkout_texto_botao = 'Liberar minha música 🎵'
WHERE p.nome = 'Música de Presente' AND pp.slug = 'musica' AND pp.checkout_destaques IS NULL;

-- O vídeo não sai na hora (ela envia as fotos na área da compra, depois de pagar): a última linha diz isso.
UPDATE produto_planos pp JOIN produtos p ON p.id = pp.produto_id
SET pp.checkout_destaques = CONCAT_WS('\n',
        '🎶 2 versões completas para escolher',
        '📝 Letra escrita com a história de vocês',
        '🎬 Videoclipe com as suas fotos, para o Status e o Instagram',
        '📥 MP3 e vídeo para baixar e guardar',
        '📲 A música chega na hora no seu e-mail; o vídeo, assim que você enviar as fotos'),
    pp.checkout_texto_botao = 'Liberar minha música e o vídeo 🎬'
WHERE p.nome = 'Música de Presente' AND pp.slug = 'videoclipe' AND pp.checkout_destaques IS NULL;

-- Conferência: 3 produtos com cor e o plano da Música com destaques e botão.
SELECT id, nome, checkout_cor_fundo, checkout_cor_destaque, checkout_marca FROM produtos WHERE checkout_cor_fundo IS NOT NULL;
SELECT pp.id, pp.slug, pp.checkout_texto_botao, pp.checkout_destaques FROM produto_planos pp
JOIN produtos p ON p.id = pp.produto_id WHERE p.nome = 'Música de Presente';
