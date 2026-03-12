-- Migration 010: Integração do fluxo de venda web com o fluxo WhatsApp
-- O checkout web passa a criar pedidos na tabela `pedidos` (unificada),
-- usando estados 1000/1001/1002 para não conflitar com os estados WhatsApp (0-4).
-- Após pagamento confirmado, a entrega do ebook é feita via WhatsApp
-- usando o mesmo engine de ações (_executar_acao) já existente.

USE vendasdb;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ------------------------------------------------------------
-- 1. Novos estados web em estado_pedidos
-- ------------------------------------------------------------
INSERT IGNORE INTO estado_pedidos (id, descricao) VALUES
    (1000, 'Pago via web'),
    (1001, 'Pedido web criado'),
    (1002, 'Aguardando pagamento BB Pay');


-- ------------------------------------------------------------
-- 2. Novas colunas em `produtos` para habilitar venda web
-- ------------------------------------------------------------
ALTER TABLE produtos
    ADD COLUMN numero_convenio_bb BIGINT NULL
        COMMENT 'Número do convênio BB Pay para este produto (somente para produtos web)',
    ADD COLUMN disponivel_web BOOLEAN NOT NULL DEFAULT FALSE
        COMMENT 'Se TRUE, o produto pode ser vendido pelo checkout web';


-- ------------------------------------------------------------
-- 3. Novas colunas em `pedidos` para o fluxo web
-- ------------------------------------------------------------
ALTER TABLE pedidos
    ADD COLUMN email VARCHAR(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL
        COMMENT 'E-mail do cliente (capturado no checkout web)',
    ADD COLUMN numero_solicitacao_bb VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL
        COMMENT 'ID da solicitação BB Pay (txid)',
    ADD COLUMN url_bbpay VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL
        COMMENT 'URL de pagamento gerada pelo BB Pay',
    ADD COLUMN qr_code_pix TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL
        COMMENT 'Texto EMV do QR code PIX (permite reexibir sem nova chamada ao BB Pay)',
    ADD COLUMN expiracao_solicitacao_bb DATETIME NULL
        COMMENT 'Momento de expiração da solicitação BB Pay (padrão: 24h após criação)',
    ADD COLUMN data_envio_ebook DATETIME NULL
        COMMENT 'Preenchido após envio bem-sucedido do ebook via WhatsApp',
    ADD INDEX idx_pedidos_solicitacao_bb (numero_solicitacao_bb);


-- ------------------------------------------------------------
-- 4. Adicionar 'confirmacao_web' ao ENUM de acoes_fluxo_produto
-- ------------------------------------------------------------
ALTER TABLE acoes_fluxo_produto
    MODIFY COLUMN fluxo ENUM(
        'introducao',
        'pedido',
        'comprovante',
        'responder',
        'followup',
        'confirmacao_web'
    ) NOT NULL;


-- ------------------------------------------------------------
-- 5. Habilitar produto 1 para venda web (migrar dados de produto_web)
-- ------------------------------------------------------------
UPDATE produtos
SET
    numero_convenio_bb = 275513,
    disponivel_web     = TRUE
WHERE id = 1;


-- ------------------------------------------------------------
-- 6. Seed: ações do fluxo confirmacao_web para o produto 1
--    Sequência: digitando → mensagem boas-vindas → ebook principal → bônus
--    Não inclui marcar_lida pois não há mensagem de entrada neste fluxo.
-- ------------------------------------------------------------
INSERT IGNORE INTO acoes_fluxo_produto
    (produto_id, fluxo, ordem, condicao, acao, url, mensagem, caption, nome_arquivo, delay_inicial, delay_final)
VALUES
    (1, 'confirmacao_web', 1, 'sempre', 'digitando',       NULL, NULL, NULL, NULL, 2.0, 4.0),
    (1, 'confirmacao_web', 2, 'sempre', 'enviar_mensagem', NULL,
        'Olá! Seu pagamento foi confirmado 🎉 Aqui está seu ebook, é só clicar para baixar ⬇',
        NULL, NULL, 0.0, 0.0),
    (1, 'confirmacao_web', 3, 'sempre', 'enviar_arquivo',  NULL, NULL, NULL, NULL, 0.0, 0.0),
    (1, 'confirmacao_web', 4, 'sempre', 'enviar_arquivo',  NULL, NULL, NULL, NULL, 3.0, 5.0);

-- Preenche o ebook principal (ordem 3) a partir de produtos
UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET
    afp.url          = p.url_arquivo_produto,
    afp.caption      = p.caption_arquivo_produto,
    afp.nome_arquivo = p.nome_arquivo_produto
WHERE afp.produto_id = 1 AND afp.fluxo = 'confirmacao_web' AND afp.ordem = 3;

-- Preenche o bônus (ordem 4) a partir de produtos
UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET
    afp.url          = p.url_arquivo_surpresa,
    afp.caption      = p.caption_arquivo_surpresa,
    afp.nome_arquivo = p.nome_arquivo_surpresa
WHERE afp.produto_id = 1 AND afp.fluxo = 'confirmacao_web' AND afp.ordem = 4;
