-- Carga do catálogo de e-books em produção — gerada a partir dos dados já validados no
-- ambiente de dev (16 e-books, 29 vínculos, produtos 1/6/7/8/9/10/11/12/14).
-- ebook_id é resolvido por path_arquivo (não por id fixo), então roda igual independente
-- do estado do AUTO_INCREMENT em produção.

INSERT INTO ebooks (nome_venda, descricao, path_arquivo, nome_arquivo, imagem_grande, imagem_pequena) VALUES
('Receitas de Pães Sem Glúten e Sem Lactose','Receitas caseiras de pães sem glúten e sem lactose','paes-sem-gluten.pdf','receitas-paes-sem-gluten.pdf',NULL,'paes-sem-gluten-sem-lactose.webp'),
('Páscoa Lucrativa','Receitas caseiras de ovos de páscoa de colher e dicas para lucrar com a venda','pascoa-lucrativa.pdf','pascoa-lucrativa.pdf',NULL,NULL),
('O Que Ninguém Me Contou Sobre a Quimio','Dicas de quem já passou pelo tratamento de câncer e quimioterapia','dicas-quimio.pdf','dicas-quimio.pdf',NULL,NULL),
('Pudim Sem Segredo','+30 pudins cremosos e irresistíveis, sem precisar ligar o forno.','pudim.pdf','receitas-pudim-sem-forno.pdf',NULL,'pudim-sem-segredo.webp'),
('Doces Fit Irresistíveis','25 Receitas Tradicionais de Doces Com Suas Versões Fit para não subir a balança.','sobremesa-doce-equilibrio.pdf','receitas-doce-equilibrio.pdf',NULL,'doces-fit-irresistiveis.webp'),
('Sabor Sem Açúcar','Receitas gostosas para reduzir o açúcar sem abrir mão do prazer de comer bem.','dia-dia-sem-acucar.pdf','receitas-dia-dia-sem-acucar.pdf',NULL,'sabor-sem-acucar.webp'),
('Temperos Caseiros no Pote','40 blends artesanais irresistíveis para transformar receitas simples em pratos cheios de sabor.','receitas-temperos-caseiros.pdf','receitas-temperos-caseiros.pdf','tempero-web-banner.webp',NULL),
('Fatias que Vendem','Receitas de fatias irresistíveis para transformar bolos simples em uma renda extra.','fatias-feira.pdf','receitas-fatias-feira.pdf','fatia-banner.webp','fatias-que-vendem.webp'),
('Guia das Orquídeas','Guia de recuperação de Orquídeas','orquideas_sos.pdf','orquideas_sos.pdf','orquidea-capa.webp',NULL),
('Receitas de Bolos Sem Glúten','Receitas Caseiras de Bolos Sem Glúten e Sem Açúcar','bolos-sem-gluten.pdf','receitas-bonus-bolos-sem-gluten.pdf',NULL,NULL),
('Como Vender Temperos no Pote','Dicas de como Vender Temperos no Pote e Fazer uma Renda Extra no Mês','tempero-como-vender.pdf','tempero-como-vender-1.pdf',NULL,NULL),
('Receitas de Molhos sem Açúcar','10 Receitas Caseiras de Molhos Sem Açúcar','molho.pdf','receitas-molho-sem-acucar.pdf',NULL,NULL),
('Receitas Caseiras de Bolos','Bolos inteiros para fazer em casa, além das fatias.','fatias-bolos.pdf','RECEITAS-BOLOS-CASEIROS.pdf',NULL,NULL),
('Guia de Vendas na Feira','Dicas práticas de precificação, embalagem e vendas.','fatia-vendas.pdf','DICAS-VENDA-FATIA-BOLO.pdf',NULL,NULL),
('Brigadeiros Gourmet que Vendem','10 brigadeiros irresistíveis com cara de confeitaria para fazer, vender e lucrar.','brigadeiros.pdf','receitas-brigadeiro.pdf',NULL,'brigadeiros-gourmet-que-vendem.webp'),
('Tudo na Air Fryer','+140 receitas completas de carnes, petiscos, massas e sobremesas na air fryer, com menos óleo.','tudo-na-airfryer.pdf','receitas-tudo-na-airfryer.pdf',NULL,'tudo-na-airfryer.webp');

