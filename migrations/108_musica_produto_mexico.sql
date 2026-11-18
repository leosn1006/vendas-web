-- Produto da Música no México (es-MX), para mostrar o site /mx/cancion a quem vai dar opinião — rodar DEPOIS da 107.
-- Mesmo molde da 090 (Brasil), com idioma = 'es-MX' (é assim que /mx/cancion acha o produto: produtos.idioma).
-- Idempotente: se o produto já existir (pelo nome), nada é inserido de novo.
--
-- Sem checkout por enquanto: o México vai vender pela Hotmart (outra frente). Até lá a prévia mostra "Por ahora no
-- estamos vendiendo" e o nosso /pay recusa música do México (integracao.conferir_para_checkout). Os preços abaixo
-- são só para o cadastro: o que valer no México sai das ofertas da Hotmart, em pesos.
-- Sem order bumps (QR e entrega para quem recebe ficam fora da 1ª versão da Hotmart).
--
-- Depois de rodar, no admin:
--   * "Disponível para venda no site": entra DESLIGADO; ligar para mostrar o site (o seletor de país do rodapé do
--     Brasil continua escondido até o lançamento: idiomas.py, 'no_seletor').
--   * E-mail remetente (precisa estar em "Enviar e-mail como" do Gmail do admin@) — os lembretes saem por ele.

SET NAMES utf8mb4;

INSERT INTO produtos (nome, idioma, preco, ativo, disponivel_web, nfe_automatica, nfe_config_id, numero_convenio_bb,
                      email_nome_remetente, email_cor_primaria, email_cor_secundaria)
SELECT 'Canción de Regalo (México)', 'es-MX', 29.90, 1, 0, 0,
       (SELECT id FROM nfe_configuracao WHERE tenant_slug = 'lbe-livros'),
       (SELECT numero_convenio_bb FROM produtos WHERE id = 12),
       'Canción de Regalo', '#E11D48', '#BE123C'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM produtos WHERE nome = 'Canción de Regalo (México)');

SET @produto = (SELECT id FROM produtos WHERE nome = 'Canción de Regalo (México)');

-- Os mesmos itens do catálogo do Brasil (o recurso é o que o pagamento libera; o idioma é da música, não do item).
SET @e_musica = (SELECT MIN(id) FROM entregaveis WHERE tipo = 'musica' AND recurso = 'musica');
SET @e_video = (SELECT MIN(id) FROM entregaveis WHERE tipo = 'musica' AND recurso = 'videoclipe');

INSERT INTO produto_planos (produto_id, slug, nome, preco_original, preco_promocional, desconto_oferta,
                            padrao, vitrine, renovacao, ativo)
SELECT @produto, p.slug, p.nome, p.preco, p.preco, 0, p.padrao, 1, 0, 1
FROM (SELECT 'musica' AS slug, 'Canción completa' AS nome, 29.90 AS preco, 1 AS padrao
      UNION ALL SELECT 'videoclipe', 'Canción + Videoclip', 49.90, 0) p
WHERE @produto IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM produto_planos pp WHERE pp.produto_id = @produto AND pp.slug = p.slug);

SET @plano_musica = (SELECT id FROM produto_planos WHERE produto_id = @produto AND slug = 'musica');
SET @plano_video = (SELECT id FROM produto_planos WHERE produto_id = @produto AND slug = 'videoclipe');

INSERT INTO plano_entregaveis (produto_id, plano_id, entregavel_id, papel, preco_original, preco_promocional, ordem)
SELECT @produto, i.plano_id, i.entregavel_id, 'principal', 0.00, 0.00, i.ordem
FROM (SELECT @plano_musica AS plano_id, @e_musica AS entregavel_id, 1 AS ordem
      UNION ALL SELECT @plano_video, @e_musica, 1
      UNION ALL SELECT @plano_video, @e_video, 2) i
WHERE i.plano_id IS NOT NULL AND i.entregavel_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM plano_entregaveis pe WHERE pe.plano_id = i.plano_id AND pe.entregavel_id = i.entregavel_id);

-- Conferência (deve mostrar 1 produto es-MX, 2 planos e 3 itens; e o produto do Brasil continua pt-BR):
SELECT p.id AS produto_id, p.nome, p.idioma, p.ativo, p.disponivel_web, p.nfe_automatica,
       (SELECT COUNT(*) FROM produto_planos WHERE produto_id = p.id) AS planos,
       (SELECT COUNT(*) FROM plano_entregaveis WHERE produto_id = p.id) AS itens
FROM produtos p WHERE p.id = @produto OR p.nome = 'Música de Presente';
