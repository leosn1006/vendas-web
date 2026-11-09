# Consultas prontas (testadas contra a cópia de produção em 24/09/2026)

Todas rodam no Hetzner, em `~/vendas-web`, no formato abaixo. Ajuste `produto_id` e a janela.
Somente leitura: nenhuma altera dado. Sem acentos de propósito (ver SKILL.md).

## 1. Números do produto

```bash
docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT telefone, provedor, status_api, contador_uso, created_at
FROM telefones_produto WHERE produto_id = 11
ORDER BY provedor, created_at;"'
```

## 2. Funil por provedor e dia

```bash
docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT dia, provedor,
       COUNT(*)                                                 AS leads,
       COUNT(data_pedido)                                       AS conversas,
       SUM(interesse_produto = 1)                               AS disseram_sim,
       COUNT(data_envio_pedido)                                 AS receberam_link,
       SUM(interesse_produto = 1 AND data_envio_pedido IS NULL) AS sim_sem_link,
       COUNT(data_pagamento)                                    AS pagos,
       COALESCE(SUM(CASE WHEN data_pagamento IS NOT NULL THEN valor_pago END), 0) AS receita
FROM (
    SELECT DATE(p.data_contato_site) AS dia,
           COALESCE((SELECT t.provedor FROM telefones_produto t
                     WHERE t.api_phone_number_id = p.phone_number_id LIMIT 1), \"sem_numero\") AS provedor,
           p.data_pedido, p.interesse_produto, p.data_envio_pedido, p.data_pagamento, p.valor_pago
    FROM pedidos p
    WHERE p.produto_id = 11 AND p.fluxo_inicial = \"wpp\"
      AND p.data_contato_site >= CURDATE() - INTERVAL 1 DAY
) x
GROUP BY dia, provedor
ORDER BY dia, provedor;"'
```

## 3. Por número e dia, com o arquivo do comprovante

```bash
docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT DATE(p.data_contato_site) AS dia,
       (SELECT t.telefone FROM telefones_produto t WHERE t.api_phone_number_id = p.phone_number_id LIMIT 1) AS telefone,
       COUNT(*)                                                          AS leads,
       COUNT(p.data_pedido)                                              AS conversas,
       COUNT(p.data_envio_pedido)                                        AS receberam_link,
       COUNT(NULLIF(p.path_comprovante, \"\"))                            AS arquivo_comprovante,
       COUNT(p.data_pagamento)                                           AS marcados_pagos,
       SUM(p.estado_id = 0)                                              AS estado_0,
       COUNT(CASE WHEN p.data_pagamento IS NOT NULL
                   AND NULLIF(p.path_comprovante, \"\") IS NULL THEN 1 END) AS pago_sem_arquivo
FROM pedidos p
WHERE p.produto_id = 11 AND p.fluxo_inicial = \"wpp\"
  AND p.data_contato_site >= CURDATE() - INTERVAL 1 DAY
GROUP BY dia, p.phone_number_id
ORDER BY dia, telefone;"'
```

## 4. Pedidos respondidos por um número num dia (ex.: chip banido)

```bash
docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT COUNT(DISTINCT p.id)                                     AS pedidos_totais_do_numero,
       COUNT(DISTINCT CASE WHEN p.estado_id >= 2 THEN p.id END)  AS passaram_da_introducao,
       COUNT(DISTINCT CASE WHEN m.tipo_mensagem = \"enviada\"
                            AND DATE(m.data_mensagem) = CURDATE() - INTERVAL 1 DAY
                       THEN m.pedido_id END)                    AS respondidos_ontem
FROM pedidos p LEFT JOIN mensagens_pedidos m ON m.pedido_id = p.id
WHERE p.phone_number_id = \"web-5561982402450\";"'
```

Nota: estado 1 pode ser só um clique na página de vendas (sem conversa) **ou** um fluxo que falhou e
reverteu; estado 0 é pago, então `estado_id >= 2` não é "funil monotônico".

## 5. Pagos presos no estado 13, por mês (e quantos ainda iriam ao Google Ads)

