-- Lembretes da Música por etapa do funil (27/10/2026, docs/MUSICA.md "Lembretes"): letra, prévia e checkout, cada
-- uma com e-mails 15 min, 3 h e 24 h depois de a música entrar na etapa. Substitui lembrete1_em/lembrete2_em (só da
-- prévia; ficam sem uso). Idempotente.
SET NAMES utf8mb4;

SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'musicas' AND COLUMN_NAME = 'lembrete_etapa');
SET @sql = IF(@tem = 0, 'ALTER TABLE musicas
    ADD COLUMN lembrete_etapa VARCHAR(10) NULL COMMENT ''letra | previa | checkout: a etapa dos lembretes em curso'' AFTER lembrete2_em,
    ADD COLUMN lembrete_desde DATETIME NULL COMMENT ''Quando a música entrou nesta etapa (o relógio dos 15 min / 3 h / 24 h)'' AFTER lembrete_etapa,
    ADD COLUMN lembretes_enviados TINYINT NOT NULL DEFAULT 0 COMMENT ''Quantos lembretes desta etapa já saíram (0 a 3)'' AFTER lembrete_desde,
    ADD COLUMN lembrete_ultimo_em DATETIME NULL AFTER lembretes_enviados,
    ADD COLUMN sem_lembretes TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''Ela pediu para não receber mais lembretes'' AFTER lembrete_ultimo_em', 'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

SET @tem = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'musicas' AND COLUMN_NAME = 'checkout_aberto_em');
SET @sql = IF(@tem = 0, 'ALTER TABLE musicas ADD COLUMN checkout_aberto_em DATETIME NULL
    COMMENT ''1ª vez que o checkout DESTA música abriu (o rascunho do funil é do navegador, não da música)'' AFTER sem_lembretes',
    'SELECT 1');
PREPARE p FROM @sql; EXECUTE p; DEALLOCATE PREPARE p;

-- Músicas em andamento no deploy: começam na etapa em que estão, com o relógio de quando entraram nela (e não do
-- deploy), para ninguém receber um "acabou de ficar pronta" de algo de dias atrás.
-- Checkout: há pedido da música esperando pagamento (1002) — o relógio é o do pedido. (Só abrir o checkout passa a
-- ser gravado na própria música a partir de agora, em checkout_aberto_em; o rascunho do funil é do navegador.)
UPDATE musicas m
JOIN (SELECT mp.musica_id, MAX(p.data_ultima_atualizacao) AS quando FROM musica_pedidos mp
      JOIN pedidos p ON p.id = mp.pedido_id WHERE p.estado_id = 1002 GROUP BY mp.musica_id) a ON a.musica_id = m.id
SET m.lembrete_etapa = 'checkout', m.lembrete_desde = a.quando
WHERE m.lembrete_etapa IS NULL AND m.liberada_em IS NULL;
-- Prévia: herda os lembretes que já recebeu no modelo antigo (1 h → o 1º; 24 h → todos).
UPDATE musicas
SET lembrete_etapa = 'previa', lembrete_desde = COALESCE(gerando_desde, atualizado_em),
    lembretes_enviados = IF(lembrete2_em IS NOT NULL, 3, IF(lembrete1_em IS NOT NULL, 1, 0))
WHERE lembrete_etapa IS NULL AND liberada_em IS NULL AND status = 'previa_pronta';
UPDATE musicas SET lembrete_etapa = 'letra', lembrete_desde = atualizado_em
WHERE lembrete_etapa IS NULL AND liberada_em IS NULL AND status = 'letra_pronta';

SELECT lembrete_etapa, COUNT(*) AS musicas FROM musicas WHERE liberada_em IS NULL GROUP BY lembrete_etapa;
