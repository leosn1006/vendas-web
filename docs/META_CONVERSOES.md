# Conversões da Meta (Instagram)

A venda de anúncio do Instagram volta para a Meta pela API de Conversões e o investimento entra no ROI, pelo mesmo caminho do Google: o clique fica no pedido, a campanha diz o canal e o gasto vai para `orcamento_campanha`. Não há Pixel nem cookie de clique.

## Colocar um produto no ar

1. **Rode a migration** `099_conversoes_meta.sql`, antes de subir o código.
2. **Token:** crie um usuário do sistema na BM do produto, com acesso às contas e ao dataset, e coloque o token no `.env` como `META_TOKEN_<BM>`. Um `META_TOKEN_` novo também precisa de uma linha no serviço `worker-baixa` do `docker-compose.yml`.
3. **Admin → produto → Conversões Meta:** cadastre o dataset e o nome da variável do token. Use o domínio do site ou `*` para os domínios sem linha própria.
4. **URL do anúncio:** nos parâmetros de URL do anúncio, use:

   ```
   gad_campaignid={{campaign.id}}&adgroupid={{adset.id}}&creative={{ad.id}}&placement={{placement}}&utm_source=meta
   ```

   O `fbclid` a Meta coloca sozinha. Sem `utm_source=meta` e sem campanha numérica, o clique não conta como anúncio.

A campanha nasce no primeiro clique, com o ID no lugar do nome, e o nome verdadeiro chega na leitura seguinte de investimento. Campanha que já existia não muda de canal sozinha: ajuste em **Campanhas**.

## Testar antes de valer

Preencha `META_TEST_EVENT_CODE` com o código de **Testar eventos** do Gerenciador de Eventos e recrie o `worker-baixa`. Os eventos vão com o código e as vendas **não** são marcadas como enviadas. Ao terminar, esvazie a variável: as vendas de teste dos últimos 6 dias serão enviadas de verdade na hora seguinte.

No dev, `config.WHATSAPP_API_URL` é um endereço morto: nada chega à Meta e as vendas contam como erro.

## O que roda

| O quê | Quando | Onde |
|---|---|---|
| Envio das compras | Toda hora, no minuto :23, fila `baixa` | `tasks.processar_conversoes_meta` → `fluxos/fluxo_meta_conversoes.py` |
| Investimento | Logo depois do Google, toda hora no :10 | `tasks.processar_orcamento_sheets` → `fluxos/fluxo_orcamento_meta.py` |

Para reprocessar o investimento de um dia, chame `tasks.processar_orcamento_sheets` com `data_str='AAAA-MM-DD'`.

## Quais vendas vão

Pedido pago (estados 0 e 1000), de campanha com `plataforma='meta'`, sem `gclid`, `wbraid` e `gbraid`, ainda não aceito e pago nos últimos 6 dias. O dataset é a linha do domínio do pedido ou, sem linha para ele, a linha `*`. Valor: site = valor pago; WhatsApp = R$ 10.

## Como investigar no log do `worker-baixa`

Procure por `FLUXO-META-CONVERSOES` e `ORCAMENTO-META`.

| Mensagem | O que significa | O que fazer |
|---|---|---|
| `sem aceite há N dias` | A venda está perto de sair da seleção: aos 6 dias, para de ser tentada e sem novo aviso | Resolva a causa, que aparece em outra linha da mesma venda |
| `sem domínio ou sem navegador` | Falta `dns_origem` ou `client_user_agent`, que a Meta exige | A venda fica pendente e é tentada de novo a cada hora |
| `token ... inválido ou vazio` | O nome no admin não começa com `META_TOKEN_`, ou a variável não chegou ao `worker-baixa` | Corrija o admin, o `.env` ou o `docker-compose.yml` |
| `recusada: HTTP ...` | A Meta recusou o evento | Veja a mensagem de erro da Meta na mesma linha |
| `Erro ao listar as contas de META_TOKEN_...` | A BM está bloqueada ou o token expirou | As outras BMs continuam. Troque o token |
| `só gravamos BRL` | A conta de anúncios não está em reais | O gasto dela não entra no ROI |
| `não encontrada em campanhas` | A campanha ainda não recebeu clique, ou foi removida em Campanhas | O gasto entra depois do primeiro clique: a leitura cobre 7 dias para trás |

Remover uma campanha no admin apaga também o canal dela: as vendas e o gasto param até o próximo clique recriá-la como Meta.

## Fora do escopo

Pixel, `_fbp`, eventos além da compra, anúncio que abre o WhatsApp direto (`ctwa_clid`), retirar conversão após devolução e salvar `wbraid` e `gbraid` no site. A especificação completa está em `META_ESPECIFICACAO.md`.
