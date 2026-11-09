# Contribuição no site ("entrega antes, contribuição depois")

Teste A/B iniciado em novembro de 2026. Ele leva para o site o modelo do WhatsApp: a cliente recebe o livro antes e
paga depois, se gostar. O motivo foi a dificuldade de conseguir novas BMs da Meta e novos números de WhatsApp. A
hipótese é que no WhatsApp quem vende é a conversa: o áudio, o nome dela e a persona.

Dados de produção, links enviados entre 08/10 e 05/11:
- 45% de quem recebe o link paga.
- **70% dos pagamentos chegam em até 30 min**: a cobrança vem junto com a entrega, não "depois de ler".
- **23% pagam só depois do follow-up de 2h**.

Por isso, no site, o pedido de contribuição aparece assim que a Estante abre, e o e-mail para os lembretes é
obrigatório.

## Como funciona

1. **Landing do WhatsApp** (`/tempero`). No carregamento, `web/contribuicao.sortear_braco` decide o braço, guardado no
   cookie `ab_contrib_<produto>` por 30 dias:
   - `wpp`: o botão "Quero receber" vai pro WhatsApp, como sempre;
   - `estante`: o botão abre a camada `_contribuicao_entrada.html` dentro da própria página. Os textos e o ícone que
     prometem WhatsApp também somem.
2. **Clique** (`POST /api/v1/contribuicao/iniciar`): cria o pedido da entrega em **1008** (`fluxo_inicial='web'`), com
   a mesma atribuição do lead do WhatsApp (`lead_incluir.atribuicao_do_clique`) e os itens do plano padrão. O clique
   conta aqui, antes de ela digitar qualquer coisa. Clicar de novo no mesmo aparelho reaproveita o pedido e soma em
   `cliques`, **mas só se ele ainda não foi entregue** (1008). Entregue, o clique cria um pedido novo, porque pode ser
   outra pessoa no mesmo celular (mãe e filho). O navegador guarda as últimas 5 entregas (`contrib_entregas_<id>` no
   localStorage); no e-mail, se ele for igual ao de uma delas, ela volta para a própria Estante e o clique novo é
   somado ao pedido dela. A comparação é só com as entregas deste navegador, nunca com o banco, porque o e-mail
   digitado não prova nada. No braço `wpp`, cada lead do `gravar-lide` entra em `contribuicao_pedidos`, porque lá cada clique vira um
   lead. Assim os dois braços contam cliques do mesmo jeito. Só cria pedido quem tem o cookie do braço estante com o
   teste ligado (ou de QA); qualquer outro caso recebe 409 e a página segue para o WhatsApp.
3. **Nome**: "Como posso te chamar?". O toque em Continuar também libera o som do áudio 1.
4. **Tela de chegada**:
   - o áudio 1 da persona toca enquanto o livro está "sendo separado" (a barra e o checklist seguem o áudio);
   - há o botão "ler em vez de ouvir";
   - depois de 15 s, aparecem o e-mail (obrigatório, com sugestão de domínio digitado errado) e o botão "Abrir meu livro".
5. **Entrega** (`POST /api/v1/contribuicao/entregar`): o pedido vai para **1009**, o e-mail "seu livro chegou" é enviado
   e ela vai para a **Estante 2** (`/pedido2/<guid>`). Na Estante:
   - o livro principal libera e o PDF baixa, como no WhatsApp;
   - os bônus ficam com cadeado;
   - o cross-sell fica escondido;
   - aparece o recado da persona (áudio 2) com o botão **"Fazer minha contribuição de R$ X"**.
6. **Contribuição**: o botão leva ao checkout v2 (`/pay2/<produto>?ref=<guid>`). É uma **venda normal do site**:
   - o preço é o do plano padrão, com order bumps, no Pix ou no cartão;
   - os dados vêm preenchidos e os textos falam em "contribuição";
   - o pedido herda o clique do anúncio da entrega (`copiar_atribuicao_pedido`);
   - o pedido vai para 1000, e NF-e, e-mail de entrega, ROI web, Financeiro e conversão (valor real) seguem como sempre;
   - os bônus da Estante de origem liberam pelo vínculo (`pedidos_vinculados`) e pela regra "liberado prevalece".
7. **Lembretes por e-mail** (`fluxos/fluxo_contribuicao_email.py`, beat a cada 10 min):
   - saem 2h e 24h depois do e-mail informado, das 8h às 22h;
   - não saem para quem já pagou o produto (pelo vínculo ou pelo mesmo e-mail);
   - o link `?lembrete=1` faz a Estante tocar o áudio de lembrete;
   - o follow-up do checkout (`fluxo_followup_web`) ignora esses pedidos, para ela não receber duas cobranças.

