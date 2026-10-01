-- Até onde cada visita chegou num quiz de página de vendas (hoje: /fatia-e → fatia2-e.html).
-- Uma linha por pedido rascunho (o mesmo criado por rastrear_visita_funil no 1004), guardando só
-- a etapa MAIS AVANÇADA alcançada — é o que basta pra ver em qual pergunta as pessoas desistem
-- (tela Analytics Web do admin). `pagina` separa quizzes diferentes do mesmo produto, se houver.
CREATE TABLE IF NOT EXISTS quiz_progresso (
    pedido_id      INT          NOT NULL PRIMARY KEY,
    pagina         VARCHAR(40)  NOT NULL COMMENT 'Slug do quiz (ex: fatia2-e)',
    etapa          TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 = abriu a página; maior = mais avançado',
    etapa_nome     VARCHAR(60)  NULL,
    criado_em      TIMESTAMP    NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em  TIMESTAMP    NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_quiz_progresso_pagina (pagina, criado_em),
    CONSTRAINT fk_quiz_progresso_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
