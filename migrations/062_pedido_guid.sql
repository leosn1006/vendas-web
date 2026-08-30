-- Migration 062: guid curto e não-sequencial para o link público de acompanhamento do pedido
-- web (/pedido/<guid>) — permite ao cliente ver os itens do pedido pago e ler os e-books
-- direto no navegador, sem login. Mesmo modelo de confiança que o link/QR code do BB Pay PIX
-- já usa hoje: posse do link é a autorização.
--
-- Nullable: pedidos antigos ficam com guid NULL pra sempre (nunca são retroativamente
-- atualizados por código, só por script de backfill pontual — ver
-- scripts/backfill_pedido_guid_itens.py). Pedidos novos sempre recebem guid na criação, nos
-- três pontos de criação de pedido: `criar_pedido` (fluxo WhatsApp) e
-- `criar_pedido_web_inicial`/`criar_pedido_web_unificado` (fluxo web).
--
-- IMPORTANTE — collation: a tabela `pedidos` usa utf8mb4_unicode_ci (case-INSENSITIVE) por
-- padrão. Um token gerado com secrets.token_urlsafe() é case-sensitive (mistura maiúsculas e
-- minúsculas no alfabeto base64 URL-safe). Sob uma collation case-insensitive, dois guids
-- diferentes só na caixa colidiriam na UNIQUE KEY e, pior, um WHERE guid = %s poderia casar com
-- a linha de OUTRO pedido — vazamento real de pedido pago de terceiro, não só um bug cosmético.
-- Por isso a coluna é declarada explicitamente com charset/collation binário-ascii,
-- independente da collation default da tabela.
ALTER TABLE pedidos
    ADD COLUMN guid VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER id,
    ADD UNIQUE KEY uk_pedidos_guid (guid);
