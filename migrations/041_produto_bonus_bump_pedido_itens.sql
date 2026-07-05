-- Base de dados para vender produto principal + bônus + order bumps (estilo Hotmart).
-- Bônus e order bump são listas soltas (nome + arquivo), não apontam para outra linha de
-- produtos — mais simples de cadastrar, sem herdar campos de fluxo WhatsApp/IA que não
-- fazem sentido pra um bônus/bump.
-- pedido_itens grava um snapshot do que foi incluído em cada pedido (nome/arquivo/valor no
-- momento da compra), para que edições futuras no catálogo não reescrevam o histórico.
-- path_arquivo = onde o arquivo fica salvo (static/arquivos); nome_arquivo = nome de exibição
-- no download/anexo (ex: "receitas-bonus-bolos-sem-gluten.pdf"), usado quando a entrega por
-- e-mail/botão de download for implementada.
--
-- Nota: habilitar produtos individuais pro checkout web (disponivel_web=TRUE) fica pra
-- quando a gente refatorar o fluxo de checkout do site.
--
-- Nota para relatórios: pedido_itens grava uma linha assim que o lead é criado (estado 1001
-- em `pedidos`), antes da confirmação de pagamento — pedidos nunca pagos também aparecem
-- aqui. Qualquer soma de pedido_itens.valor para relatório de receita precisa fazer JOIN
-- com pedidos.estado_id (só contar quando estado_id = 1000), senão carrinho abandonado
-- entra como venda.

CREATE TABLE produto_bonus (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    produto_id    INT NOT NULL,
    nome          VARCHAR(255) NOT NULL,
    path_arquivo  VARCHAR(255) NOT NULL,
    nome_arquivo  VARCHAR(255) NOT NULL,
    descricao     VARCHAR(500) NULL,
    ordem         TINYINT UNSIGNED NOT NULL DEFAULT 1,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_produto_bonus_produto FOREIGN KEY (produto_id) REFERENCES produtos(id)
);

CREATE TABLE produto_bump (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    produto_id        INT NOT NULL,
    nome              VARCHAR(255) NOT NULL,
    path_arquivo      VARCHAR(255) NOT NULL,
    nome_arquivo      VARCHAR(255) NOT NULL,
    descricao         VARCHAR(500) NULL,
    preco_original    DECIMAL(10,2) NOT NULL,
    preco_promocional DECIMAL(10,2) NOT NULL,
    ordem             TINYINT UNSIGNED NOT NULL DEFAULT 1,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_produto_bump_produto FOREIGN KEY (produto_id) REFERENCES produtos(id)
);

CREATE TABLE pedido_itens (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id           INT NOT NULL,
    tipo                ENUM('principal','bonus','bump') NOT NULL,
    produto_bonus_id    INT NULL,
    produto_bump_id     INT NULL,
    nome                VARCHAR(255) NOT NULL,
    path_arquivo        VARCHAR(255) NOT NULL,
    nome_arquivo        VARCHAR(255) NOT NULL,
    valor               DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pedido_itens_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
    CONSTRAINT fk_pedido_itens_bonus FOREIGN KEY (produto_bonus_id) REFERENCES produto_bonus(id),
    CONSTRAINT fk_pedido_itens_bump FOREIGN KEY (produto_bump_id) REFERENCES produto_bump(id)
);

CREATE INDEX idx_produto_bonus_produto ON produto_bonus(produto_id);
CREATE INDEX idx_produto_bump_produto ON produto_bump(produto_id);
CREATE INDEX idx_pedido_itens_pedido ON pedido_itens(pedido_id);
