# Conversões da Meta (Instagram)

A venda de anúncio do Instagram volta para a Meta pela API de Conversões e o investimento entra no ROI, pelo mesmo caminho do Google: o clique fica no pedido, a campanha diz o canal e o gasto vai para `orcamento_campanha`. Não há Pixel nem cookie de clique.

## Colocar um produto no ar

1. **Rode a migration** `099_conversoes_meta.sql`, antes de subir o código.
2. **Token:** crie um usuário do sistema na BM do produto, com `ads_read`, acesso às contas e ao dataset, e coloque o token no `.env` como `META_TOKEN_<BM>`. Um `META_TOKEN_` novo também precisa de uma linha no serviço `worker-baixa` do `docker-compose.yml`.
3. **URL do anúncio:** nos parâmetros de URL do anúncio, use:

   ```
   gad_campaignid={{campaign.id}}&adgroupid={{adset.id}}&creative={{ad.id}}&placement={{placement}}&utm_source=meta
   ```

   O `fbclid` a Meta coloca sozinha. Sem `utm_source=meta` e sem campanha numérica, o clique não conta como anúncio.

A campanha nasce no primeiro clique, com o ID no lugar do nome. A rotina de investimento preenche depois o nome, a conta, o dataset e o token dela: não há cadastro de dataset. Até lá, a venda da campanha fica pendente e sai na rodada seguinte. Campanha que já existia não muda de canal sozinha: ajuste em **Campanhas**.

O destino sai dos conjuntos da campanha (`promoted_object.pixel_id`), o dataset em que eles otimizam, e o token é o que enxergou a conta. Para parar o envio de uma campanha, marque-a como Google em **Campanhas**.

## Testar antes de valer

Preencha `META_TEST_EVENT_CODE` com o código de **Testar eventos** do Gerenciador de Eventos e recrie o `worker-baixa`. Os eventos vão com o código e as vendas **não** são marcadas como enviadas. Ao terminar, esvazie a variável: as vendas de teste dos últimos 6 dias serão enviadas de verdade na hora seguinte.

No dev, `config.WHATSAPP_API_URL` é um endereço morto: nada chega à Meta e as vendas contam como erro.

## O que roda

| O quê | Quando | Onde |
|---|---|---|
| Envio das compras | Toda hora, no minuto :23, fila `baixa` | `tasks.processar_conversoes_meta` → `fluxos/fluxo_meta_conversoes.py` |
| Destino das vendas e investimento | Toda hora, no minuto :17, fila `baixa` | `tasks.processar_orcamento_meta` → `fluxos/fluxo_orcamento_meta.py` |

Para reprocessar o investimento de um dia, chame `tasks.processar_orcamento_meta` com `data_str='AAAA-MM-DD'`.

## Quais vendas vão

Pedido pago (estados 0 e 1000), de campanha com `plataforma='meta'`, sem `gclid`, `wbraid` e `gbraid`, ainda não aceito e pago nos últimos 6 dias. O destino é o da campanha do pedido. Valor: site = valor pago; WhatsApp = R$ 10.

## Como investigar no log do `worker-baixa`

Procure por `FLUXO-META-CONVERSOES` e `ORCAMENTO-META`.

| Mensagem | O que significa | O que fazer |
|---|---|---|
| `sem aceite há N dias` | A venda está perto de sair da seleção: aos 6 dias, para de ser tentada e sem novo aviso | Resolva a causa, que aparece em outra linha da mesma venda |
| `ainda sem destino` | A rotina de investimento não achou dataset nos conjuntos da campanha: ela ainda não rodou, o token não enxerga a conta, ou a campanha não otimiza por conversão | Confira o token e o objetivo da campanha. A venda é tentada de novo a cada hora |
| `sem domínio ou sem navegador` | Falta `dns_origem` ou `client_user_agent`, que a Meta exige | A venda fica pendente e é tentada de novo a cada hora |
| `token ... inválido ou vazio` | A variável saiu do `.env` ou não chegou ao `worker-baixa` | Corrija o `.env` ou o `docker-compose.yml` |
| `recusada: HTTP ...` | A Meta recusou o evento | Veja a mensagem de erro da Meta na mesma linha |
| `Erro ao listar as contas de META_TOKEN_...` | A BM está bloqueada ou o token expirou | As outras BMs continuam. Troque o token |
| `só gravamos BRL` | A conta de anúncios não está em reais | O gasto dela não entra no ROI |
| `não encontrada em campanhas` | A campanha ainda não recebeu clique,  | O gasto entra depois do primeiro clique: a leitura cobre 7 dias para trás |

Em **Campanhas**, "Remover" numa campanha da Meta só volta o nome para o ID: o canal e o destino ficam.

## Fora do escopo

Pixel, `_fbp`, eventos além da compra, anúncio que abre o WhatsApp direto (`ctwa_clid`), retirar conversão após devolução e salvar `wbraid` e `gbraid` no site. A especificação completa está em `META_ESPECIFICACAO.md`.