```bash
docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT DATE_FORMAT(data_pagamento, \"%Y-%m\") AS mes, COUNT(*) AS presos_no_13,
       SUM((gclid IS NOT NULL AND gclid <> \"\") OR (wbraid IS NOT NULL AND wbraid <> \"\")
           OR (gbraid IS NOT NULL AND gbraid <> \"\"))                       AS com_id_do_google,
       SUM(data_envio_google_ads IS NULL
           AND ((gclid IS NOT NULL AND gclid <> \"\") OR (wbraid IS NOT NULL AND wbraid <> \"\")
                OR (gbraid IS NOT NULL AND gbraid <> \"\")))                 AS a_exportar,
       SUM(valor_pago)                                                      AS valor
FROM pedidos
WHERE fluxo_inicial = \"wpp\" AND estado_id = 13
  AND data_pagamento IS NOT NULL AND data_pagamento <= NOW()
GROUP BY mes ORDER BY mes;"'
```

## 6. Estado dos pedidos pagos nos últimos 14 dias

Esperado: quase tudo no estado 0. Pago em 3 ou 4 = sobrescrito depois de pagar; em 13 = preso.

```bash
docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT estado_id, COUNT(*) AS pedidos FROM pedidos
WHERE fluxo_inicial = \"wpp\" AND data_pagamento >= CURDATE() - INTERVAL 14 DAY
GROUP BY estado_id ORDER BY pedidos DESC;"'
```

## 7. Datas de pagamento no futuro (preview da correção dia/mês; só SELECT)

```bash
docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT id, data_contato_site, data_pagamento AS registrada,
       STR_TO_DATE(CONCAT(YEAR(data_pagamento), \"-\", LPAD(DAY(data_pagamento),2,\"0\"), \"-\",
                          LPAD(MONTH(data_pagamento),2,\"0\"), \" \", TIME(data_pagamento)),
                   \"%Y-%m-%d %H:%i:%s\") AS trocada
FROM pedidos
WHERE data_pagamento > NOW() AND DAY(data_pagamento) <= 12
HAVING trocada > data_contato_site AND trocada <= NOW()
ORDER BY id;"'
```

Pedidos com data futura e dia > 12 não são troca de dia/mês (PIX agendado ou leitura errada): revisar
à mão.

## 8. A/B da contribuição no site × WhatsApp (docs/CONTRIBUICAO_WEB.md)

Cliques por braço desde `INTERVAL 7 DAY`, sem os de QA (`teste = 0`). Pago no braço estante = pedido 0/1000 vinculado
à entrega (`pedidos_vinculados`) ou com o mesmo e-mail e pago depois do clique; no braço wpp = o próprio lead em estado 0
(comprovante aceito pela IA). A métrica é `receita / cliques`. O mesmo dado aparece no admin (ROI do produto).

```bash
docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT braco, SUM(cliques) AS cliques, COUNT(nome_em) AS nome, COUNT(audio1_play_em) AS audio1, COUNT(email_em) AS email,
       COUNT(estante_em) AS estante, COUNT(audio2_play_em) AS audio2, COUNT(checkout_em) AS checkout,
       COUNT(valor) AS pagos, COALESCE(SUM(valor), 0) AS receita, ROUND(COALESCE(SUM(valor), 0) / SUM(cliques), 2) AS receita_clique
FROM (
    SELECT cp.*, CASE WHEN cp.braco = \"wpp\" THEN IF(p.estado_id = 0, p.valor_pago, NULL)
           ELSE (SELECT pg.valor_pago FROM pedidos pg
                 WHERE pg.produto_id = cp.produto_id AND pg.estado_id IN (0, 1000) AND pg.id <> p.id
                   AND (pg.id IN (SELECT pv.pedido_id_adquirido FROM pedidos_vinculados pv WHERE pv.pedido_id_origem = cp.pedido_id)
                        OR (COALESCE(p.email, \"\") <> \"\" AND pg.email = p.email AND pg.data_pagamento >= cp.criado_em))
                 ORDER BY pg.id LIMIT 1) END AS valor
    FROM contribuicao_pedidos cp JOIN pedidos p ON p.id = cp.pedido_id
    WHERE cp.produto_id = 11 AND cp.teste = 0 AND cp.criado_em >= CURDATE() - INTERVAL 7 DAY
) x
GROUP BY braco;"'
```
