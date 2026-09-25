---
name: analise-funil-whatsapp
description: Analisa o funil de vendas do WhatsApp de um produto no banco de PRODUÇÃO (leads, conversas, link enviado, comprovante, pago), por dia, por número e por provedor (API oficial da Meta x gateway WhatsApp Web), e checa pedidos presos em estado intermediário. Use quando o usuário pedir para "analisar/conferir os números do produto X", "quantos pedidos respondemos com o chip Y", "comparar Meta com WhatsApp Web", "ver se o web está vendendo" ou "por que caiu a venda". Não serve para vendas do site (fluxo web, estado 1000).
---

# Análise do funil de vendas no WhatsApp

Pegadinha nº 1: **você não acessa o banco de produção.** O usuário roda o comando no Hetzner
(`~/vendas-web`) e cola a saída. Entregue o comando e espere o resultado; se ele colar só o
comando (sem tabela embaixo), não rodou. Nunca escreva números que ele não mostrou. O banco de
dev é uma cópia de produção (defasada): serve para **validar a sintaxe**, não para concluir nada.

As consultas prontas, já testadas, estão em `consultas.md` (mesma pasta). Troque `produto_id = 11`
pelo produto pedido e a janela `INTERVAL 1 DAY` (ontem + hoje) conforme o caso.

## O que cada coluna significa (não deduza: já se errou aqui)

- `fluxo_inicial`: `'wpp'` = WhatsApp, `'web'` = site. **Sempre filtrar `= "wpp"`**: pedido do site
  também guarda um número de WhatsApp (para a confirmação depois do pagamento).
- `data_contato_site` = criação do pedido (agrupe por dia com ela; `data_criacao` **não existe**).
  `data_pedido` = quando o cliente escreveu de fato. Horários no fuso do servidor (Brasília).
- Marcos do funil, em ordem: `data_pedido` (conversou) → `interesse_produto = 1` (disse sim) →
  `data_envio_pedido` (fluxo `pedido` terminou: link/produto enviado) → `data_pagamento`.
- Estados: `0` pago (WhatsApp) · `1000` pago (site) · `1` iniciado (pode ser só clique, ou fluxo que
  falhou e reverteu) · `2` introdução concluída · `3` aguardando pagamento · `4` follow-up enviado ·
  `11`/`12`/`13` travas do orquestrador (introdução / fluxo pedido / comprovante em análise).
- `path_comprovante` é **string vazia**, não NULL, em pedido sem comprovante: use
  `NULLIF(path_comprovante, "")`. Um `COUNT(path_comprovante)` puro conta todos os pedidos.
- **`data_pagamento` no WhatsApp = comprovante aceito pela IA** (aceita qualquer imagem), não
  dinheiro recebido; o que vale é o financeiro. Serve para comparar canais, não como receita.

## Formato do comando (para não quebrar ao colar)

- Aspas do SQL como `\"` dentro do `'...'` do shell; **nenhuma aspa simples no SQL**.
- **Sem acentos** em `LIKE` e em rótulos: o cliente `mysql` do container fala latin1 (acento sai
  como `?` e o `LIKE` não casa).
- Um comando por vez, com o título do que ele mede. Pedir que cole a saída inteira.

## Roteiro (nesta ordem; pare quando a pergunta estiver respondida)

1. **Números do produto** (consulta 1): provedor, `status_api`, `contador_uso`. Chip do gateway sem
   `CONNECTED` não entra no sorteio de leads.
2. **Funil por provedor e dia** (consulta 2): leads → conversas → sim → link → pagos.
3. **Por número** (consulta 3), se um chip parecer puxar o resultado.
4. **Conferência do comprovante** (consulta 4): `arquivo_comprovante` x `marcados_pagos` x `estado_0`.
5. **Saúde do fluxo** (consultas 5 a 7), quando algo destoa: pagos presos em 13, estado dos pagos e
   datas de pagamento no futuro.

## Como ler (o que já enganou)

- **Compare taxas entre provedores no MESMO dia**, nunca um dia contra o outro: o comprovante chega
  horas depois do link, então o dia corrente sempre parece pior.
- **Volume pequeno engana.** Com ~20 links por grupo, 5 pontos de diferença é ruído (os números da
  Meta variaram de 28% a 45% entre si no mesmo dia). Abaixo de ~30 links por grupo, não conclua.
- `sim_sem_link` deve ser **0**. Se não for, o fluxo `pedido` travou (já aconteceu com pedido sem
  `dns_origem`); o problema não é o cliente nem o link.
- `pago_sem_arquivo` só no gateway = o download do comprovante pelo gateway está falhando.
- `estado_0` menor que `marcados_pagos` = pago que saiu do 0 (bugs conhecidos em
  `project_comprovante_estado_13_e_datas` na memória: pago preso no 13, pago sobrescrito para 3/4,
  data com dia e mês trocados).
- Chip novo do gateway recebe fatia **igual** de leads desde o primeiro dia: se ele tiver volume
  acima do que o anterior aguentou antes de ser banido, avise do risco de ban.

## Resposta ao usuário

Tabela curta (por provedor e dia) + conclusão honesta: o que os números mostram, o que **não**
provam (amostra, dia parcial, `pagos` ≠ dinheiro) e qual dado falta para decidir. Se achar bug
novo nos dados, diga o mecanismo com evidência e proponha reparo **sem executar nada**: UPDATE em
produção é decisão do usuário, e mexer em estado/`data_envio_google_ads` afeta a exportação de
conversões ao Google Ads (ROI).
