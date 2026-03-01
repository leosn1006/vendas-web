-- Migração 005: Ações de fluxo por produto
-- Substitui a lógica hardcoded nos arquivos fluxo_*.py por linhas configuráveis no BD.
-- Cada linha representa uma ação dentro de um fluxo, com sua ordem, condição,
-- tipo de ação, conteúdo (url/mensagem/arquivo) e delay humanizado antes da execução.
--
-- Lógica de ordenação:
--   • Ações com condicao='sempre' executam primeiro, em ordem crescente de `ordem`.
--   • Depois, as ações da condição aplicável (interesse_sim/nao ou pagamento_valido/invalido)
--     executam em sua própria ordem crescente de `ordem`.
--   • Quando duas condições ocupam o mesmo `ordem` (ex: interesse_sim e interesse_nao com
--     ordem=3 no fluxo pedido), significa que são alternativas no mesmo passo — apenas uma
--     delas será executada conforme a condição avaliada.

USE vendasdb;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS acoes_fluxo_produto (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    produto_id    INT              NOT NULL,
    fluxo         ENUM('introducao','pedido','comprovante','responder','followup')
                  NOT NULL,
    ordem         TINYINT UNSIGNED NOT NULL DEFAULT 1
                  COMMENT 'Sequência de execução dentro do escopo fluxo+condicao',
    condicao      ENUM('sempre','interesse_sim','interesse_nao','pagamento_valido','pagamento_invalido')
                  NOT NULL DEFAULT 'sempre'
                  COMMENT 'Condição para executar esta ação',
    acao          ENUM('marcar_lida','digitando','enviar_audio','enviar_imagem',
                       'enviar_arquivo','enviar_mensagem')
                  NOT NULL,
    url           VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                  COMMENT 'URL do áudio, imagem ou arquivo a enviar',
    mensagem      TEXT         CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                  COMMENT 'Texto da mensagem (acao=enviar_mensagem)',
    caption       VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                  COMMENT 'Legenda do arquivo (acao=enviar_arquivo)',
    nome_arquivo  VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                  COMMENT 'Nome do arquivo exibido ao cliente (acao=enviar_arquivo)',
    delay_inicial DECIMAL(5,1)  NOT NULL DEFAULT 0.0
                  COMMENT 'Tempo mínimo de espera (s) antes de executar esta ação',
    delay_final   DECIMAL(5,1)  NOT NULL DEFAULT 0.0
                  COMMENT 'Tempo máximo de espera (s) antes de executar esta ação',
    CONSTRAINT fk_afp_produto FOREIGN KEY (produto_id) REFERENCES produtos(id),
    UNIQUE KEY uk_afp (produto_id, fluxo, condicao, ordem)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Sequência parametrizável de ações de fluxo por produto';


-- ============================================================
-- SEED: Produto 1 — mapeamento das ações atuais hardcoded
-- Conteúdo (url/mensagem) é copiado da tabela produtos logo
-- abaixo de cada bloco de INSERT, via UPDATE … JOIN produtos.
-- ============================================================

-- ------------------------------------------------------------
-- FLUXO: introducao  (estado 1 → 2)
-- sempre: marcar_lida → digitando → áudio1 → digitando →
--         áudio2 → digitando → imagem → digitando → mensagem
-- ------------------------------------------------------------
INSERT IGNORE INTO acoes_fluxo_produto
    (produto_id, fluxo, ordem, condicao, acao,             url,  mensagem, caption, nome_arquivo, delay_inicial, delay_final)
VALUES
    (1, 'introducao', 1, 'sempre', 'marcar_lida',    NULL, NULL, NULL, NULL,  0.0,  0.0),
    (1, 'introducao', 2, 'sempre', 'digitando',      NULL, NULL, NULL, NULL,  0.0,  0.0),
    (1, 'introducao', 3, 'sempre', 'enviar_audio',   NULL, NULL, NULL, NULL,  8.0, 10.0),  -- url_audio_introducao
    (1, 'introducao', 4, 'sempre', 'digitando',      NULL, NULL, NULL, NULL,  0.0,  0.0),
    (1, 'introducao', 5, 'sempre', 'enviar_audio',   NULL, NULL, NULL, NULL,  5.0,  8.0),  -- url_audio_explicativo
    (1, 'introducao', 6, 'sempre', 'digitando',      NULL, NULL, NULL, NULL,  0.0,  0.0),
    (1, 'introducao', 7, 'sempre', 'enviar_imagem',  NULL, NULL, NULL, NULL,  5.0,  8.0),  -- url_imagem_complementar
    (1, 'introducao', 8, 'sempre', 'digitando',      NULL, NULL, NULL, NULL,  0.0,  0.0),
    (1, 'introducao', 9, 'sempre', 'enviar_mensagem',NULL, NULL, NULL, NULL,  5.0,  8.0);  -- mensagem_introducao

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.url      = p.url_audio_introducao
WHERE afp.produto_id = 1 AND afp.fluxo = 'introducao' AND afp.ordem = 3;

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.url      = p.url_audio_explicativo
WHERE afp.produto_id = 1 AND afp.fluxo = 'introducao' AND afp.ordem = 5;

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.url      = p.url_imagem_complementar
WHERE afp.produto_id = 1 AND afp.fluxo = 'introducao' AND afp.ordem = 7;

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.mensagem = p.mensagem_introducao
WHERE afp.produto_id = 1 AND afp.fluxo = 'introducao' AND afp.ordem = 9;


-- ------------------------------------------------------------
-- FLUXO: pedido  (estado 2 → 3)
-- sempre (1,2): marcar_lida → digitando
-- interesse_sim (3): mensagem pré-entrega
-- interesse_nao (3): mensagem alternativa pré-entrega
-- sempre (4): enviar PDF do produto
-- interesse_sim (5): áudio de entregue
-- interesse_nao (5): mensagem sem interesse
-- sempre (6,7,8): dados pix → chave pix → teaser surpresa
-- Nota: ordem 3 e 5 compartilhadas entre interesse_sim/nao
--       pois são alternativas no mesmo passo do fluxo.
-- ------------------------------------------------------------
INSERT IGNORE INTO acoes_fluxo_produto
    (produto_id, fluxo, ordem, condicao,        acao,             url,  mensagem, caption, nome_arquivo, delay_inicial, delay_final)
VALUES
    (1, 'pedido', 1, 'sempre',        'marcar_lida',    NULL, NULL, NULL, NULL,  0.0,  0.0),
    (1, 'pedido', 2, 'sempre',        'digitando',      NULL, NULL, NULL, NULL,  0.0,  0.0),
    (1, 'pedido', 3, 'interesse_sim', 'enviar_mensagem',NULL,
        'Suas receitinhas estão aqui, é só clicar abaixo ⬇',
        NULL, NULL,  9.0, 12.0),
    (1, 'pedido', 3, 'interesse_nao', 'enviar_mensagem',NULL,
        'Queremos o seu melhor, então receba esse presente totalmente sem custo⬇',
        NULL, NULL,  9.0, 12.0),
    (1, 'pedido', 4, 'sempre',        'enviar_arquivo', NULL, NULL, NULL, NULL,  0.0,  0.0),  -- url_arquivo_produto
    (1, 'pedido', 5, 'interesse_sim', 'enviar_audio',   NULL, NULL, NULL, NULL, 12.0, 20.0),  -- url_audio_pedido_entregue (delay 10-15 + 2-5)
    (1, 'pedido', 5, 'interesse_nao', 'enviar_mensagem',NULL, NULL, NULL, NULL, 10.0, 15.0),  -- mensagem_pedido_enviado_sem_interesse
    (1, 'pedido', 6, 'sempre',        'enviar_mensagem',NULL, NULL, NULL, NULL,  5.0,  9.0),  -- mensagem_para_pagamento
    (1, 'pedido', 7, 'sempre',        'enviar_mensagem',NULL, NULL, NULL, NULL,  0.0,  0.0),  -- chave_pix
    (1, 'pedido', 8, 'sempre',        'enviar_mensagem',NULL,
        '🎁 *Surpresinha especial* para quem realizar o pagamento e enviar o comprovante!',
        NULL, NULL,  0.0,  0.0);

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.url = p.url_arquivo_produto, afp.caption = p.caption_arquivo_produto, afp.nome_arquivo = p.nome_arquivo_produto
WHERE afp.produto_id = 1 AND afp.fluxo = 'pedido' AND afp.ordem = 4;

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.url      = p.url_audio_pedido_entregue
WHERE afp.produto_id = 1 AND afp.fluxo = 'pedido' AND afp.ordem = 5 AND afp.condicao = 'interesse_sim';

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.mensagem = p.mensagem_pedido_enviado_sem_interesse
WHERE afp.produto_id = 1 AND afp.fluxo = 'pedido' AND afp.ordem = 5 AND afp.condicao = 'interesse_nao';

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.mensagem = p.mensagem_para_pagamento
WHERE afp.produto_id = 1 AND afp.fluxo = 'pedido' AND afp.ordem = 6;

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.mensagem = p.chave_pix
WHERE afp.produto_id = 1 AND afp.fluxo = 'pedido' AND afp.ordem = 7;


-- ------------------------------------------------------------
-- FLUXO: comprovante
-- sempre (1): marcar_lida
-- pagamento_valido (2,3,4): digitando → confirmação → arquivo surpresa
-- pagamento_invalido (2,3): digitando → mensagem inválido
-- Cada ramo condicional tem sua própria sequência a partir de ordem=2.
-- ------------------------------------------------------------
INSERT IGNORE INTO acoes_fluxo_produto
    (produto_id, fluxo, ordem, condicao,             acao,             url,  mensagem, caption, nome_arquivo, delay_inicial, delay_final)
VALUES
    (1, 'comprovante', 1, 'sempre',            'marcar_lida',    NULL, NULL, NULL, NULL, 0.0, 0.0),
    (1, 'comprovante', 2, 'pagamento_valido',  'digitando',      NULL, NULL, NULL, NULL, 0.0, 0.0),
    (1, 'comprovante', 3, 'pagamento_valido',  'enviar_mensagem',NULL, NULL, NULL, NULL, 0.0, 0.0),  -- mensagem_pagamento_confirmado
    (1, 'comprovante', 4, 'pagamento_valido',  'enviar_arquivo', NULL, NULL, NULL, NULL, 5.0, 8.0),  -- url_arquivo_surpresa
    (1, 'comprovante', 2, 'pagamento_invalido','digitando',      NULL, NULL, NULL, NULL, 0.0, 0.0),
    (1, 'comprovante', 3, 'pagamento_invalido','enviar_mensagem',NULL, NULL, NULL, NULL, 3.0, 6.0);  -- mensagem_comprovante_invalido

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.mensagem = p.mensagem_pagamento_confirmado
WHERE afp.produto_id = 1 AND afp.fluxo = 'comprovante' AND afp.ordem = 3 AND afp.condicao = 'pagamento_valido';

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.url = p.url_arquivo_surpresa, afp.caption = p.caption_arquivo_surpresa, afp.nome_arquivo = p.nome_arquivo_surpresa
WHERE afp.produto_id = 1 AND afp.fluxo = 'comprovante' AND afp.ordem = 4;

UPDATE acoes_fluxo_produto afp JOIN produtos p ON p.id = afp.produto_id
SET afp.mensagem = p.mensagem_comprovante_invalido
WHERE afp.produto_id = 1 AND afp.fluxo = 'comprovante' AND afp.ordem = 3 AND afp.condicao = 'pagamento_invalido';


-- ------------------------------------------------------------
-- FLUXO: responder  (estado >= 3, respostas a dúvidas)
-- sempre: marcar_lida → digitando → enviar_mensagem (gerada por IA)
-- Nota: mensagem da ordem 3 é NULL pois é gerada pelo agente de IA em runtime.
-- ------------------------------------------------------------
INSERT IGNORE INTO acoes_fluxo_produto
    (produto_id, fluxo, ordem, condicao, acao,             url,  mensagem, caption, nome_arquivo, delay_inicial, delay_final)
VALUES
    (1, 'responder', 1, 'sempre', 'marcar_lida',    NULL, NULL, NULL, NULL, 0.0, 0.0),
    (1, 'responder', 2, 'sempre', 'digitando',      NULL, NULL, NULL, NULL, 5.0, 8.0),
    (1, 'responder', 3, 'sempre', 'enviar_mensagem',NULL, NULL, NULL, NULL, 0.0, 0.0);  -- gerada por IA


-- ------------------------------------------------------------
-- FLUXO: followup  (estado 3 → 4, executado por schedule)
-- interesse_sim (1): mensagem para cliente com interesse declarado
-- interesse_nao (1): mensagem para cliente sem interesse declarado
-- Nota: mensagens hardcoded pois não existem na tabela produtos.
-- ------------------------------------------------------------
INSERT IGNORE INTO acoes_fluxo_produto
    (produto_id, fluxo, ordem, condicao,        acao,             url,  mensagem, caption, nome_arquivo, delay_inicial, delay_final)
VALUES
    (1, 'followup', 1, 'interesse_sim', 'enviar_mensagem', NULL,
        'Oi! Sei que o dia a dia é bem corrido, mas o nosso sistema ainda não identificou o seu pagamento. \n \n Será que você consegue ajudar nosso projeto com apenas R$10,00? Posso te ajudar com alguma dúvida? 😊',
        NULL, NULL, 0.0, 0.0),
    (1, 'followup', 1, 'interesse_nao', 'enviar_mensagem', NULL,
        'Ola! Gostou do nosso presente. \n \n Será que você consegue ajudar nosso projeto com apenas R$10,00? E ainda você ganhará outro presente surpresa. Posso te ajudar com alguma dúvida? 😊',
        NULL, NULL, 0.0, 0.0);
