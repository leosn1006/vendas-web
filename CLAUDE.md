# vendas-web

## O negócio (leia antes de sugerir qualquer mudança)

- Vendemos **e-books low ticket** para **mulheres 35+** (público-alvo de quase todas as campanhas), com tráfego vindo de **Google Ads**.
- Várias marcas/empresas (CNPJs) e domínios rodam na mesma base de código; cada produto tem configuração própria no banco (tabela `produtos`) — nada hardcoded por produto.
- Público 35+: textos simples, botões grandes, poucos passos. Evite jargão e fluxos "espertos".

### Dois canais de venda

1. **WhatsApp — entrega primeiro, cobra depois.** O cliente recebe o e-book *antes* de pagar e paga (PIX) se gostar. Isso é proposital: `static/arquivos/` é público de propósito — nunca restringir/mover. Fluxos em `app/fluxos/`, orquestrados por `app/whatsapp_orquestrador.py`; follow-ups de cobrança via Celery beat. Uma IA (`agente_resposta_produto.py`) responde dúvidas.
2. **Site — paga antes de receber.** Landing + checkout PIX/cartão (`app/web/`, estilo Hotmart com bônus e order bump). Depois do pagamento o cliente acessa a **Estante 2** (`/pedido2/<guid>`, para onde o checkout redireciona e o e-mail de entrega aponta), onde baixa/lê os e-books e vê o **cross-sell** (`/pay2/<id>`) dos produtos que ainda não tem. A Estante 1 (`/pedido/<guid>`, sem cross-sell) continua no ar para links antigos e fluxos do WhatsApp sem `url='v2'`.

### O que se vende: produto → planos → entregáveis (out/2026, `docs/PLANOS.md`)

- **Produto** (`produtos`) = campanha do Google Ads, ISBN, NF-e (sempre como livro), chave PIX, planilha do Ads, remetente do e-mail. Funil, ROI e Financeiro são por produto.
- **Plano** (`produto_planos`) = a oferta que a cliente compra: nome, preço, desconto de oferta, imagens. Um produto tem N planos, ex. no Fatia (12): **Básico** (padrão, só e-books), **Completo** (e-book + App Fatias), **Renovação** (só o app, `renovacao=1`, fora da vitrine). Link: `/pay/<produto>?plano=<slug>` — monte sempre com `web.links.link_checkout`. **Plano padrão** (1 por produto) = link sem `?plano=` e **todo pedido do WhatsApp**; por isso o padrão de produto com WhatsApp não pode ter app.
- **Entregável** (`entregaveis`, catálogo único; antes "ebooks") = e-book (arquivo) ou app (`app_slug`). Cada plano tem seus itens em `plano_entregaveis` (antes "ebooks_produto") com papel **principal / bônus / order bump**; preço próprio só no bump, `dias` só no app. Order bumps são por plano. Vários principais por plano: o preço do plano vai no primeiro.
- **Pedido** grava o plano (`pedidos.plano_id`; NULL = antigo = padrão) e os itens (`pedido_itens.ebook_produto_id` aponta para `plano_entregaveis` — nome antigo mantido). Estante, licença e e-mail saem desses itens.
- **Apps das clientes** (`app/apps/`, PWA em `/app/<slug>/`, ex.: App Fatias; `docs/APPS.md`): um app é vendido como item de um plano. A licença é por app (não por produto) e é liberada pelos **itens app do pedido pago** (dias do item) — Básico não libera, Completo libera. Renovação = plano de renovação **do mesmo produto em que ela comprou o app** ("Meu acesso" só mostra esses). Um app novo = pasta `app/apps/<slug>/` + item no catálogo + plano no produto.
- Produto que virou plano de outro (o antigo 16 "Plano Guiado" → Completo do 12, migration 087) fica em `produtos_redirecionados`: `/pay/<antigo>` redireciona para o plano.
- Admin: produto → "Planos e entregáveis"; menu geral → "Catálogo de entregáveis" e "Apps das clientes". ROI do produto tem "Vendas por plano"; Financeiro filtra por plano.

Conversões voltam pro Google Ads via Google Sheets (GCLID) — venda do site com o valor real pago, WhatsApp com R$ 10 fixo; mexer em atribuição/GCLID afeta o ROI das campanhas.

