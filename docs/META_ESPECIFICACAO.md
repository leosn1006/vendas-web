# Conversões da Meta (Instagram): especificação

## Objetivo

Vamos anunciar no Instagram. A venda precisa voltar para a Meta pela API de Conversões, e o investimento das campanhas precisa entrar no ROI. A Meta deve funcionar como o Google já funciona, sem criar um fluxo paralelo.

| Etapa | Google (já existe) | Meta (a fazer) |
|---|---|---|
| De qual campanha veio | `pedidos.campaignid` | `pedidos.campaignid` |
| Qual pessoa clicou | `gclid` | `fbc`, montado do `fbclid` |
| De qual canal é a campanha | Padrão | `campanhas.plataforma = 'meta'` |
| Para onde vai a venda | Planilha (`google_ads_planilha_dns`) | Dataset (`meta_dataset_dns`) |
| Como chega lá | Service account em env var | Token em env var (`META_TOKEN_<BM>`) |

Cada produto anuncia em BM própria, para um bloqueio não derrubar os outros. Um token enxerga só as contas da sua BM.

## Parâmetros que o anúncio traz na URL

```
fbclid=<automático>&gad_campaignid={{campaign.id}}&adgroupid={{adset.id}}&creative={{ad.id}}&placement={{placement}}&utm_source=meta
```

São os nomes que o código já lê, então landings e checkout não mudam de comportamento para os demais parâmetros.

## Regras

### O que é um anúncio da Meta
- É anúncio quando a URL traz `utm_source=meta` e `gad_campaignid` numérico (no máximo 30 dígitos), sem clique do Google (`gclid`, `wbraid`, `gbraid`).
- O `fbclid` é opcional: ele pode ser removido por navegador ou redirecionamento. Sem ele, o pedido fica sem `fbc`, mas a campanha é da Meta e a venda vai com e-mail e telefone.
- `fbclid` com caracteres inválidos, longo demais ou que não seja texto é ignorado, sem erro e sem `fbc`. O anúncio continua valendo.
- O `fbclid` nunca é alterado: a Meta diferencia maiúsculas de minúsculas.
- Formato do `fbc`: `fb.1.<timestamp em ms>.<fbclid>`.
- Link orgânico (bio ou post do Instagram, com `fbclid` e sem os outros parâmetros) não é anúncio e não muda nada.

### Campanha
- No primeiro clique de anúncio, a campanha é criada em `campanhas` com `plataforma='meta'` e o ID no lugar do nome. Campanha que já existe não muda, porque o admin pode ter ajustado.
- `venda_web` nasce verdadeiro quando o clique passa pelo funil do site e falso quando vem da landing do WhatsApp (`persistir_lead`).
- A plataforma padrão de toda campanha é `google`, e as existentes continuam assim.
- O admin pode alterar a plataforma na tela de Campanhas do produto.

### Clique no pedido
- O clique fica no pedido, como o `gclid`. **Não há cookie de clique nem Pixel.**
- O clique vale enquanto o rascunho existir (24 horas, o cookie do funil que já existe).
- Último clique no rascunho (`rastrear_visita_funil`): clique novo troca campanha, `gclid` e `fbc` juntos. A venda vai para um canal só.
- Clique do Google na mesma URL vence o da Meta.
- Visita só com `wbraid` ou `gbraid`: troca a campanha e zera o `fbc` apenas se o pedido estiver com clique da Meta. Em qualquer outro caso, não muda nada, para não apagar um `gclid` que o pedido já tem. O site ainda não salva `wbraid` e `gbraid`; isso fica para outro trabalho.
- Pedido criado sem rascunho (corpo do `gerar_pix` e do `gerar_cartao`) também captura o clique. Os templates `checkout.html`, `checkout-2.html` e `dicas-quimio.html` precisam mandar `fbclid` e `utm_source` em `utmData`.
- Landing do WhatsApp (`persistir_lead`): a URL chega no corpo, e os parâmetros dela seguem a mesma regra. Falha ao gravar o clique nunca pode impedir a resposta com o número do WhatsApp.
- IP (`X-Real-IP`, depois `remote_addr`) e navegador (`User-Agent`) são gravados ao finalizar o pedido, ou ao criar o lead. Falha aqui nunca derruba o checkout.
- Pedido pago nunca muda.
- Música (`musica/adaptadores/repositorio_mysql.py`, `vincular_pedido`): o pedido novo herda a campanha do rascunho em que a música nasceu. A herança precisa levar também o `fbc`, e valer se a origem tiver `gclid` ou `fbc` e o pedido novo não tiver nenhum dos dois.

