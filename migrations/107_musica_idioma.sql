-- Música internacional (Fase 1, o site em espanhol do México): idioma da música e do produto (docs/MUSICA.md,
-- seção "Idiomas"). pt-BR é o padrão: o Brasil continua igual. Idempotente.
SET NAMES utf8mb4;

-- Idioma da música: gravado na criação (pelo endereço do quiz: /musica = pt-BR, /mx/cancion = es-MX). Tudo depois
-- (letra, som, prévia, lembretes) sai daqui, nunca da URL.
SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'musicas' AND COLUMN_NAME = 'idioma');
SET @sql = IF(@tem = 0, 'ALTER TABLE musicas
    ADD COLUMN idioma VARCHAR(5) NOT NULL DEFAULT ''pt-BR'' COMMENT ''Idioma e país: pt-BR, es-MX...'' AFTER produto_id', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

-- Idioma do produto: a Música de cada idioma é um produto próprio (campanha, ofertas, remetente). Genérico: vale
-- também para um e-book vendido fora do Brasil.
SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'produtos' AND COLUMN_NAME = 'idioma');
SET @sql = IF(@tem = 0, 'ALTER TABLE produtos
    ADD COLUMN idioma VARCHAR(5) NOT NULL DEFAULT ''pt-BR'' COMMENT ''Idioma e país do público: pt-BR, es-MX...''', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

SHOW COLUMNS FROM musicas LIKE 'idioma';
SHOW COLUMNS FROM produtos LIKE 'idioma';
