# Certificados SSL — Let's Encrypt (certbot)

Este diretório dá suporte a emissão e renovação de certificados SSL gratuitos
via [Let's Encrypt](https://letsencrypt.org/), como alternativa aos
certificados pagos (RapidSSL/DigiCert, ~R$119/domínio) usados hoje em
`infra/nginx/certs/`.

## Por que Let's Encrypt

- CA gratuita e confiável, reconhecida por todos os navegadores/SOs modernos.
- Validade de **90 dias** (vs ~6 meses do RapidSSL) — curto de propósito, para
  forçar renovação automatizada via o protocolo ACME. Ver seção Renovação.
- Emite apenas certificados **DV (Domain Validation)**: valida só que você
  controla o domínio, não a identidade jurídica da empresa. Por isso o
  certificado não carrega campos de Organização/Cidade/Estado/País — só o CN
  (nome do domínio). Nenhuma parte do app lê esses campos em certificados SSL
  (o único parsing de campos de Organização em x509 no repo é
  `app/fiscal/nfe_assinador.py`, do certificado ICP-Brasil da nota fiscal —
  mecanismo totalmente separado, não afetado por isto).

## Como funciona (HTTP-01, sem TXT/DNS-01)

A validação de domínio usa o desafio **HTTP-01**: a Let's Encrypt faz uma
requisição HTTP para `http://seu-dominio/.well-known/acme-challenge/<token>`,
que o próprio nginx responde a partir de um webroot compartilhado. **Não é
necessário criar registro TXT no DNS** (diferente do processo manual do
RapidSSL) — o único pré-requisito de DNS é o domínio ter um **A record**
apontando para o VPS. TXT/DNS-01 só voltaria a ser necessário se um dia for
preciso emitir certificado wildcard (`*.dominio.site`), o que não é o caso de
nenhum domínio hoje.

## Arquitetura

- Serviço `certbot` no `docker-compose.yml` (imagem `certbot/certbot`), sem
  processo contínuo — é chamado sob demanda via `docker compose run --rm
  certbot ...`.
- Dois volumes compartilhados entre `certbot` e `nginx`:
  - `infra/certbot/www/` → webroot do desafio ACME (`/var/www/certbot`)
  - `infra/certbot/conf/` → onde ficam os certificados emitidos
    (`/etc/letsencrypt`, inclui `live/<dominio>/fullchain.pem` e `privkey.pem`)
- Ambas as pastas são ignoradas pelo git (`.gitignore`) — contêm chave privada
  e tokens de desafio, nunca versionar.

## Domínios: quem está em quê

| Domínio | CA |
|---|---|
| 8 domínios `.com.br` legados (`lneditor`, `lssolucoesdigitais`, `lsdigitalsolucoes`, `kpnlivros`, `lsfb-livros`, `rc-livros`, `lclivros`, `ju-livros`, `lsreceitas`) + `breplivros.site`, `lb-livros.site`, `lbe-livros.site` | RapidSSL (pago, manual) |
| `lsnlivros.com.br` | RapidSSL — **fica assim de propósito**: esse certificado é reaproveitado como client cert mTLS da API Pix do Banco do Brasil (`BB_PIX_CERT_PEM`/`BB_PIX_CERT_KEY` no `docker-compose.yml`). Trocar de CA exigiria validar antes com o BB. |
| `livrinhosdigitais.site` | Let's Encrypt (em emissão — blocos nginx 80 e 443 já no `default.conf`, aguardando o `certbot certonly` rodar no VPS) |
| `leituraemais.site` | Let's Encrypt (em emissão — blocos nginx 80 e 443 já no `default.conf`, aguardando o `certbot certonly` rodar no VPS) |

Migração dos domínios legados para Let's Encrypt é possível (ideia discutida:
deixar o certificado pago vencer e emitir Let's Encrypt no lugar), mas não foi
executada — fica como direção futura.

## Runbook: emitir certificado para um domínio novo

1. **Pré-requisito**: A record do domínio (e `www.` se for usar) apontando
   pro VPS. Conferir com `dig +short <dominio> A`.

2. Adicionar um bloco HTTP (porta 80) em `infra/nginx/default.conf` com a
   location do ACME challenge, redirecionando o resto pra HTTPS. Modelo (ver
   os blocos de `livrinhosdigitais.site`/`leituraemais.site` no próprio
   arquivo como exemplo — por padrão sem `www`, a não ser que o domínio
   precise):

   ```nginx
   server {
       listen 80;
       server_name seu-dominio.site;

       location /.well-known/acme-challenge/ {
           root /var/www/certbot;
       }

       location / {
           return 301 https://seu-dominio.site$request_uri;
       }
   }
   ```

   Aplicar com `make reload-nginx` (**nunca** `make restart-nginx` nesse
   momento — ver seção "Cuidado" abaixo). Não adicionar ainda o bloco
   HTTPS/`ssl_certificate` — o arquivo do certificado não existe até o passo 3.

3. Emitir o certificado:

   ```bash
   docker compose run --rm certbot certonly --webroot \
     -w /var/www/certbot \
     -d seu-dominio.site \
     --email admin@lsnlivros.com.br --agree-tos --no-eff-email
   ```

   (adicionar `-d www.seu-dominio.site` também, só se o `www` estiver
   configurado no DNS — o certbot falha se pedir um nome que não resolve.)

4. Adicionar o bloco HTTPS em `infra/nginx/default.conf`, copiando o padrão
   de segurança de qualquer domínio `.site` existente, trocando só:

   ```nginx
   ssl_certificate     /etc/letsencrypt/live/seu-dominio.site/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/seu-dominio.site/privkey.pem;
   ```

   Aplicar com `make reload-nginx` de novo.

5. Validar:

   ```bash
   curl -I https://seu-dominio.site
   openssl s_client -connect seu-dominio.site:443 -servername seu-dominio.site </dev/null 2>/dev/null | openssl x509 -noout -issuer -dates
   ```

   Confirmar `issuer=... Let's Encrypt` e checar que os outros domínios no
   mesmo nginx continuam respondendo normalmente.

Isso cobre só o certificado. Domínio novo + webhook do WhatsApp precisa
*também* de entrada em `app/whatsapp_seguranca.py`
(`_HOST_SECRET_MAP`/`_HOST_ACCESS_TOKEN_MAP`) e das chaves
`WHATSAPP_APP_SECRET_<SLUG>`/`WHATSAPP_ACCESS_TOKEN_<SLUG>` no `.env` de
produção — sem isso, a rota de webhook aceita o GET de verificação da Meta
mas rejeita POSTs reais com 401. Isso faz parte do onboarding de domínio mais
amplo (templates, `app/app.py`, etc.), não deste README.

## Renovação automática

`infra/certbot/renew.sh` (versionado, executável):

```bash
docker compose run --rm certbot renew --quiet
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```

`certbot renew` varre **todas** as lineages em `/etc/letsencrypt` e só renova
quem está a 30 dias ou menos do vencimento — domínios novos emitidos pelo
runbook acima entram automaticamente, sem precisar tocar neste script.

Cron da VPS (fora do repo, configurar manualmente):

```
0 3,15 * * * /caminho/para/vendas-web/infra/certbot/renew.sh >> /var/log/certbot-renew.log 2>&1
```

Horário 3h/15h segue a recomendação da própria Let's Encrypt (2x/dia, ~12h de
intervalo).

## Cuidado: `reload-nginx` vs `restart-nginx`

Um único container nginx serve **todos** os domínios do projeto a partir de
um `default.conf` só. `make restart-nginx` (`docker compose restart nginx`)
para o container e sobe de novo lendo a config do zero — se ela referenciar
um certificado que não existe (esqueceu de emitir antes de adicionar o bloco
HTTPS), o container falha ao subir e **nenhum domínio fica no ar**, nem os
que já estavam certos.

`make reload-nginx` (`nginx -t` + `nginx -s reload`) testa a config nova
antes de aplicar; se for inválida, mantém a config antiga rodando e nenhum
domínio cai. Por isso todo o runbook acima usa `reload-nginx`, nunca
`restart-nginx` — use `restart-nginx` só quando for preciso reiniciar o
processo de verdade (ex.: travado).
