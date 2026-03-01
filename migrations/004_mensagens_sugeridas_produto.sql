-- Migração 004: Mensagens sugeridas por produto
-- Substitui o dict_mensagens hardcoded em agente_gera_mensagem_inicial.py.
-- O sistema sorteia aleatoriamente uma dessas mensagens ao criar um novo lide.

USE vendasdb;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS mensagens_sugeridas_produto (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    produto_id INT          NOT NULL,
    mensagem   VARCHAR(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    CONSTRAINT fk_msp_produto FOREIGN KEY (produto_id) REFERENCES produtos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Mensagens iniciais sugeridas ao visitante por produto';

-- Seed: mensagens do produto 1 (E-book Receitas Sem Glúten)
INSERT IGNORE INTO mensagens_sugeridas_produto (produto_id, mensagem) VALUES
(1, 'Olá, tenho interesse nas receitas'),
(1, 'Oi, tenho interesse nas receitas'),
(1, 'Olá, quero receber as receitas'),
(1, 'Oi, quero receber as receitas'),
(1, 'Olá, pode me enviar as receitas?'),
(1, 'Oi, pode me enviar as receitas?'),
(1, 'Olá, gostaria de saber mais sobre as receitas'),
(1, 'Oi, gostaria de saber mais sobre as receitas');
