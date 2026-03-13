-- Migration 011: Ação enviar_produto_whatsapp — entrega de produto via WhatsApp Template Message
-- Adiciona suporte a WhatsApp Template Messages no engine de ações dinâmicas.
-- Necessário para fluxos que iniciam conversa pelo sistema (sem message_id de entrada),
-- como confirmacao_web, onde a API exige templates pré-aprovados.

USE vendasdb;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ------------------------------------------------------------
-- 1. Adicionar param1 e param2 para parâmetros configuráveis do template
-- ------------------------------------------------------------
ALTER TABLE acoes_fluxo_produto
    ADD COLUMN param1 VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL
        COMMENT 'Parâmetro 1 do template (ex: nome comercial do produto)',
    ADD COLUMN param2 VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL
        COMMENT 'Parâmetro 2 do template (ex: nome comercial do brinde)';


-- ------------------------------------------------------------
-- 2. Adicionar enviar_produto_whatsapp ao ENUM de acao
-- ------------------------------------------------------------
ALTER TABLE acoes_fluxo_produto
    MODIFY COLUMN acao ENUM(
        'marcar_lida',
        'digitando',
        'enviar_audio',
        'enviar_imagem',
        'enviar_arquivo',
        'enviar_mensagem',
        'enviar_produto_whatsapp'
    ) NOT NULL;


-- ------------------------------------------------------------
-- 3. Atualizar fluxo confirmacao_web do produto 1
--    Novo fluxo:
--      1. enviar_produto_whatsapp (ebook via template — sem digitando, pois não há message_id)
--      2. enviar_arquivo (bônus separado)
-- ------------------------------------------------------------

-- Remove ações antigas: digitando (1), enviar_mensagem (2), enviar_arquivo ebook (3)
DELETE FROM acoes_fluxo_produto
WHERE produto_id = 1 AND fluxo = 'confirmacao_web' AND ordem IN (1, 2, 3);

-- Insere enviar_produto_whatsapp na ordem 1
INSERT INTO acoes_fluxo_produto
    (produto_id, fluxo, ordem, condicao, acao, url, mensagem, caption, nome_arquivo, param1, param2, delay_inicial, delay_final)
SELECT
    1,
    'confirmacao_web',
    1,
    'sempre',
    'enviar_produto_whatsapp',
    p.url_arquivo_produto,
    'entrega_pedido_venda',
    'pt_BR',
    p.nome_arquivo_produto,
    'Pão Sem Glúten Perfeito',
    'Guia Bônus de Receitas',
    0.0,
    0.0
FROM produtos p WHERE p.id = 1;

-- Renumera o bônus (era ordem 4) para ordem 2
UPDATE acoes_fluxo_produto
SET ordem = 2
WHERE produto_id = 1 AND fluxo = 'confirmacao_web' AND ordem = 4;
