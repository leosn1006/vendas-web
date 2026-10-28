-- Miniaturas dos order bumps da Música no checkout (28/10/2026): static/images/musica-bump-qrcode.webp (cartão com QR
-- e nota musical) e musica-bump-entrega.webp (envelope + WhatsApp). Aparecem a 64×64 (geradas a 256×256). Só
-- preenche entregável ainda sem imagem — a escolhida no admin fica. Idempotente.
SET NAMES utf8mb4;

UPDATE entregaveis
SET imagem_pequena = CASE recurso WHEN 'qrcode' THEN 'musica-bump-qrcode.webp'
                                  WHEN 'entrega_email' THEN 'musica-bump-entrega.webp' END
WHERE tipo = 'musica' AND recurso IN ('qrcode', 'entrega_email')
  AND (imagem_pequena IS NULL OR imagem_pequena = '');

SELECT id, recurso, nome_venda, imagem_pequena FROM entregaveis WHERE tipo = 'musica';