-- Vínculos principal (1 por produto)
INSERT INTO ebooks_produto (produto_id, ebook_id, papel, preco_original, preco_promocional, ordem)
SELECT v.produto_id, e.id, v.papel, v.preco_original, v.preco_promocional, v.ordem
FROM (
    SELECT  1 AS produto_id, 'paes-sem-gluten.pdf'           AS path_arquivo, 'principal' AS papel, 10.00 AS preco_original, 10.00 AS preco_promocional, 1 AS ordem UNION ALL
    SELECT  6, 'pascoa-lucrativa.pdf',           'principal', 10.00, 10.00, 1 UNION ALL
    SELECT  7, 'dicas-quimio.pdf',               'principal', 19.90, 19.90, 1 UNION ALL
    SELECT  8, 'pudim.pdf',                      'principal', 10.00, 10.00, 1 UNION ALL
    SELECT  9, 'sobremesa-doce-equilibrio.pdf',  'principal', 10.00, 10.00, 1 UNION ALL
    SELECT 10, 'dia-dia-sem-acucar.pdf',         'principal', 10.00, 10.00, 1 UNION ALL
    SELECT 11, 'receitas-temperos-caseiros.pdf', 'principal', 10.00, 10.00, 1 UNION ALL
    SELECT 12, 'fatias-feira.pdf',               'principal', 10.00, 10.00, 1 UNION ALL
    SELECT 14, 'orquideas_sos.pdf',              'principal', 10.00, 10.00, 1
) v
JOIN ebooks e ON e.path_arquivo = v.path_arquivo;

-- Vínculos bônus (valor sempre 0.00, por convenção)
INSERT INTO ebooks_produto (produto_id, ebook_id, papel, preco_original, preco_promocional, ordem)
SELECT v.produto_id, e.id, v.papel, v.preco_original, v.preco_promocional, v.ordem
FROM (
    SELECT  8 AS produto_id, 'bolos-sem-gluten.pdf'     AS path_arquivo, 'bonus' AS papel, 0.00 AS preco_original, 0.00 AS preco_promocional, 1 AS ordem UNION ALL
    SELECT 11, 'tempero-como-vender.pdf', 'bonus', 0.00, 0.00, 1 UNION ALL
    SELECT 11, 'molho.pdf',               'bonus', 0.00, 0.00, 2 UNION ALL
    SELECT 12, 'fatias-bolos.pdf',        'bonus', 0.00, 0.00, 1 UNION ALL
    SELECT 12, 'fatia-vendas.pdf',        'bonus', 0.00, 0.00, 2
) v
JOIN ebooks e ON e.path_arquivo = v.path_arquivo;

-- Vínculos order bump (preço vem direto de produto_bump de produção)
INSERT INTO ebooks_produto (produto_id, ebook_id, papel, preco_original, preco_promocional, ordem)
SELECT v.produto_id, e.id, v.papel, v.preco_original, v.preco_promocional, v.ordem
FROM (
    SELECT  8 AS produto_id, 'fatias-feira.pdf'               AS path_arquivo, 'bump' AS papel, 19.90 AS preco_original, 0.70 AS preco_promocional, 1 AS ordem UNION ALL
    SELECT  8, 'receitas-temperos-caseiros.pdf', 'bump', 17.90, 0.08, 2 UNION ALL
    SELECT 11, 'brigadeiros.pdf',                'bump', 10.90, 3.90, 1 UNION ALL
    SELECT 11, 'fatias-feira.pdf',                'bump', 19.90, 6.90, 2 UNION ALL
    SELECT 11, 'pudim.pdf',                       'bump', 19.90, 6.90, 3 UNION ALL
    SELECT 11, 'dia-dia-sem-acucar.pdf',          'bump', 19.90, 6.90, 4 UNION ALL
    SELECT 11, 'sobremesa-doce-equilibrio.pdf',   'bump', 19.90, 6.90, 5 UNION ALL
    SELECT 11, 'paes-sem-gluten.pdf',             'bump', 19.90, 6.90, 6 UNION ALL
    SELECT 11, 'tudo-na-airfryer.pdf',            'bump', 29.90, 9.90, 7 UNION ALL
    SELECT 12, 'brigadeiros.pdf',                 'bump', 10.90, 3.90, 1 UNION ALL
    SELECT 12, 'pudim.pdf',                       'bump', 19.90, 6.90, 2 UNION ALL
    SELECT 12, 'dia-dia-sem-acucar.pdf',          'bump', 19.90, 6.90, 3 UNION ALL
    SELECT 12, 'sobremesa-doce-equilibrio.pdf',   'bump', 19.90, 6.90, 4 UNION ALL
    SELECT 12, 'paes-sem-gluten.pdf',             'bump', 19.90, 6.90, 5 UNION ALL
    SELECT 12, 'tudo-na-airfryer.pdf',             'bump', 29.90, 9.90, 6
) v
JOIN ebooks e ON e.path_arquivo = v.path_arquivo;
