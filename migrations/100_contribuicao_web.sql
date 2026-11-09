-- Venda "entrega antes, contribuição depois" no site (08/11/2026, docs/CONTRIBUICAO_WEB.md).
-- A/B na landing do WhatsApp: no clique em "Quero receber", parte das clientes fica no site — informa o nome,
-- ouve o áudio da persona, informa o e-mail e recebe o livro na Estante 2 antes de pagar; o pagamento
-- ("contribuição") é uma venda normal do checkout v2 (/pay2?ref=<guid>), que libera os bônus.
--   estado 1008 = clicou em "Quero receber" (ainda sem e-mail, nada entregue)
--   estado 1009 = livro entregue, aguardando contribuição (a Estante abre o principal; bônus com cadeado)
--   contribuicao_config  = liga/desliga e configura por produto (percentual do A/B, persona, áudios, textos)
--   contribuicao_pedidos = uma linha por clique nos DOIS braços (wpp e estante) + marcos do funil e lembretes
-- Sai com o teste desligado (percentual_estante = 0). Idempotente.
SET NAMES utf8mb4;

INSERT IGNORE INTO estado_pedidos (id, descricao) VALUES
    (1008, 'Contribuição: clicou em Quero receber'),
    (1009, 'Contribuição: livro entregue, aguardando contribuição');

