-- Migration 060: catálogo central de e-books + vínculo com produto.
--
-- Hoje o caminho do PDF de um produto está duplicado em várias tabelas
-- (produtos.url_pdf/url_arquivo_produto, produto_bonus.path_arquivo,
-- produto_bump.path_arquivo, acoes_fluxo_produto.url) — cadastrar um produto
-- novo significa repetir nome/descrição/valor/arquivo várias vezes, o que já
-- causou erro de enviar o arquivo errado pro cliente.
--
-- ebooks é o catálogo único (cadastra uma vez); ebooks_produto vincula um
-- ebook a um produto informando o papel dele (principal/bonus/bump). Este
-- primeiro passo só cria a base — nenhuma tela ou fluxo existente (WhatsApp,
-- checkout, produtos/produto_bonus/produto_bump/acoes_fluxo_produto) foi
-- alterado pra ler daqui ainda; a migração da entrega vem depois, gradualmente.
--
-- path_arquivo/nome_arquivo seguem a mesma convenção de produto_bonus/produto_bump:
-- path_arquivo = URL pública completa do PDF em static/arquivos/; nome_arquivo =
-- nome de exibição pro cliente no download/anexo. imagem_grande/imagem_pequena
-- guardam só o nome do arquivo em static/images/ (mesma convenção de
-- produto_bump.imagem_checkout) — a capa é característica do e-book, não do
-- vínculo, por isso fica aqui; grande é usada quando o e-book é o principal do
-- produto, pequena quando é bônus ou order bump.
--
-- Preço NÃO fica no catálogo: o mesmo e-book pode valer preços diferentes
-- dependendo do papel que ocupa em cada produto (ex: R$10 como principal de um
-- produto, R$0 como bônus de outro, R$6,90 como order bump de um terceiro) —
-- por isso preco_original/preco_promocional (mesmo nome de produto_bump, pra
-- permitir promoções) ficam em ebooks_produto, por vínculo.
--
-- papel='principal' único por produto é garantido no banco via a coluna gerada
-- produto_principal + unique key: MySQL trata múltiplos NULL como distintos numa
-- UNIQUE KEY, então linhas com papel<>'principal' (produto_principal=NULL) podem
-- se repetir à vontade, mas duas linhas 'principal' pro mesmo produto_id colidem
-- na unique key — sem essa coluna, um SELECT-then-INSERT na aplicação teria uma
-- corrida (dois cliques quase simultâneos podiam passar os dois pela checagem).
--
-- CHARACTER SET/COLLATE explícito nas colunas de texto: já é redundante com o
-- default do banco (vendasdb é utf8mb4/utf8mb4_unicode_ci desde o 001_script.sql),
-- mas segue a mesma convenção defensiva usada lá — protege contra o default do
-- banco mudar no futuro. Não tem relação com o bug de acentuação corrompida que
-- apareceu ao importar seed via `mysql` sem --default-character-set: aquele era
-- do charset da CONEXÃO cliente no momento do import, não da coluna.

CREATE TABLE ebooks (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    nome_venda     VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    descricao      VARCHAR(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
    path_arquivo   VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    nome_arquivo   VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
    imagem_grande  VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
    imagem_pequena VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE ebooks_produto (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    produto_id         INT NOT NULL,
    ebook_id           INT NOT NULL,
    papel              ENUM('principal','bonus','bump') NOT NULL,
    preco_original     DECIMAL(10,2) NOT NULL,
    preco_promocional  DECIMAL(10,2) NOT NULL,
    ordem              TINYINT UNSIGNED NOT NULL DEFAULT 1,
    produto_principal  INT GENERATED ALWAYS AS (CASE WHEN papel = 'principal' THEN produto_id END) VIRTUAL,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ebooks_produto_produto FOREIGN KEY (produto_id) REFERENCES produtos(id),
    CONSTRAINT fk_ebooks_produto_ebook FOREIGN KEY (ebook_id) REFERENCES ebooks(id),
    UNIQUE KEY uk_ebooks_produto_principal (produto_principal)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ebooks_produto_produto ON ebooks_produto(produto_id);
CREATE INDEX idx_ebooks_produto_ebook ON ebooks_produto(ebook_id);
