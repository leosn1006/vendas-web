-- Capas dos planos da Música no checkout (26/10/2026): static/images/musica-plano-musica.webp e
-- musica-plano-videoclipe.webp (16:9, tema escuro da landing). Só preenche plano ainda sem capa — se já foi
-- escolhida outra no admin, fica a do admin. Idempotente.
SET NAMES utf8mb4;

UPDATE produto_planos pp JOIN produtos p ON p.id = pp.produto_id
SET pp.imagem_grande = CASE pp.slug WHEN 'musica' THEN 'musica-plano-musica.webp'
                                    WHEN 'videoclipe' THEN 'musica-plano-videoclipe.webp' END
WHERE p.nome = 'Música de Presente' AND pp.slug IN ('musica', 'videoclipe')
  AND (pp.imagem_grande IS NULL OR pp.imagem_grande = '');

-- Conferência: os 2 planos com a capa.
SELECT pp.id, pp.slug, pp.nome, pp.imagem_grande
FROM produto_planos pp JOIN produtos p ON p.id = pp.produto_id WHERE p.nome = 'Música de Presente';
