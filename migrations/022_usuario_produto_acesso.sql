-- Migration 022: Controle de acesso de usuários por produto
-- Cria tabela de vínculo usuario_produtos e adiciona coluna de primeiro_acesso

-- Tabela de vínculo: um usuário pode ter acesso a múltiplos produtos
CREATE TABLE IF NOT EXISTS usuario_produtos (
    usuario_id  INT NOT NULL,
    produto_id  INT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (usuario_id, produto_id),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
);

-- Indica que o usuário ainda usa a senha padrão e deve trocá-la no primeiro acesso
ALTER TABLE usuarios ADD COLUMN primeiro_acesso BOOLEAN NOT NULL DEFAULT FALSE;
