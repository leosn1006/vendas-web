# Hotmart: checkout de fora do Brasil

No Brasil continua o nosso checkout (PIX/cartão). Fora do Brasil a venda passa pela Hotmart, que é a vendedora legal
(Merchant of Record): ela recolhe os impostos de lá e aceita os meios locais (no México: cartão, OXXO, SPEI). O
primeiro produto é a Música do México (`/mx/cancion`, produto `es-MX`, migration 108).

## Fluxo

1. A cliente clica em comprar na prévia (`/mx/cancion/comprar/<token>/<oferta>`) e **nós criamos o pedido** (1001,
   `metodo_pagamento = 'hotmart'`, plano da oferta, a música vinculada, o e-mail da música).
2. Redirecionamos para o **link da oferta** na Hotmart com `xcod=<guid do pedido>` (+ `email`) e guardamos o guid
   no cookie `musica_hotmart`.
3. A cliente paga na Hotmart e a Hotmart chama **`POST /hotmart/webhook`** (`app/hotmart/`).
4. O webhook acha o pedido pelo `xcod`, confere a oferta e, se pagou, faz o mesmo que o PIX e o cartão:
   `confirmar_pagamento_web` (estado 1000) + `tasks.enviar_email_entrega` (libera a Música/apps e manda o e-mail).

## Webhook (`app/hotmart/`)

- Cadastro no painel da Hotmart: versão **2.0.0**, URL `https://<domínio>/hotmart/webhook`, eventos de compra.
- Proteção: o hottok do painel vem no cabeçalho `X-HOTMART-HOTTOK` e tem de bater com `HOTMART_HOTTOK` no `.env`
  (só no serviço `app`). Vazio = webhook desligado (404). O corpo não é assinado.
- Todo aviso fica cru em `pagamento_hotmart_eventos` (o `evento_id` evita processar duas vezes). Erro inesperado →
  500 e a Hotmart reenvia; o reenvio é processado de novo sem repetir efeito (a confirmação só "ganha" uma vez).
- Cada compra (transação) tem uma linha em `pagamento_hotmart`, com a última situação.

| Evento | O que acontece com o pedido |
|---|---|
| `PURCHASE_APPROVED` | pago (1000), entrega enfileirada uma vez |
| `PURCHASE_COMPLETE` (fim da garantia) | `liberado_em` na compra; se ainda não estava pago, paga |
| `PURCHASE_BILLET_PRINTED` ou status `WAITING_PAYMENT`/`PRINTED_BILLET` | aguardando OXXO/SPEI (**1010**), se não pago |
| `PURCHASE_CANCELED`, `PURCHASE_EXPIRED` | cancelado/expirado (**1011**), nunca um pedido já pago |
| `PURCHASE_REFUNDED`, `PURCHASE_CHARGEBACK`, `PURCHASE_PROTEST` | só registra (Estante continua aberta) |
| order bump | ignorado na 1ª versão (só registra) |

**Conferências que impedem a confirmação** (resultado no `pagamento_hotmart_eventos.resultado`, ERROR no log):
- `sem_pedido`: sem `xcod` ou guid desconhecido — a compra fica gravada com `pedido_id` NULL para conferir à mão.
- `oferta_divergente`: a oferta paga (`purchase.offer.code`) não está em `hotmart_ofertas` ou é de outro
  produto/plano do pedido (senão daria para pagar a oferta barata com o `xcod` de um pedido do plano caro).

## Ofertas (`hotmart_ofertas`)

De-para oferta da Hotmart → plano nosso. Um plano pode ter várias (ex.: videoclipe cheio e com desconto do popup).
Cadastro em **Admin → Hotmart → Ofertas** (o código é o `off=` do link da oferta). Desativar só tira a oferta dos
links: quem já pagou continua recebendo.

## Moeda e repasse

- **Os campos em reais do pedido não mudam de significado**: `valor_pago`, `valor_liquido_pagamento` e
  `data_repasse` ficam em reais, então ROI, Financeiro e Google Ads funcionam igual.
