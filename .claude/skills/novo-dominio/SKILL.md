---
name: novo-dominio
description: Ativa um domínio novo no vendas-web (site institucional da empresa + webhook do WhatsApp): nginx 80/443 com Let's Encrypt, roteamento por host em app/app.py, templates, _HOST_SECRET_MAP em whatsapp_seguranca.py, variáveis WHATSAPP_APP_SECRET_/ACCESS_TOKEN_ nos 4 serviços do docker-compose.yml e runbook de produção. Use quando o usuário pedir para "ativar", "incluir", "cadastrar" ou "configurar" um domínio/site novo, um domínio espelho de marca existente, ou um domínio só para o webhook do WhatsApp.
---

# Novo domínio

Roteiro de execução. Pegadinha nº 1 (já causou 401 em produção 5 vezes): **o domínio só recebe
mensagens reais da Meta se estiver em `_HOST_SECRET_MAP` E se as variáveis estiverem nos 4
serviços do `docker-compose.yml`**. A verificação GET da Meta passa mesmo sem isso — o erro só
aparece quando chegam mensagens de verdade.

## Fase 1 — Perguntar (AskUserQuestion; nunca assumir)

1. **Domínio** e se usa `www` (padrão recente: sem `www`).
2. **Tipo** — define todo o resto:
   - **completo**: empresa nova → 4 templates + variáveis novas (modelo: `barreiroslivros.com.br`).
   - **espelho**: mesma marca de um domínio existente em outro TLD → reaproveita templates e
     variáveis, sem nada novo (modelo: `lblivros.com.br` → `lb-livros.site`).
   - **webhook**: só para o webhook, página mínima → 1 template (modelo: `stracklivros.com.br`).
   - Mesmo CNPJ de um domínio existente **não** implica espelho (`barreiroslivros` tem o CNPJ do
     `brep` e não é espelho). Perguntar sempre.
3. **Dados da empresa** (completo/webhook): nome de marca, razão social (MEI: nome literal da
   Receita), CNPJ, e-mail, telefone (a maioria não tem), endereço (a maioria não mostra; se
   mostrar, com rótulos de campo como na ficha do CNPJ), segmento.
4. **Segmento fora de livros/e-books?** Perguntar se a copy do site deve ser adaptada ao segmento
   real (ex.: `livrosemais.site` é vestuário: copy de moda e Termos com "Trocas e Devoluções",
   Art. 49 CDC, no lugar de "Licença") ou se mantém a linguagem de e-books.
5. **E-mail do certbot** (ou nenhum → `--register-unsafely-without-email`).

Definir o **slug** a partir do domínio: minúsculo nos templates e na função (`barreiroslivros`),
MAIÚSCULO nas variáveis (`BARREIROSLIVROS`).

## Fase 2 — Implementar

Copie sempre do domínio-modelo do mesmo tipo; não reescreva do zero.

| Arquivo | completo | espelho | webhook |
|---|---|---|---|
| `infra/nginx/conf.d/default.conf`: bloco 80 (com `/.well-known/acme-challenge/`) + bloco 443 **comentado** até o certbot emitir, inserido antes do bloco `# ── Desenvolvimento local` | ✔ | ✔ | ✔ |
| `app/app.py`: `_is_<slug>()` (cópia de `_is_barreiroslivros`) | nova função | adicionar o host na `_is_*` existente | nova função |
| `app/app.py`: `elif` nas rotas | 5 rotas (`/`, `/portifolio`, `/politica-privacidade`, `/termos-de-uso`, `/contato`) | nenhum | só `/` e `/portifolio` |
| `app/templates/`: `portifolio-`, `politica-privacidade-`, `termos-de-uso-`, `contato-<slug>.html` | 4 | nenhum | só `portifolio-` |
| `app/whatsapp_seguranca.py`: host em `_HOST_SECRET_MAP` e `_HOST_ACCESS_TOKEN_MAP` | variáveis novas | variáveis da marca original | variáveis novas |
| `.env.example`: `WHATSAPP_APP_SECRET_<SLUG>` e `WHATSAPP_ACCESS_TOKEN_<SLUG>` (placeholders) | ✔ | — | ✔ |
| `docker-compose.yml`: `- WHATSAPP_APP_SECRET_<SLUG>=${WHATSAPP_APP_SECRET_<SLUG>:-}` e o de `ACCESS_TOKEN` em **app, worker-urgente, worker-normal, worker-baixa** | ✔ (8 linhas) | — | ✔ (8 linhas) |

Nos templates, troque **todos** os dados da empresa do modelo (grep pelo CNPJ, e-mail, nome e
domínio antigos no arquivo novo para garantir que não sobrou nada).

## Fase 3 — Verificar

```bash
.claude/skills/novo-dominio/verificar_dominio.sh <dominio> <SLUG> <completo|espelho|webhook>
python3 -m pytest -q
```

Num espelho, `<SLUG>` é o da marca original (ex.: `LB`). O script precisa terminar com
"Tudo certo". Com o `.env` local em `AMBIENTE=desenvolvimento`, não teste o webhook contra a Meta
(o dev nunca chama a API oficial).

## Fase 4 — Commit e runbook de produção

Commit só com os arquivos do domínio (padrão de mensagem: `inclui dominio <dominio> (<RAZÃO SOCIAL>)`).
Pergunte antes de dar push. Depois entregue ao usuário este runbook **preenchido** com domínio,
slug e e-mail. A fonte de verdade do SSL é [infra/certbot/README.md](../../../infra/certbot/README.md);
se ele mudar, siga o README.

1. DNS: registro A do domínio apontando para o VPS → `dig +short <dominio> A`.
2. No VPS: `git pull` + `make reload-nginx` (sobe o bloco 80). **Nunca** `make restart-nginx`,
   porque um cert faltando derruba todos os domínios.
3. `docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d <dominio> --email <email> --agree-tos --no-eff-email`
4. Descomentar o bloco 443 → commit → `git pull` no VPS → `make reload-nginx`.
5. Colar no `.env` de produção os valores **reais** de `WHATSAPP_APP_SECRET_<SLUG>` (painel do
   Meta App) e `WHATSAPP_ACCESS_TOKEN_<SLUG>`; conferir com `grep WHATSAPP_.*_<SLUG> .env`.
6. Recriar os serviços para pegar as variáveis novas (**`up -d`, não `restart`**):
   `docker compose up -d --build app worker-urgente worker-normal worker-baixa` e depois `make reload-nginx`.
7. Na Meta: webhook `https://<dominio>/api/v1/webhook-whatsapp` com o `WHATSAPP_VERIFY_TOKEN`.
8. Validar: `curl -I https://<dominio>`; mandar uma mensagem real e conferir nos logs que não
   houve `Host '<dominio>' não mapeado` nem 401.

## Fase 5 — Memória

Registrar `project_dominio_<slug>.md` com os dados da empresa, o tipo, qualquer desvio do padrão
e as pendências de produção (cert, App Secret real), e adicionar a linha na seção Domínios do
`MEMORY.md`.