Não há conversão dupla: o pedido da entrega (1008/1009) nunca é pago, então nunca vai para o Google Ads nem para a Meta.

## Configuração (`contribuicao_config`, migration 100)

Uma linha por produto. Nada fica fixo no código.

| Coluna | O que é |
|---|---|
| `ativo`, `percentual_estante` | Liga/desliga e a parte dos cliques que fica no site. **0 desliga na hora**, sem deploy |
| `persona_nome`, `persona_foto` | Quem fala com a cliente |
| `audio_intro`, `audio_cobranca`, `audio_lembrete` | Caminhos em `/static`. **Use mp3** (o `.ogg` do WhatsApp não toca em todo iPhone) e **nome versionado** (`-v2.mp3`), porque o nginx guarda `/static/audios/` em cache `immutable` |
| `texto_intro`, `texto_cobranca`, `texto_lembrete` | Transcrições ("ler em vez de ouvir") |
| `checklist` | O que vem no livro, uma linha por item (tela de chegada) |
| `lembrete1_minutos`, `lembrete2_minutos` | Tempo até os lembretes (padrão 120 e 1440) |

Para um produto novo:
1. Inserir a linha de configuração.
2. Incluir `{% include '_contribuicao_entrada.html' %}` na landing do WhatsApp dele, como em `tempero.html`.
3. Chamar `contexto_landing`/`gravar_cookie_braco` na rota da landing.

**QA**: `?contrib=estante` (ou `?contrib=wpp`) força o braço, mesmo com o teste em 0%. Esses cliques ficam com
`teste=1` e fora da análise.

## Acompanhamento

No admin, em **ROI do produto**, o card **"Teste: contribuição no site × WhatsApp"** mostra, por braço:
- cliques;
- funil: nome → ouviu o áudio → e-mail → estante → áudio 2 → checkout;
- pagos, receita e **receita por clique**, que é a métrica do teste.

O custo por clique é o mesmo nos dois braços, porque é a mesma campanha. Um cuidado: no WhatsApp, "pago" é o
comprovante aceito pela IA, não dinheiro recebido. Compare também o Financeiro.

## "Guarde seu livro" (Estante 2, todos os pedidos)

Para ela não perder o livro se fechar a aba e o e-mail não chegar. Fica abaixo dos livros, antes e depois de pagar
(`web/estante_acesso.py`, `_estante_guardar.html`):
- **Baixar meu livro no celular**: o livro principal. Cada livro liberado também tem um "Baixar" embaixo da capa. No
  iPhone, aparece a dica de que o arquivo fica no app Arquivos, em Downloads.
- **Mandar o link pro meu WhatsApp**: abre o WhatsApp (`wa.me/?text=`) para ela mandar o link para o próprio número,
  que aparece como "(Você)".
- **E-mail mascarado + Reenviar o e-mail**: só em pedido do site (1000 ou 1009) com e-mail. O reenvio vai sempre para
  o e-mail já gravado. Limites na tabela `envios_email_site` (migration 101): por pedido, 1 a cada 5 min e 3 por
  dia; por IP, 20 por hora (IP de operadora é compartilhado); teto global por hora em `REENVIO_ESTANTE_LIMITE_HORA`
  (padrão 60), que protege a cota de envio do Gmail do `admin@`. Quando o teto global estoura, o log registra um erro
  `[ESTANTE-REENVIO]`.

**E-mail da entrega da contribuição**: o e-mail é digitado sem verificação, então o "seu livro chegou" sai só na
primeira entrega do pedido e passa pela mesma tabela (20 por IP por hora, teto global em
`CONTRIBUICAO_ENTREGA_LIMITE_HORA`, padrão 200). Os lembretes também passam por ela (teto em
`CONTRIBUICAO_LEMBRETE_LIMITE_HORA`, padrão 200; o que passar fica para a próxima varredura). Depois de entregue, o
e-mail do pedido não muda: outro e-mail na mesma página recomeça com um pedido novo. Se um limite barrar, ela recebe o livro na tela do mesmo jeito; só o
e-mail não sai. Pelo mesmo motivo, a Estante da entrega (1009) **não junta pedidos pelo e-mail** (só pelo vínculo do
checkout), não lista apps e não abre app.

Os players de áudio (chegada e Estante) têm barra tocável e arrastável, como no WhatsApp (`_audio_busca.html`).

## Estados

| id | Significado |
|---|---|
| 1008 | Contribuição: clicou em Quero receber (nada entregue; a Estante responde "ainda não entregue") |
| 1009 | Contribuição: livro entregue, aguardando contribuição (`web/checkout._entrega_contribuicao`) |
