-- Lembretes da Música por PESSOA (e-mail), não por música (28/10/2026, docs/MUSICA.md "Lembretes"). A série de cada
-- etapa (letra, prévia, checkout) é de quem recebe os e-mails: uma música nova, uma "outra versão" ou uma música que
-- muda de etapa não recomeçam nem duplicam a série. De `musicas` (095) continua valendo só `lembrete_etapa`: a etapa
-- mais avançada em que ESTA música já recebeu lembrete (ela não volta para uma anterior); lembrete_desde,
-- lembretes_enviados, lembrete_ultimo_em e sem_lembretes ficam sem uso. Idempotente.
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS musica_lembretes (
    email_chave  VARCHAR(200) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'LOWER(TRIM(email)) — regras.chave_email',
    etapa        VARCHAR(10)  COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'letra | previa | checkout',
    inicio       DATETIME NOT NULL COMMENT 'Quando a série desta etapa começou (a validade de 3 dias)',
    desde        DATETIME NOT NULL COMMENT 'O relógio dos 15 min / 3 h / 24 h (recomeça quando outra música dela assume)',
    enviados     TINYINT NOT NULL DEFAULT 0 COMMENT '0 a 3',
    ultimo_em    DATETIME NULL,
    musica_id    INT NULL COMMENT 'Música do último lembrete',
    PRIMARY KEY (email_chave, etapa),
    KEY idx_musica_lembretes_inicio (inicio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS musica_lembretes_saida (
    email_chave  VARCHAR(200) COLLATE utf8mb4_unicode_ci NOT NULL PRIMARY KEY,
    em           DATETIME NOT NULL COMMENT '"Não quero mais estes lembretes" — vale 90 dias'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- O que a 095 já gravou por música vira a série da pessoa: em cada etapa, a música que mais avançou (mais lembretes;
-- empatando, a mais recente) — relógio, contagem e música vêm da MESMA linha; o início (validade) é o mais antigo dela
-- naquela etapa.
INSERT IGNORE INTO musica_lembretes (email_chave, etapa, inicio, desde, enviados, ultimo_em, musica_id)
SELECT chave, lembrete_etapa, inicio, lembrete_desde, lembretes_enviados, ultimo, id
FROM (SELECT LOWER(TRIM(email)) AS chave, lembrete_etapa, lembrete_desde, lembretes_enviados, id,
             MAX(lembrete_ultimo_em) OVER (PARTITION BY LOWER(TRIM(email))) AS ultimo,
             MIN(lembrete_desde) OVER (PARTITION BY LOWER(TRIM(email)), lembrete_etapa) AS inicio,
             ROW_NUMBER() OVER (PARTITION BY LOWER(TRIM(email)), lembrete_etapa
                                ORDER BY lembretes_enviados DESC, lembrete_desde DESC, id DESC) AS ordem
      FROM musicas
      WHERE email IS NOT NULL AND lembrete_etapa IS NOT NULL AND lembrete_desde IS NOT NULL
        AND criado_em >= NOW() - INTERVAL 6 DAY) x
WHERE ordem = 1;

-- Quem já pediu para parar (095, por música): vale para a pessoa, 90 dias contados de agora.
INSERT IGNORE INTO musica_lembretes_saida (email_chave, em)
SELECT DISTINCT LOWER(TRIM(email)), NOW() FROM musicas WHERE email IS NOT NULL AND sem_lembretes = 1;

SELECT etapa, COUNT(*) AS pessoas, SUM(enviados = 3) AS series_encerradas FROM musica_lembretes GROUP BY etapa;