### Envio das compras
- Seleção: pedido pago (estados 0 e 1000), de campanha `plataforma='meta'`, sem `gclid`, `wbraid` e `gbraid`, ainda não aceito e pago nos últimos 6 dias. A Meta rejeita a requisição inteira se houver evento com mais de 7 dias.
- Dataset: a linha do domínio do pedido (`dns_origem`) ou, sem linha para ele, o coringa `dns='*'` do produto. Linha do domínio **inativa** bloqueia o envio, sem cair no coringa. Sem dataset, a venda não é enviada.
- Agendamento: toda hora no minuto :23, fila `baixa`, com trava no Redis como em `processar_orcamento_sheets`, sem retry. O que não foi aceito volta na hora seguinte.
- Um evento por requisição. Erro de qualquer tipo numa venda não atrapalha as outras.
- A venda só é marcada como enviada depois de `events_received >= 1`.
- Depois de 5 dias sem aceite, cada tentativa registra um erro no log, porque aos 6 ela sai da seleção sem rastro.
- `META_TEST_EVENT_CODE` preenchida: manda `test_event_code` e **não** marca como enviada.
- URL: `config.WHATSAPP_API_URL` + `<dataset>/events`, com token no cabeçalho `Authorization: Bearer`. No dev, essa URL é um endereço morto. Token nunca em log nem na URL.
- O nome da variável do token vem do admin: só aceitar `META_TOKEN_*`, para outro segredo do ambiente nunca sair para a Meta.

### Evento
```
event_name: Purchase
event_time: data_pagamento em horário de Brasília, em Unix; se estiver no futuro, usa agora (a data do comprovante do WhatsApp não é validada)
event_id: pedido-<id>
action_source: website
event_source_url: https://<dns_origem>/
custom_data: currency BRL, value = valor_conversao() de fluxo_upload_google_ads.py (site = pago; WhatsApp = R$ 10)
user_data:
  client_user_agent e client_ip_address, sem hash
  fbc, sem hash
  em: SHA256 do e-mail sem espaços nas pontas e em minúsculas
  ph: SHA256 do telefone só com dígitos, sem zeros à esquerda, com DDI
```
- Celular brasileiro salvo sem o 9º dígito (12 dígitos, começando com 55, 5º dígito de 6 a 9) ganha o 9 de volta antes do hash. Telefone fixo e de outros países não muda. O pedido sempre tem DDI.
- Sem `dns_origem` ou sem `client_user_agent`: não envia, porque a Meta exige. Registra aviso e a venda segue pendente.
- Cartão não guarda telefone: vai só com o e-mail.

### Investimento
- Roda logo depois do Google em `tasks.processar_orcamento_sheets`, mesmo com erro no Google. Erro na Meta não vira retry da task. O retry do Google chama a Meta de novo, sem duplicar dados (upsert).
- Tokens: todas as variáveis de ambiente `META_TOKEN_*` não vazias.
- Contas: `GET me/adaccounts` de cada token. Não há tabela de contas. Uma BM bloqueada não atrapalha as outras. Conta vista por dois tokens é lida uma vez.
- Dados: `GET <act_id>/insights`, com `level=campaign`, `time_increment=1`, `time_range` e campos `campaign_id,campaign_name,spend,inline_link_clicks,impressions,account_currency,date_start`. Ler todas as páginas (`paging.next` e `paging.cursors.after`).
- Período: sempre os últimos 7 dias, para entrar o gasto anterior ao primeiro clique e os ajustes da Meta. Reprocessamento manual com `data_str` lê um dia só.
- Grava com `upsert_orcamento_campanha`, na data de cada linha. Produto com `buscar_produto_id_por_campaignid`; campanha sem linha é ignorada, com aviso.
- Só grava conta em BRL. Outra moeda é ignorada, com erro no log.
- O nome da campanha vem da API e troca só o nome automático (igual ao ID). Nome dado no admin fica.
- O orçamento configurado não é gravado: o ROI usa o gasto.

### Admin
- Produto → **Conversões Meta**: listar, adicionar, ativar/desativar e remover dataset por domínio. Dataset ID só com números, variável começando com `META_TOKEN_`. Adicionar, alternar e remover só para admin, seguindo `produto_planilhas_google.html`.
- Produto → **Campanhas**: seletor de plataforma (Google ou Meta).

### Configuração
- Migration `099_conversoes_meta.sql`, idempotente, no estilo da 098: em `pedidos`, `fbc`, `client_ip`, `client_user_agent`, `data_envio_meta` e índice para a seleção; em `campanhas`, `plataforma`; tabela `meta_dataset_dns`, única por produto e domínio.
- `docker-compose.yml`: no serviço `worker-baixa`, `META_TOKEN_LSN` e `META_TEST_EVENT_CODE`. Também em `.env.example`.
- `docs/META_CONVERSOES.md` para quem vai operar, e menção no `CLAUDE.md`.

