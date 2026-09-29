# Atendimento por e-mail

Fila única de atendimento da caixa `admin@lsnlivros.com.br` (Google Workspace): cada e-mail que
chega é classificado, ligado ao pedido quando possível e recebe uma resposta pronta, que um humano
aprova em 1 clique em **Admin → 📧 Atendimento e-mail** (`/admin/atendimento-email`).

Por que existe: a análise da caixa (mar–set/2026, 94 clientes) mostrou ~45% dos e-mails sem
resposta. Os motivos mais comuns eram e-mail em branco para a chave PIX (34%), "a Estante não
abre" (17%), dúvida de pagamento (13%) e "paguei e fui cobrada" (10%). Na maioria, bastava achar o
pedido e mandar o link da Estante.

## Como funciona

**Leitor** — `app/fluxos/fluxo_email_conversas.py`, tarefa `tasks.verificar_emails_clientes`,
a cada 10 min na fila `baixa`. Lê até 50 e-mails da caixa de entrada dos **últimos 3 dias** que
ainda não têm o marcador `Sistema/Processado` (não depende de "não lido": o sistema não marca nada
como lido). Para cada um:

1. **Equipe** (domínio `@lsnlivros.com.br` ou `EMAIL_ATENDIMENTO_EQUIPE`) → marca o thread como
   respondido; não vira pendência. Vem antes do ruído: um aviso automático vindo do nosso domínio
   também cai aqui.
2. **Ruído** (bounce, autoresponder, newsletter, remetente `noreply`/`nao-responder…`, Google,
   bancos) → marcador `Ruído` e arquivado.
3. **Triagem** (`app/agente_triagem_email.py`, gpt-4o-mini): `vendas` / `administrativo` / `ruido`
   e a categoria (`chave_pix`, `acesso_estante`, `pagou_e_cobrado`, `pagamento`, `reclamacao`,
   `quer_comprar`, `duvida_uso`, `agradecimento`, `outros`). Atalhos sem IA: e-mail vazio para uma
   chave PIX → `chave_pix`; agradecimento curto → `agradecimento`. Erro da OpenAI → fila humana.
4. **Vínculo com o pedido** (`app/fluxos/email_vinculo.py`), do dado mais confiável ao menos:
   1. thread (resposta ao e-mail de entrega/cobrança);
   2. nº do pedido no assunto/corpo — só se o e-mail do pedido for o do remetente;
   3. e-mail do remetente e e-mails escritos no corpo;
   4. telefone e CPF no corpo (telefone com e sem o 9);
   5. **escreveu para a chave PIX de um produto**: pedidos desse produto nos 7 dias antes do
      e-mail (nunca depois), pagos ou não, por palavra do nome — a cliente acabou de receber a
      chave no WhatsApp;
   6. comprovante anexado (nome do pagador lido pela IA);
   7. nome do remetente (completo, depois primeiro + último).

   As buscas no banco (e-mail, telefone, CPF, nome) olham os pedidos dos últimos 12 meses; a do
   passo 5 olha só os 7 dias antes do e-mail.

   Regras:
   - **pagos de uma pessoa só**: se os pedidos pagos encontrados são de mais de uma pessoa, vira
     lista de candidatos para o humano;
   - sem pedido pago, nos passos 1–4 (identificador forte) vale o não pago mais recente, sem
     checar se há mais de uma pessoa; no passo 5, o não pago da pessoa que bate mais palavras do
     nome (empate → candidatos); nos passos 6–7, pedido não pago nunca vincula;
   - nome comum sozinho ("Maria", "Silva") não basta;
   - vínculo por nome nunca escolhe pedido de produto diferente do da chave para onde ela escreveu.
5. **Decisão e resposta pronta** (`email_respostas.decidir`; textos fixos em
   `app/fluxos/email_respostas.py`). Depende da categoria:

   - **`acesso_estante`, `pagou_e_cobrado`, `chave_pix`** (o grupo da Estante):

     | Situação | Resposta |
     |---|---|
     | pedido pago | `estante_pago`: link da Estante 2 (`/pedido2/<guid>`) |
     | não pago, com comprovante (imagem/PDF) anexado | sem resposta: fila humana confere o pagamento |
     | WhatsApp, livro entregue, não pago | `estante_nao_pago_wpp`: Estante 2 + como pagar |
     | site, não pago, com `url_pagina_vendas` | `pagina_vendas_nao_pago` (a Estante de pedido web não pago não tem botão de pagar) |
     | sem pedido, escreveu para a chave PIX | `chave_pix`: explica a chave + pede dados |
     | sem pedido | `pedir_dados`: comprovante, e-mail/telefone ou nome/CPF |

   - **`duvida_uso`, `quer_comprar`, `outros`** com pedido → `ia` (sugestão do agente de e-mail do
     produto). Só funciona para produto com `disponivel_web`; nos outros, e sem pedido, vai para a
     fila humana sem resposta pronta.
   - **`agradecimento`** e ruído → `sem_acao`.
   - **`pagamento`, `reclamacao`**, administrativo e nome ambíguo (candidatos) → fila humana, sem
     resposta pronta.

   E-mail com mais de 3 dias ganha "Desculpe a demora para responder." Assinatura e cores vêm do
   produto (`email_nome_remetente`, `email_cor_primaria`); sem produto, "Equipe LBE Livros".
6. Grava em `emails_atendimento` (migração 077) — registro leve, **sem copiar o corpo** (a tela
   lê o thread do Gmail na hora). Se há pedido, grava também em `mensagens_email_pedido` (tela de
   conversa do produto e histórico do agente).