- O original fica em `pagamento_hotmart`: `valor`/`moeda` (o que a cliente pagou), `taxa_hotmart` e `liquido` (as
  comissões MARKETPLACE e PRODUCER, cada uma com a sua moeda), `taxa_brl`, `fonte_taxa`, `valor_brl`, `liquido_brl`.
- Conversão para reais (`hotmart/cambio.py`), nesta ordem: já em BRL → `currency_conversion` que a Hotmart mandar na
  nossa comissão → cotação de referência (`cotacao.cotacao_em_reais`: **PTAX do BCB**, que só tem 10 moedas — USD,
  EUR, GBP…; fora dela a **referência do BCE**, que cobre MXN e INR; a naira não tem) → última taxa gravada da mesma
  moeda → `pendente` (valor 0 e ERROR no log). **A entrega nunca espera o câmbio.**
- **Previsão de repasse**: o webhook não traz a data em que a Hotmart paga a empresa. `previsao_repasse` (e
  `pedidos.data_repasse`) = aprovação + `HOTMART_DIAS_REPASSE` (padrão 15, o prazo de saque de vendas em outra moeda)
  ou o fim da garantia, se for mais tarde. `liberado_em` = chegou o `PURCHASE_COMPLETE`.

## Documentação oficial e o que ainda falta conferir

Os campos foram conferidos com a página oficial **"Eventos de pedidos" 2.0.0** do Hotmart Developers
(developers.hotmart.com/docs, que só abre no navegador). O que ela esclarece:
- `price` = valor da oferta na compra; `full_price` = total pago **com juros e taxas** do parcelamento. O
  `valor_pago` usa o `price`.
- Order bump: a compra **principal** também vem com `is_order_bump = true`, com `parent_purchase_transaction` vazio
  (tabela) ou igual à própria transação (JSON de exemplo). Só é bump de verdade quando a mãe é **outra** transação.
- `commissions.source` na tabela: PRODUCER, COPRODUCER, AFFILIATE, ADDON — mas o JSON de exemplo traz MARKETPLACE
  (a taxa da Hotmart). Tratamos os dois casos (`taxa_hotmart` nulo quando não vem).
- **Moedas** (JSON de exemplo, em `tests/hotmart/exemplo_oficial_purchase_approved.json`): a taxa da Hotmart pode vir
  em BRL e o **nosso líquido em USD**, com `currency_conversion` = `{converted_value: 16.34, converted_to_currency:
  BRL, conversion_rate: 5.271103}` — reais por 1 unidade da moeda **da comissão**. `liquido_brl` usa o
  `converted_value`; a taxa da compra só sai da `conversion_rate` quando a compra está na mesma moeda da comissão.
- Fiscal: `invoice_by` (HOTMART ou SELLER emite a nota) e `business_model` (R = a Hotmart emite; A = nós, pela entidade
  da Hotmart no exterior; I = nós, pela entidade no Brasil) ficam em `nota_fiscal_por` / `modelo_fiscal`. Conversa com
  o contador.
- A Hotmart guarda o histórico dos avisos por 60 dias e tem botão de teste no painel; a API tem sandbox
  (`sandbox.hotmart.com`).

**Confirmado na 1ª venda real** (HP0277856500, 25/11/2026, MX$ 50 no cartão): `price` 50 MXN (sem IVA), `full_price`
58 MXN (com o IVA de 16%), taxa da Hotmart **US$ 0,50 = 20%** (`hotmart_fee.percentage` na API), **nosso líquido em
USD** (2,01) com `currency_conversion` para BRL (11,69 a 5,815299), `business_model` **"A"** (nós emitimos a nota,
pela entidade da Hotmart no exterior). Ainda falta ver um OXXO/SPEI real (`payment.type` e o evento de "gerado").

## Próximas etapas