## Fora do escopo
Pixel, cookie de clique, `_fbp`, eventos além da compra, anúncio que abre o WhatsApp direto (`ctwa_clid`), retirar conversão após devolução, salvar `wbraid` e `gbraid` no site, mudanças no fluxo do Google e na exportação para a planilha, mudanças em `app/config.py` e no hook.

## Cenários que os testes precisam cobrir

**Clique**
1. URL com `fbclid`, `gad_campaignid` e `utm_source=meta`, pedido novo: grava `fbc` e campanha; cria a campanha como Meta.
2. A mesma URL sem `fbclid`: grava a campanha, sem `fbc`; cria a campanha como Meta.
3. Link da bio (só `fbclid`), em rascunho com `gclid`: nada muda.
4. `fbclid` sem `utm_source=meta`, ou sem campanha: não é anúncio.
5. `gad_campaignid` não numérico, ou com mais de 30 dígitos: não é anúncio e não cria campanha.
6. `fbclid` inválido ou que não seja texto (no corpo, por exemplo `123`): não dá erro e não grava `fbc`.
7. `gclid`, `wbraid` ou `gbraid` junto de `fbclid` e parâmetros da Meta: não é anúncio da Meta.
8. `fbclid` com maiúsculas: chega igual no `fbc`.

**Último clique no rascunho**
9. Rascunho com `gclid`, anúncio da Meta: zera o `gclid`, troca campanha e demais campos e grava o `fbc`.
10. Rascunho da Meta, clique com `gclid`: grava o `gclid`, troca a campanha e zera o `fbc`.
11. Rascunho da Meta, mesmo `fbclid` de novo (F5): nada muda.
12. Rascunho da Meta, `fbclid` novo: troca o `fbc`.
13. Rascunho da Meta, anúncio sem `fbclid` em outra campanha: troca a campanha e zera o `fbc`. Na mesma campanha: nada muda.
14. Navegação sem parâmetros: nada muda.
15. Rascunho com `gclid`, visita só com `wbraid` em outra campanha: **nada muda**, e o `gclid` fica.
16. Rascunho da Meta, visita só com `wbraid` ou `gbraid`: troca a campanha e zera o `fbc`.
17. Mesmo `gclid` de novo: nada muda.

**Lead**
18. Landing do WhatsApp com anúncio na URL: grava `fbc`, IP e navegador; campanha criada com `venda_web` falso.
19. Falha ao gravar `fbc` ou criar a campanha no lead: responde normalmente com o número do WhatsApp.

**Seleção de vendas** (SQL real, se o teste tiver banco; senão, verificar o texto da consulta)
20. Pago, campanha Meta, dataset ativo: vai.
21. Pago, campanha Google, ou com `gclid`: não vai.
22. Não pago, já enviado, ou pago há mais de 6 dias: não vai.
23. Sem dataset: não vai. Coringa: vai. Linha do domínio tem prioridade sobre o coringa. Linha do domínio inativa, com coringa ativo: não vai.

**Evento e envio**
24. Evento do site: campos acima, com valor real pago.
25. WhatsApp (estado 0): valor R$ 10.
26. E-mail e telefone normalizados e com hash; `fbc`, IP e navegador sem hash.
27. Telefone: `556181163324` vira `5561981163324`; `5561981163324` não muda; fixo `556133334444` não muda; `14155550123` não muda; vazio ou `None` dá vazio.
28. Data no futuro vira agora; `event_time` em horário de Brasília.
29. Sem domínio ou sem navegador: não monta o evento, a venda fica pendente.
30. Aceite: marca como enviada. Recusa HTTP, `events_received = 0`, JSON que não é objeto ou falha de conexão: não marca e conta como erro.
31. Exceção inesperada numa venda: as seguintes continuam.
32. Modo teste: manda o código e não marca.
33. Token: só `META_TOKEN_*`. `SECRET_KEY` ou variável vazia: não chama a Meta e conta como erro. Nunca no corpo nem na URL.
34. Aviso de janela: com 5 dias sim, com 4 não.

**Investimento**
35. Grava na tabela do Google, com cada dia na sua data; atualiza o nome.
36. Descobre as contas pelo token; lê todas as páginas.
37. Sem data: últimos 7 dias. Com data: um dia.
38. Campanha sem linha e moeda diferente de BRL: não grava.
39. BM bloqueada e erro numa conta: as outras continuam. Conta vista por dois tokens é lida uma vez.
40. Erro na Meta não vira retry da task; erro no Google não impede a Meta.

**Compatibilidade**
41. Música: pedido novo herda `fbc` e campanha da origem; pedido que já tem clique não muda; origem sem clique não muda nada.
42. Exportação do Google: pedido com `gclid` continua saindo igual; pedido da Meta, sem `gclid`, não sai.
