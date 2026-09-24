# vendas-web

## O negócio (leia antes de sugerir qualquer mudança)

- Vendemos **e-books low ticket** para **mulheres 35+** (público-alvo de quase todas as campanhas), com tráfego vindo de **Google Ads**.
- Várias marcas/empresas (CNPJs) e domínios rodam na mesma base de código; cada produto tem configuração própria no banco (tabela `produtos`) — nada hardcoded por produto.
- Público 35+: textos simples, botões grandes, poucos passos. Evite jargão e fluxos "espertos".

### Dois canais de venda

1. **WhatsApp — entrega primeiro, cobra depois.** O cliente recebe o e-book *antes* de pagar e paga (PIX) se gostar. Isso é proposital: `static/arquivos/` é público de propósito — nunca restringir/mover. Fluxos em `app/fluxos/`, orquestrados por `app/whatsapp_orquestrador.py`; follow-ups de cobrança via Celery beat. Uma IA (`agente_resposta_produto.py`) responde dúvidas.
2. **Site — paga antes de receber.** Landing + checkout PIX/cartão (`app/web/`, estilo Hotmart com bônus e order bump). Depois do pagamento o cliente acessa a **Estante** (`/pedido/<guid>`), onde baixa/lê os e-books. A Estante tem um **piloto de cross-sell** (v2: `/pedido2/<guid>` → `/pay2/<id>`) que oferece produtos que o cliente ainda não tem.

Conversões voltam pro Google Ads via Google Sheets (GCLID) — mexer em atribuição/GCLID afeta o ROI das campanhas.

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
- **Dev nunca chama a API oficial da Meta** — `AMBIENTE=desenvolvimento` no `.env` local faz `app/config.py` forçar um endereço morto em `WHATSAPP_API_URL` (ausente = `producao`). Dev só envia pelo gateway (`WPP_WEB_API_URL`). Código novo que fale com a Meta deve usar `config.WHATSAPP_API_URL` (nunca URL fixa) ou checar `config.EH_PRODUCAO`.
- Não alternar `disponivel_web` de produtos como efeito colateral de teste.
- Novo domínio + webhook WhatsApp: além do nginx, atualizar `app/whatsapp_seguranca.py` e as variáveis de secret nos 4 serviços do `docker-compose.yml` (senão a Meta recebe 401).
- Scripts em `scripts/` rodam fora do Docker em produção (venv próprio).
- Código, comentários, commits e mensagens ao usuário em **português**.

Hooks em `.claude/hooks/` automatizam duas dessas regras: bloqueiam comandos para `graph.facebook.com` no dev e rodam `make reload-nginx` depois de `docker compose up/restart` de app/worker/beat.

## Documentação

`docs/` — `FLUXO_MENSAGENS.md`, `WEBHOOK_WHATSAPP.md`, `PLAYBOOK_SITE_VENDA_WEB.md`, `INTEGRACAO.md` (gateway WhatsApp Web), `SEGURANCA*.md`. SSL/certbot: `infra/certbot/README.md`.