- Order bumps; devolução no Financeiro. **Hoje um reembolso/chargeback não muda o pedido**: ele continua pago e
  somando no ROI (a `pagamento_hotmart.status` mostra REFUNDED/CHARGEBACK e a tela conta os reembolsos).

## Botão e página de obrigado (`hotmart/checkout.py` + `musica/rotas.py`, 26/11/2026)

- **Prévia**: fora do Brasil, `_planos_e_oferta_hotmart` mostra cada plano que tem oferta **`uso = 'botao'`** em
  `hotmart_ofertas` (com `produto_hotmart`, `preco` e `moeda`, que montam o link e o preço "MX$ 149"); o popup
  "última chance" usa a oferta **`popup`** (do plano com videoclipe, mais cara que o botão da música e mais barata
  que o botão dela). Sem oferta de botão = "venda fechada". Cadastro em Admin → Hotmart → Ofertas (uma oferta de
  botão por plano: salvar outra tira a anterior).
- **`GET /<prefixo>/comprar/<token>/<oferta>`**: confere a música (prévia pronta, não comprada) e a oferta
  (ativa, botão/popup, do produto); reaproveita o pedido Hotmart aberto da mesma música e plano (1001/1010/1011) ou
  cria um; liga a música (`vincular_ao_pedido`, que herda GCLID/fbc do rascunho da landing); cookie e 302 para
  `https://pay.hotmart.com/<produto_hotmart>?off=<oferta>&xcod=<guid>&email=...`. Limite de 30 cliques por IP/hora.
- **Página de obrigado** (cadastrar no painel da Hotmart, no produto): `https://<domínio>/mx/cancion/gracias`. Lê o
  cookie e consulta `GET /<prefixo>/api/compra-hotmart` (só o pedido do cookie, nunca guid pela URL) a cada 3 s:
  pago → área da compra (`/compra/<guid>`); OXXO/SPEI gerado → "te enviaremos por correo"; sem cookie ou depois de
  2 min → "te enviamos el enlace por correo".
- O webhook grava o `buyer.email` da Hotmart no pedido sem e-mail antes da entrega.
- **Popup**: o link leva `?oferta=<token assinado>` (o mesmo `web/oferta.py`, 24 h); sem ele, o código da oferta com
  desconto sozinho não vende (volta para a prévia).
- Pré-carregamento (`Sec-Purpose`/`Purpose: prefetch`) não cria pedido. Pedido aguardando OXXO/SPEI (1010) **não** é
  reaproveitado num novo clique (o mesmo xcod em dois pagamentos cobraria duas vezes); o cancelado (1011)
  reaproveitado volta a 1001 (senão a página de obrigado diria "cancelado" durante o pagamento novo).
- **Pagamento duplicado** → resultado `duplicado` em "Para conferir", para reembolsar na Hotmart: (a) outra
  transação pagou o mesmo pedido ANTES desta (só a que veio depois é marcada; os avisos seguintes da original, como o
  COMPLETE, seguem normais); (b) a música do pedido já foi paga por OUTRO pedido (ex.: OXXO num pedido e cartão em
  outro). A entrega não duplica (é idempotente).
- A prévia só mostra ofertas na moeda do país (`idiomas.py` → `moeda`): preço, ordem e economia nunca misturam
  moedas.
- Página de obrigado: cancelado/recusado (1011) → "o pagamento não foi concluído" + volta para a música; depois de
  2 min sem confirmação → "assim que confirmar, enviamos por e-mail" (nunca diz que já enviou).
- Lembretes da Música não vão para quem tem pedido Hotmart 1010 (já está pagando o OXXO).
- Na Hotmart: Produtos → o produto → Ferramentas → Configurações de pagamento → aba **Pós-venda** → "Onde será?" =
  **Externa**, com a URL de obrigado acima (para compra aprovada e para boleto/OXXO gerado).
- `idiomas.py`: es-MX `'vende': True` (lembretes por e-mail ligados).

## Conciliação (`hotmart/conciliacao.py`, fase 2b, 26/11/2026)

