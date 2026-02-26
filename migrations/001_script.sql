-- Script de criação do banco de dados MySQL
-- Encoding: UTF-8

USE vendasdb;

-- Garante interpretação correta de acentos e emojis durante execução do script
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Tabela de produtos
CREATE TABLE IF NOT EXISTS produtos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL UNIQUE,
    preco DECIMAL(10, 2) NOT NULL,
    descricao TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    prompt_vendas TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    url_faq_produto VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    prompt_followup TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    url_audio_introducao VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    url_audio_explicativo VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    url_audio_pedido_entregue VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    url_imagem_complementar VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    url_arquivo_produto VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    caption_arquivo_produto TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    nome_arquivo_produto VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    mensagem_introducao TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    mensagem_pedido_enviado_sem_interesse TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    mensagem_para_pagamento TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    chave_pix VARCHAR(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    pix_destinatario_esperado VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    valor_minimo_pagamento DECIMAL(10, 2),
    mensagem_pagamento_confirmado TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    mensagem_comprovante_invalido TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    url_arquivo_surpresa VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    caption_arquivo_surpresa TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    nome_arquivo_surpresa VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Índice adicional na tabela produtos
CREATE INDEX idx_produtos_ativo ON produtos(ativo);

-- Inserir produtos iniciais
INSERT IGNORE INTO produtos (
    nome,
    preco,
    descricao,
    prompt_vendas,
    url_faq_produto,
    url_audio_introducao,
    url_audio_explicativo,
    url_audio_pedido_entregue,
    url_imagem_complementar,
    url_arquivo_produto,
    caption_arquivo_produto,
    nome_arquivo_produto,
    mensagem_introducao,
    mensagem_pedido_enviado_sem_interesse,
    mensagem_para_pagamento,
    chave_pix,
    pix_destinatario_esperado,
    valor_minimo_pagamento,
    mensagem_pagamento_confirmado,
    mensagem_comprovante_invalido,
    url_arquivo_surpresa,
    caption_arquivo_surpresa,
    nome_arquivo_surpresa
)
VALUES (
    'ebook celiaco',
    10.00,
    'E-book com receitas para celíacos',
    'Você é a Luiza, consultora atenciosa de receitas sem glúten. Responda em português do Brasil, de forma objetiva, cordial e no estilo WhatsApp. Use poucos emojis. Nunca invente informações. Se faltar contexto, diga que vai confirmar e retornar. Foque em ajudar a pessoa a avançar na conversa de compra e pagamento sem pressionar.',
    'prompts/faq_paes_sem_gluten.txt',
    'https://lneditor.com.br/static/audios/introducao-paes.ogg',
    'https://lneditor.com.br/static/audios/introducao-explicativa-paes.ogg',
    'https://lneditor.com.br/static/audios/paes-pedido-entregue.ogg',
    'https://lneditor.com.br/static/images/paes-foto-semanal.jpg',
    'https://lneditor.com.br/static/arquivos/paes-sem-gluten.pdf',
    'Aqui está suas receitas sem glúten e sem lactose 📚',
    'RECEITAS LIBERADAS! ❤️ - Toque AQUI.pdf',
    '*Esses são alguns pães que fiz na última semana 😋*\nPosso te enviar o livrinho agora?',
    'Se você gostou do presente e se for da sua vontade, você pode nos ajudar ajudar com R$10,00 ou mais. Essa ajuda irá permitir que outras pessoas conheçam essas receitas sem glutén e possam ter uma vida mais tranquila e saudável também ❤️ Para contribuir, vou mandar os dados do Pix ⬇',
    '*Informações do PIX*:\n\n- 💸 *Valor*: R$10, 12, 15, 20\n- 📱 *Chave Pix* (cpf): 50934392315\n- 👤 *Nome*: Leonardo Santos Negreiros\n\nPara facilitar, vou te enviar a chave Pix separada, assim é só copiar e colar:',
    '50934392315',
    'leonardo santos negreiros',
    10.00,
    'Obrigado pelo envio do comprovante e sua honestidade 🙏🏼! Estamos confirmando o pagamento e em breve você receberá seu e-book surpresa! 🎁',
    'Não consegui validar seu comprovante ainda. Por favor, verifique se o valor é igual ou superior ao mínimo e se o destinatário do Pix está correto, depois envie novamente 🙏🏼',
    'https://lneditor.com.br/static/arquivos/bolos-sem-gluten.pdf',
    'Sua surpresa chegou! 🎁',
    'BOLOS SEM GLUTEN-RECEITAS-SURPRESA.pdf'
);

-- Tabela de estados de pedidos
CREATE TABLE IF NOT EXISTS estado_pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    descricao VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Inserir estados de pedidos
SET SESSION sql_mode = 'NO_AUTO_VALUE_ON_ZERO';
INSERT IGNORE INTO estado_pedidos (id, descricao) VALUES
(0, 'Pago'),
(1, 'Cliente acessou a página de vendas e clicou para enviar mensagem'),
(2, 'Enviado mensagem de introdução'),
(3, 'Produto enviado'),
(4, 'Follow-up enviado')


-- Tabela de pedidos
CREATE TABLE IF NOT EXISTS pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    produto_id INT NOT NULL,
    valor_pago DECIMAL(6, 2) NOT NULL,
    estado_id INT NOT NULL DEFAULT 1,
    gclid VARCHAR(255) NULL DEFAULT NULL,
    data_ultima_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    mensagem_sugerida varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    emoji_sugerida VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    data_contato_site TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    interesse_produto BOOLEAN DEFAULT NULL,
    phone_number_id VARCHAR(20) NULL DEFAULT NULL,
    contact_phone VARCHAR(20) NULL DEFAULT NULL,
    contact_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
    data_pedido TIMESTAMP NULL DEFAULT NULL,
    campaignid VARCHAR(255) NULL DEFAULT NULL,
    adgroupid VARCHAR(255) NULL DEFAULT NULL,
    creative VARCHAR(255) NULL DEFAULT NULL,
    matchtype VARCHAR(255) NULL DEFAULT NULL,
    device VARCHAR(255) NULL DEFAULT NULL,
    placement VARCHAR(255) NULL DEFAULT NULL,
    video_id VARCHAR(255) NULL DEFAULT NULL,
    path_comprovante VARCHAR(120) NULL DEFAULT NULL,
    data_followup TIMESTAMP NULL DEFAULT NULL,
    nome_banco VARCHAR(100) NULL DEFAULT NULL,
    nome_pagador VARCHAR(150) NULL DEFAULT NULL,
    data_pagamento TIMESTAMP NULL DEFAULT NULL,
    data_envio_pedido TIMESTAMP NULL DEFAULT NULL,
    data_envio_google_ads TIMESTAMP NULL DEFAULT NULL,
    data_agendamento_pagamento TIMESTAMP NULL DEFAULT NULL ,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE RESTRICT,
    FOREIGN KEY (estado_id) REFERENCES estado_pedidos(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Índices na tabela pedidos
CREATE INDEX idx_pedidos_data_estado ON pedidos(data_pedido, estado_id);
CREATE INDEX idx_pedidos_contact ON pedidos(contact_name, data_pedido);
CREATE INDEX idx_pedidos_phone ON pedidos(contact_phone);
CREATE INDEX idx_pedidos_data_envio_google_ads ON pedidos(estado_id, data_contato_site, data_envio_google_ads);

-- Tabela de mensagens dos pedidos
CREATE TABLE IF NOT EXISTS mensagens_pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id INT NOT NULL,
    sequencial_mensagem INT NOT NULL,
    message_id VARCHAR(100) NOT NULL,
    data_mensagem TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mensagem_json TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    tipo_mensagem ENUM('recebida', 'enviada') DEFAULT 'recebida',
    UNIQUE KEY uk_pedido_sequencial (pedido_id, sequencial_mensagem),
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Índices na tabela mensagens_pedidos
CREATE INDEX idx_mensagens_pedido ON mensagens_pedidos(pedido_id, data_mensagem);
CREATE INDEX idx_mensagens_message_id ON mensagens_pedidos(message_id);
