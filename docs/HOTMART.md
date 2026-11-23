# Hotmart: checkout de fora do Brasil

No Brasil continua o nosso checkout (PIX/cartão). Fora do Brasil a venda passa pela Hotmart, que é a vendedora legal
(Merchant of Record): ela recolhe os impostos de lá e aceita os meios locais (no México: cartão, OXXO, SPEI). O
primeiro produto é a Música do México (`/mx/cancion`, produto `es-MX`, migration 108).

## Fluxo

1. A cliente clica em comprar no nosso site e **nós criamos o pedido** (estado 1001, com `plano_id`).
2. Redirecionamos para o **link fixo da oferta** na Hotmart com `xcod=<guid do pedido>` (+ `name`/`email`).
   *(Próxima etapa: criação do pedido, redirecionamento e página de obrigado ainda não existem.)*
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
Por enquanto o cadastro é à mão:

```sql
INSERT INTO hotmart_ofertas (codigo, produto_id, plano_id, descricao) VALUES ('<off da Hotmart>', 22, 25, 'Canción');
```

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

Não está na documentação, conferir no 1º aviso real (`payload` em `pagamento_hotmart_eventos`): em que moeda vem a
nossa comissão (BRL? USD?) numa venda em pesos, se vem `currency_conversion`, o `payment.type` do OXXO/SPEI
(provavelmente `CASH_PAYMENT` / `DIRECT_BANK_TRANSFER`) e qual evento chega quando o OXXO é gerado.

## Próximas etapas

- Criar o pedido e redirecionar com `xcod`; página de obrigado (cookie com o guid, espera o webhook).
- Fase 2b: tela "Hotmart" no admin (vendas, totais por moeda, aguardando OXXO, "Para conferir") e conciliação pela
  API de vendas da Hotmart (OAuth client_credentials; não há API de saques).
- Order bumps; devolução no Financeiro. **Hoje um reembolso/chargeback não muda o pedido**: ele continua pago e
  somando no ROI até essa etapa (a `pagamento_hotmart.status` mostra REFUNDED/CHARGEBACK).
- ROI: a venda da Hotmart entra na receita do produto, mas na coluna "web" (as consultas só separam `cartao` do
  resto, `admin/views.py` `_SQL_ROI_REAL_WEB`). Separar `hotmart` junto com a tela. O Financeiro não é afetado (sai
  de `pagamento_pix`/`pagamento_cartao`).

## API de vendas (para a fase 2b)

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
- Faltou copiar (está em "mostrar parâmetros", fechado na página): os campos do retorno do `history` e o endpoint de
  comissões por venda.

## Robustez

- Avisos repetidos ou simultâneos: o aviso é gravado como `processando`; outra cópia só reprocessa se a primeira deu
  `erro` ou ficou parada mais de 2 min.
- Sem cotação na hora: o pedido é confirmado com o valor esperado (não zera) e o próximo aviso com cotação (ex.: o
  `PURCHASE_COMPLETE`) corrige `valor_pago`.
- Aguardando/cancelado só mexem em pedido web antes do pagamento (1001, 1003, 1004, 1010, 1011) e com oferta do mesmo
  produto; pedido sem plano nunca é confirmado.
- A cotação roda dentro da requisição com limite de 3 s e cache de 6 h.