CREATE TABLE IF NOT EXISTS contribuicao_config (
    produto_id          INT NOT NULL PRIMARY KEY,
    ativo               TINYINT(1) NOT NULL DEFAULT 1 COMMENT '0 = teste desligado (todo mundo vai pro WhatsApp)',
    percentual_estante  TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0-100: parte dos cliques que fica no site (braço estante)',
    persona_nome        VARCHAR(60)  NOT NULL COMMENT 'Quem fala com a cliente (ex.: Luiza)',
    persona_foto        VARCHAR(200) NULL COMMENT 'Caminho em /static (ex.: images/luiza.jpg)',
    audio_intro         VARCHAR(200) NOT NULL COMMENT 'Áudio 1, tela de chegada (caminho em /static, mp3; nome versionado: cache immutable)',
    audio_cobranca      VARCHAR(200) NOT NULL COMMENT 'Áudio 2, na Estante: entrega + pedido de contribuição',
    audio_lembrete      VARCHAR(200) NULL COMMENT 'Áudio 3, na Estante quando ela volta pelo e-mail de lembrete',
    audio_agradecimento VARCHAR(200) NULL COMMENT 'Áudio 4 (opcional), depois de pagar',
    texto_intro         TEXT NULL COMMENT 'Transcrição do áudio 1 (botão "ler em vez de ouvir")',
    texto_cobranca      TEXT NULL COMMENT 'Transcrição do áudio 2',
    texto_lembrete      TEXT NULL COMMENT 'Transcrição do áudio 3',
    checklist           TEXT NULL COMMENT 'O que vem no livro, uma linha por item (tela de chegada)',
    lembrete1_minutos   INT NOT NULL DEFAULT 120 COMMENT 'Primeiro e-mail de lembrete, minutos depois do e-mail informado',
    lembrete2_minutos   INT NOT NULL DEFAULT 1440 COMMENT 'Segundo e-mail de lembrete',
    atualizado_em       TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contribuicao_pedidos (
    pedido_id       INT NOT NULL PRIMARY KEY COMMENT 'Pedido do clique (braço wpp: o lead estado 1; braço estante: 1008/1009)',
    produto_id      INT NOT NULL,
    braco           ENUM('wpp','estante') NOT NULL COMMENT 'Braço sorteado no clique',
    teste           TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = forçado por ?contrib= (QA), fora da análise',
    cliques         INT NOT NULL DEFAULT 1 COMMENT 'Cliques em Quero receber (braço estante: repetidos no mesmo aparelho somam aqui; wpp: 1 por lead)',
    criado_em       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'O clique em Quero receber',
    nome_em         DATETIME NULL COMMENT 'Informou o nome',
    audio1_play_em  DATETIME NULL COMMENT 'Começou a ouvir o áudio 1',
    audio1_fim_em   DATETIME NULL COMMENT 'Ouviu o áudio 1 até o fim',
    email_em        DATETIME NULL COMMENT 'Informou o e-mail = livro entregue (estado 1009)',
    estante_em      DATETIME NULL COMMENT 'Abriu a Estante pela primeira vez',
    audio2_play_em  DATETIME NULL COMMENT 'Tocou o áudio de cobrança na Estante',
    checkout_em     DATETIME NULL COMMENT 'Abriu o checkout da contribuição',
    lembrete1_em    DATETIME NULL COMMENT 'Primeiro e-mail de lembrete (gravado antes de enviar)',
    lembrete2_em    DATETIME NULL COMMENT 'Segundo e-mail de lembrete',
    KEY idx_contrib_produto_criado (produto_id, criado_em),
    KEY idx_contrib_lembrete (email_em, lembrete1_em, lembrete2_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Quem já criou a tabela antes desta coluna existir (dev).
SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'contribuicao_pedidos' AND COLUMN_NAME = 'cliques');
SET @sql = IF(@tem = 0, 'ALTER TABLE contribuicao_pedidos
    ADD COLUMN cliques INT NOT NULL DEFAULT 1 COMMENT ''Cliques em Quero receber (braço estante: repetidos no mesmo aparelho somam aqui; wpp: 1 por lead)'' AFTER teste', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

-- Tempero (11): persona Luiza, teste DESLIGADO (percentual 0) até os áudios novos estarem no ar.
INSERT IGNORE INTO contribuicao_config
    (produto_id, ativo, percentual_estante, persona_nome, persona_foto,
     audio_intro, audio_cobranca, audio_lembrete, texto_intro, texto_cobranca, texto_lembrete, checklist)
VALUES (11, 1, 0, 'Luiza', 'images/luiza.jpg',
    'audios/contribuicao/tempero-intro-v1.mp3',
    'audios/contribuicao/tempero-cobranca-v1.mp3',
    'audios/contribuicao/tempero-lembrete-v1.mp3',
    'Oi, meu bem, tudo bem? Eu sou a Luiza e eu trabalho com cozinha há muitos anos. E nesse tempo eu aprendi que o segredo de uma comida realmente gostosa está no tempero. Por isso, eu organizei um material simples e prático, com os meus melhores temperos caseiros. Tem temperos secos, pastosos, misturas prontas para o dia a dia e combinações especiais para carne, frango, arroz, feijão e muito mais. Tudo natural, saboroso e sem conservantes. Eu também ensino as proporções certinhas, como conservar e até ideias para quem quiser vender e fazer uma renda extra. E pode ficar tranquila, porque é tudo muito fácil de fazer, mesmo para quem não tem experiência nenhuma na cozinha. A maioria dos ingredientes você já deve ter até aí na sua casa.\n\nE funciona assim: o material completo custa 67 reais, mas aqui eu te mando o livro agora, você dá uma olhadinha e, se gostar, faz uma contribuição de apenas 10 reais. E depois da sua contribuição, eu libero dois bônus especiais: um com dicas de como vender temperos no pote e outro com receitinhas de molhos caseiros que fazem o maior sucesso por aqui. Se você quiser receber agora, é só tocar no botão aqui embaixo.',
    'Prontinho, meu bem! Seu livro já está aqui na sua estante, é só tocar nele que ele abre direitinho. As receitas são super simples, com passo a passo detalhado. Mesmo que você nunca tenha feito isso antes, dessa vez você vai arrasar. Agora eu conto com a sua honestidade pra fazer a sua contribuição de 10 reais, tá? É só tocar no botão aqui embaixo, pode ser no Pix ou no cartão. Assim que cair, seus dois bônus aparecem aqui na hora, não precisa mandar comprovante nenhum. Muito obrigada pela confiança!',
    'Oi, meu bem, é a Luiza de novo! Eu sei como a rotina é corrida e a gente acaba deixando algumas coisas pra depois. Quando você conseguir um tempinho pra fazer a sua contribuição de 10 reais, eu vou ficar muito agradecida. Esse valor é simbólico, mas me ajuda a continuar criando essas receitas. E lembra: assim que ela cair, os seus bônus, as dicas de como vender temperos no pote e as receitinhas de molhos caseiros, aparecem aqui pra você na hora. Se tiver qualquer dificuldade, é só responder o e-mail que eu te ajudo, tá bom?',
    'Temperos secos e pastosos\nMisturas prontas pro dia a dia\nCombinações pra carne, frango, arroz e feijão\nProporções certinhas e como conservar');

SELECT produto_id, ativo, percentual_estante, persona_nome FROM contribuicao_config;