**Meta (Instagram)** segue o mesmo caminho (`docs/META_CONVERSOES.md`): o clique fica no pedido (`fbc`), `campanhas.plataforma = 'meta'` diz o canal, a venda vai pela API de Conversões para o dataset da campanha, descoberto pelo token `META_TOKEN_<BM>` nos conjuntos dela, e o investimento entra em `orcamento_campanha`.

**Música de Presente** (`app/musica/`, `/musica/...`; `docs/MUSICA.md`): produto sem e-book — quiz → letra (OpenAI) → música (gerador na borda: Apiframe no MVP, `MUSICA_GERADOR`) → prévia grátis → checkout (`?musica=<token>`) → área da compra. Entregável `tipo='musica'` com `recurso` (música, videoclipe, QR, entrega por e-mail); fica fora da NF-e automática (`produtos.nfe_automatica = 0`).

**Atendimento por e-mail:** a caixa `admin@lsnlivros.com.br` é lida a cada 10 min (`app/fluxos/fluxo_email_conversas.py`); cada e-mail é ligado ao pedido e ganha resposta pronta na fila `/admin/atendimento-email`, que um humano aprova. Detalhes em `docs/ATENDIMENTO_EMAIL.md`.

## Stack

Flask + Gunicorn, Celery (filas `worker-urgente`/`worker-normal`/`worker-baixa` + `beat`) com Redis, MySQL, Nginx, tudo em `docker-compose.yml`. Pagamentos: BB Pay/PIX BB (`app/bb_pix.py`). NF-e em `app/fiscal/`. Admin em `app/admin/`.

WhatsApp tem dois provedores por número: API oficial da Meta e o gateway WhatsApp Web (`app/wpp_web_gateway.py`).

## Comandos

- Subir/rebuild: `docker compose up -d --build <serviço>` — **depois de recriar `app`/`worker-*`/`beat`, rode `make reload-nginx`** (senão 502). Nunca `restart-nginx`.
- Testes: `pytest` (padrão exclui marcadores `integration` e `sefaz`).
- Migrations: SQL numerado em `migrations/` (próximo número = último + 1).
- Outros alvos: `make help`.

## Regras

- **Ambiente local é DEV isolado** (banco e credenciais próprios), mesmo com `.env` citando domínios reais.
- **O código no dev nunca chama a API oficial da Meta; à mão, só consulta e evento de teste de conversão, nunca mensagem a cliente nem webhook** — `AMBIENTE=desenvolvimento` no `.env` local faz `app/config.py` forçar um endereço morto em `WHATSAPP_API_URL` (ausente = `producao`). Dev só envia pelo gateway (`WPP_WEB_API_URL`). Código novo que fale com a Meta deve usar `config.WHATSAPP_API_URL` (nunca URL fixa) ou checar `config.EH_PRODUCAO`.
- Não alternar `disponivel_web` de produtos como efeito colateral de teste.
- **E-mail remetente novo de produto** (`produtos.email_remetente`) precisa estar em "Enviar e-mail como" do Gmail do `admin@`, senão o Gmail troca o remetente pelo `admin@`. No dev, o atendimento por e-mail só abre uma caixa de teste (`EMAIL_ATENDIMENTO_CAIXA`), nunca a real.
- Novo domínio + webhook WhatsApp: use a skill `novo-dominio` (além do nginx, exige `app/whatsapp_seguranca.py` e as variáveis nos 4 serviços do `docker-compose.yml`, senão a Meta recebe 401).
- Scripts em `scripts/` rodam fora do Docker em produção (venv próprio).
- Código, comentários, commits e mensagens ao usuário em **português**.

Hooks em `.claude/hooks/` automatizam duas dessas regras: no dev, negam por padrão comandos para `graph.facebook.com` (só passam `curl` de consulta e evento de teste da API de Conversões; mensagem e webhook nunca) e rodam `make reload-nginx` depois de `docker compose up/restart` de app/worker/beat.

## Documentação

`docs/` — `PLANOS.md` (produto → planos → entregáveis), `APPS.md`, `MUSICA.md`, `META_CONVERSOES.md`, `FLUXO_MENSAGENS.md`, `WEBHOOK_WHATSAPP.md`, `PLAYBOOK_SITE_VENDA_WEB.md`, `INTEGRACAO.md` (gateway WhatsApp Web), `ATENDIMENTO_EMAIL.md` (fila de e-mail, Gmail, DKIM/DMARC), `SEGURANCA*.md`. SSL/certbot: `infra/certbot/README.md`.