- Roda **de hora em hora** (beat `hotmart-conciliar`, minuto 17, fila `baixa`) e pelo botão **Conciliar agora** em
  Admin → Hotmart, que só agenda a mesma tarefa no worker (são dezenas de chamadas: na página passaria do tempo do
  Gunicorn). Execução que não terminou em 30 min é marcada "interrompida" na próxima. Período: últimos `HOTMART_DIAS_CONCILIACAO` dias (45). Credencial em `HOTMART_CLIENT_ID`,
  `_SECRET`, `_TOKEN` (no `app` e no `worker-baixa`); vazia = não roda. `HOTMART_API_URL` vazio = produção.
- Busca `history`, `price/details` e `commissions` para cada status (sem `transaction_status` a API só devolve
  APPROVED/COMPLETE) e junta pela transação. **Só GET** (`hotmart/api.py`).
- Venda que o webhook não trouxe, ou **paga na Hotmart com o pedido ainda aberto** (webhook perdido): vira um aviso
  no formato do webhook (`evento_id = conciliacao:<transação>:<status>`) e passa pelo mesmo `servico.processar()` —
  confere a oferta, converte para reais, **confirma e entrega**. Preço sem IVA = `price/details.base`.
- Venda que **não paga** e o webhook não trouxe: só muda o pedido se for a transação **mais recente** daquele `xcod`
  (um cartão recusado antigo não cancela o pedido que espera o OXXO); as outras só são registradas
  (`EVENTO_SO_REGISTRO`, `evento_id` terminado em `:registro`).
- **Order bump**: a API não diz o que é bump. Uma venda de oferta não cadastrada cujo pedido (`xcod`) tem outra
  venda com oferta cadastrada é tratada como bump: só registrada, nunca confirma. As de oferta cadastrada são
  aplicadas primeiro. Linha já gravada como bump pelo webhook nunca é confirmada pela conciliação.
- Se o aviso do webhook da venda já está em "Para conferir", a conciliação não cria um segundo aviso igual.
- Pedido pago pela Hotmart, com e-mail e sem entrega, entre 30 min e 6 h depois do pagamento (o agendamento da
  entrega falhou): agenda a entrega de novo (idempotente pelo `data_envio_ebook`; contado em
  `hotmart_conciliacoes.reentregas`).
- "Reprocessar" só aceita aviso `sem_pedido` / `oferta_divergente` / `erro` (nunca um `processando` ou `ok`).
- Grava o que a API diz em `pagamento_hotmart.api_*` (total com IVA, IVA, taxa e %, líquido, garantia, xcod, oferta)
  e a **divergência** que sobrar: status (ex.: REFUNDED na API sem o aviso), valor cheio, líquido, xcod ≠ guid, sem
  pedido, paga com pedido não pago. Divergência só aparece na tela. Cada execução fica em `hotmart_conciliacoes`.
- Atenção: o `history.price` é o valor **com IVA** (58), o `price` do webhook é **sem IVA** (50); a comparação usa o
  `full_price`/`valor_cheio`. O líquido em reais da conciliação usa a PTAX do dólar quando a API não traz a conversão
  da Hotmart (pode diferir alguns centavos dos 11,69 do webhook).

## Tela Admin → Hotmart (`admin/hotmart_views.py`)

- **Vendas**: resumo (vendas, total por moeda com IVA, em R$, nosso líquido, taxa média, aguardando OXXO/SPEI,
  canceladas, reembolsos) e a lista com pedido (Estante e e-mails), país, pagamento, valores, taxa %, situação, modelo
  da nota, previsão de repasse e conciliação.
- **Conciliação**: botão, últimas execuções e as vendas com divergência.
- **Para conferir**: avisos `sem_pedido` / `oferta_divergente` / `erro` com o JSON e o botão **Reprocessar**
  (`servico.reprocessar`), e as vendas sem cotação.