**Envio** — `app/fluxos/fluxo_resposta_atendimento.py`. Responde no mesmo thread (threadId +
In-Reply-To). Remetente: alias do produto (`produtos.email_remetente`); sem produto, `suporte@`
(`EMAIL_ATENDIMENTO_REMETENTE`); nunca o `admin@`, que fica para assuntos administrativos. Reserva
atômica no banco evita resposta duplicada (clique duplo). Depois do envio: `respondido`, ou
`aguardando_cliente` quando a resposta pede dados.

**Automático** — fase 1: nada sai sem aprovação. `EMAIL_ATENDIMENTO_AUTO_TIPOS` (lista de
`resposta_tipo`) libera o envio sozinho, mas nunca para `ia`, nunca com vínculo por nome ou
comprovante, nunca num thread já respondido pela fila e no máximo 1 por remetente a cada 24h.
Limitação conhecida (resolver antes de ligar o automático): "já respondido" só enxerga respostas
enviadas pela fila; resposta dada direto no Gmail ou marcada como "Respondido por fora" não conta.

## Marcadores do Gmail

Espelho do estado no banco (a fonte da verdade é `emails_atendimento`):

- status: `Atendimento/A responder`, `…/Aguardando aprovação`, `…/Aguardando cliente`,
  `…/Respondido`, `…/Sem ação`, `…/Em análise` (estoque antigo, fora da fila);
  `Administrativo/A responder`, `Administrativo/Respondido`;
- produto: `Produto/<nome>` ou `Produto/Sem produto`;
- enviados pelo sistema: `Envios/<produto>` — **não pode ser "Enviados"**: o Gmail recusa
  ("Invalid label name"), é o nome da pasta do sistema;
- `Ruído` (arquivado) e `Sistema/Processado` (controle do leitor).

## Variáveis de ambiente

| Variável | Padrão | Uso |
|---|---|---|
| `EMAIL_ATENDIMENTO_CAIXA` | `admin@lsnlivros.com.br` em produção | caixa lida/usada |
| `EMAIL_ATENDIMENTO_EQUIPE` | vazio | e-mails de fora do domínio de quem atende (ex: `lneditoraadm@gmail.com`) |
| `EMAIL_ATENDIMENTO_REMETENTE` | `suporte@lsnlivros.com.br` | remetente das respostas sem produto |
| `EMAIL_ATENDIMENTO_AUTO_TIPOS` | vazio (fase 1) | tipos de resposta enviados sem aprovação |

Estão nos 4 serviços do `docker-compose.yml` (app e workers). A conta de serviço é a
`GOOGLE_SA_JSON_P6` (delegação no domínio com `gmail.send` e `gmail.modify`).

**Dev:** fora de produção (`AMBIENTE != producao`) o leitor **nunca** abre a caixa real: só lê
uma caixa de teste explícita em `EMAIL_ATENDIMENTO_CAIXA` (diferente de `admin@`). Sem ela, a
tarefa não faz nada e o botão de envio avisa.

## Pré-requisitos no Google (feitos em 28–29/09/2026)

- Todo endereço usado como `email_remetente` de produto (e o `suporte@`) precisa estar em
  **Gmail do admin@ → Configurações → Contas → "Enviar e-mail como"** ("Tratar como alias").
  Senão o Gmail troca o remetente pelo `admin@` com o nome padrão da conta. Se a janela de
  adicionar der erro 404, usar janela anônima só com o `admin@`.
- Alias novo se cria em **admin.google.com → Diretório → Usuários → admin@ → Endereços de e-mail
  alternativos**. Alias não tem nome; o nome é o do "Enviar e-mail como".
- DNS do `lsnlivros.com.br` fica no **Hetzner**: SPF (`include:_spf.google.com`), DKIM
  (`google._domainkey`, 2048 bits, ativado em admin.google.com → Gmail → Autenticar e-mail) e
  DMARC (`_dmarc`: `v=DMARC1; p=none`). Teste: "Mostrar original" deve dar PASS nos três.

## Chaves PIX e produto

`database.buscar_chave_pix_do_email` usa `chaves_pix_produto` (não `produtos.chave_pix`, que está
desatualizado). Chave de produto **inativo** não aponta produto: é o caso do `pascoa@`, que até
set/2026 foi a chave do QR de todos os produtos do site.

## Estoque antigo da caixa

`scripts/organizar_caixa_email_antiga.py` (host, venv do projeto) organiza, uma vez, o que é
anterior à fila: simula por padrão e só aplica com `--aplicar`.

```bash
~/vendas-web/.venv/bin/python scripts/organizar_caixa_email_antiga.py            # simulação
~/vendas-web/.venv/bin/python scripts/organizar_caixa_email_antiga.py --aplicar
```

Sem IA: ruído arquivado; conversa em que respondemos por último → `Respondido`; em que a cliente
falou por último há mais de 30 dias → `Em análise`; nos últimos 30 dias → passa pelo leitor e
entra na fila (sem envio automático); enviados → `Envios/<produto>`. Rodado em produção em
29/09/2026: 2.854 e-mails marcados, 38 na fila. E-mails de empresa escritos por pessoas caem como
cliente (o script não faz triagem) — revisar à mão.

## Tela do admin

- **Aprovar e enviar** é o único botão que envia (pede confirmação).
- **Respondido por fora**: já resolvido por outro canal. **Sem ação**: não precisa de resposta
  (inclusive mensagem repetida da mesma pessoa em outra conversa). **Mover p/ Administrativo**:
  não é cliente; descarta a resposta pronta.
- **Vincular a um pedido** / **É este**: refaz a resposta pronta para o pedido informado.
- Editar o texto é permitido; o HTML editado passa pelo sanitizador (o botão colorido vira link).

## Testes

`pytest tests/email` — cascata de vínculo, decisão, textos, proteção do dev, envio automático,
marcadores, fuso (datas do Gmail convertidas para o horário de São Paulo, como o banco grava).
