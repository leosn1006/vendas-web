# Cartão de crédito no checkout (Cielo + Silent Order Post)

## Visão geral

O cartão aparece no checkout do site (`/pay/<id>` e `/pay2/<id>`) quando o produto tem a configuração em
`config_cartao_produto` (admin: produto → "Cartão de Crédito (Cielo)"). O WhatsApp continua só com Pix.

**O número do cartão e o CVV nunca passam pelo nosso backend** (PCI SAQ A-EP). Quem leva o cartão até a Cielo é o
**Silent Order Post (SOP)**: um script da Cielo lê os campos da nossa página e envia direto, recebendo um
`PaymentToken` (GUID, uso único, ~20 min). O backend autoriza a compra só com esse token.

```
navegador                                 backend                                  Cielo / Braspag
1. clique em Pagar ─────────────────────► POST /api/v1/cartao/sop-token
                                          OAuth (CIELO_SOP_ID/KEY, cache Redis) ──► auth.braspag.com.br
                                          AccessToken SOP ────────────────────────► transaction.pagador.com.br
   ◄──────────────────────────────────── {access_token, ambiente}
2. bpSop_silentOrderPost (cartão) ───────────────────────────────────────────────► www.pagador.com.br
   ◄──────────────────────────────────────────────────────────────── PaymentToken
3. POST /api/v1/cartao/gerar {credencial} ► gerar_cartao → POST /1/sales com
                                            CreditCard.PaymentToken ─────────────► API E-commerce 3.0
```

## Onde está cada parte

| Parte | Arquivo |
|---|---|
| Credencial no navegador (SOP; depois as wallets) | `static/js/checkout-cartao.js` (`CheckoutCartao.obterCredencial`) |
| Campos ocultos no formato do SOP | `checkout.html` / `checkout-2.html` (`#sopNumero`, `#sopValidade`, `#sopCvv`, `#sopTitular`) |
| AccessToken do SOP (limite 10/10 min por IP) | `web/checkout.py:gerar_access_token_sop` + rota em `web/__init__.py` |
| OAuth, AccessToken, autorização por credencial | `web/cielo.py` |
| Pedido, parcelas, nova tentativa, auditoria | `web/checkout.py:gerar_cartao` |
| Reconciliação dos presos em 1005 (a cada 15 min) | `fluxos/fluxo_verificar_cartao_pendente.py` → `reconciliar_cartao` |
| Parcelamento (Tabela Price, juros do lojista, mínimo R$ 5/parcela) | `web/parcelamento_cartao.py` |
| Bandeira pelo BIN (cache em `bandeira_bin`) | `web/bandeira_bin.py` |

## Detalhes que não estão na documentação da Cielo (vistos no script)

- Classes lidas: `bp-sop-cardnumber`, `bp-sop-cardexpirationdate`, `bp-sop-cardcvv` (não "cardcvvc") e
  `bp-sop-cardholdername`. O script pega o **primeiro** elemento de cada classe na página.
- Número só com dígitos; validade `MM/AAAA`; titular só `[a-zA-Z ]` (por isso o nome vai sem acento e em maiúsculas).
- O script valida o dígito verificador (Luhn) e chama `onInvalid` com `[{Field, Message}]`.
  `onError` recebe `{Code: 400, Response}` (dados recusados) ou `{Code, Text}`.

## Credencial (`credencial` no corpo de `/api/v1/cartao/gerar`)

`{tipo: 'sop', payment_token, bin, bandeira}`. O backend recusa (sem criar pedido) corpo com `numero_cartao`/`cvv`
ou credencial malformada. `pagamento_cartao.origem` (migration 105) grava o tipo: `digitado` (legado), `sop`, e
no futuro `google_pay`/`apple_pay` — que entram como novos tipos em `cielo._credit_card_da_credencial` e
`CheckoutCartao`, sem mudar o fluxo do pedido.

A auditoria (`pagamento_cartao`) nunca guarda número, CVV nem o token: antes da resposta só o BIN (`453211******`);
o número mascarado completo vem da resposta da Cielo.

## Estados do pedido

1001 criado → **1005** aguardando a Cielo (gravado antes da chamada) → **1000** pago · **1006** negado (nova tentativa
no mesmo pedido) · **1007** sem resposta da Cielo por 7 dias.

## Configuração

| Variável | Padrão (sandbox) | Produção |
|---|---|---|
| `CIELO_MERCHANT_ID` / `CIELO_MERCHANT_KEY` | — | do portal (E-commerce → Credenciais) |
| `CIELO_API_URL` / `CIELO_API_QUERY_URL` | `apisandbox` / `apiquerysandbox` | `api.cieloecommerce…/1/` / `apiquery…/1/` |
| `CIELO_SOP_ID` / `CIELO_SOP_KEY` | — | portal: E-commerce → Gestão API E-commerce → Microsserviços → Silent Order Post |
| `CIELO_OAUTH_URL` | `https://authsandbox.braspag.com.br/oauth2/token` | `https://auth.braspag.com.br/oauth2/token` |
| `CIELO_SOP_URL` | `https://transactionsandbox.pagador.com.br/post/api/public/v2/accesstoken` | `https://transaction.pagador.com.br/post/api/public/v2/accesstoken` |
| `CIELO_SOP_AMBIENTE` | `sandbox` | `production` |

Ficam nos serviços `app` e `worker-baixa` do `docker-compose.yml`. **Não clicar em "Gerar nova Merchant Key"**: invalida
a chave em uso e derruba o cartão. "Nova credencial" do SOP também invalida a anterior.

## PCI (SAQ A-EP)

- A página de pagamento é nossa: o checkout não carrega scripts de terceiros além do SOP — manter assim.
- Pendente: CSP nas páginas de checkout, monitor de alteração da página, scan ASV trimestral e o questionário anual.