- **Ofertas**: o de-para oferta → plano.
- Os POSTs exigem Origin/Referer do próprio site (`apps/_nucleo/auth.origem_confiavel`; o projeto não tem token CSRF).

## ROI

A Hotmart tem coluna própria: **"Recebido (Hotmart)"** no ROI de todos os produtos e **"Recebido via Hotmart"** no
card "ROI Real Web" do produto (`total_hotmart` em `_SQL_ROI_REAL_WEB`/`_SQL_ROI_TODOS_PRODUTOS`; o `total_web`
exclui `cartao` e `hotmart`). Valor bruto em reais, sem o IVA da cliente, como PIX e cartão.

## API de vendas

Da documentação oficial ("Vendas", copiada em 21/11/2026). Autenticação OAuth `client_credentials` (Ferramentas →
Credenciais Developers; credencial própria para o sandbox `https://sandbox.hotmart.com`, com dados fictícios), token
de ~48 h, limite de 500 chamadas/min, paginação por `page_token`, datas em milissegundos UTC.

| Endpoint | Para quê |
|---|---|
| `GET /payments/api/v1/sales/history` | lista de vendas (sem filtro de status só vêm APPROVED e COMPLETE) |
| `GET /payments/api/v1/sales/summary` | comissões somadas por moeda |
| `GET /payments/api/v1/sales/users` | participantes (comprador, produtor...) |
| `GET /payments/api/v1/sales/price/details` | `base`, `total`, `vat` (imposto), `fee` (a taxa da Hotmart), cupom e `real_conversion_rate`, cada valor com a moeda |
| `PUT /payments/api/v1/sales/:transaction/refund` | pedir reembolso (só aprovada/completa) |

- **Não há data de saque/liberação** em nenhum desses retornos: a `previsao_repasse` continua estimada.
- O `price/details` completa o que o webhook pode não trazer: a taxa da Hotmart (`fee`) e o imposto (`vat`).
- Garantia (prazo de reembolso para a compradora): mínimo 7 dias, até 30 (pode estender a 60), e precisa estar
  informada antes da venda.
- Respostas vistas no sandbox (26/11/2026; dados fictícios, só o formato vale):
  - `history` (item): `product.{id,name}`, `buyer.{name,email,ucode}`, `producer`, `purchase.{transaction, status,
    approved_date, order_date, warranty_expire_date, price.{value,currency_code}, offer.{code,payment_mode},
    payment.{type,method,installments_number}, hotmart_fee.{total,fixed,percentage,base,currency_code},
    tracking.{source,source_sck,external_code}, commission_as, is_subscription}`. A taxa da Hotmart vem aberta
    (ex.: 9,9% + 1 fixo). Conferir numa venda real se o `tracking.external_code` é o nosso `xcod`.
  - `commissions` (item): `transaction`, `product`, `exchange_rate_currency_payout`, `commissions[].{source,
    commission.{value,currency_code}, user.{name,email,ucode}}`.
  - `price/details` (item): `transaction`, `product`, `base`, `total`, `vat`, `fee` (cada um `{value,
    currency_code}`), `coupon.{code,value}`, `real_conversion_rate`.
- A credencial é do sandbox **ou** de produção (o tipo é escolhido na criação e não muda): a de sandbox recebe 403
  `unauthorized_client` em `developers.hotmart.com`.

## Robustez

- Avisos repetidos ou simultâneos: o aviso é gravado como `processando`; outra cópia só reprocessa se a primeira deu
  `erro` ou ficou parada mais de 2 min.
- Sem cotação na hora: o pedido é confirmado com o valor esperado (não zera) e o próximo aviso com cotação (ex.: o
  `PURCHASE_COMPLETE`) corrige `valor_pago`.
- Aguardando/cancelado só mexem em pedido web antes do pagamento (1001, 1003, 1004, 1010, 1011) e com oferta do mesmo
  produto; pedido sem plano nunca é confirmado.
- A cotação roda dentro da requisição com limite de 3 s e cache de 6 h.
