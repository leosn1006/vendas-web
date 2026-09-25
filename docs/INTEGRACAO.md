# Integração do gateway WhatsApp Web (api-wpp-web) com o vendas-web

Documento de referência da integração **já implementada** na branch `integracao-wpp-web` e validada em dev com um chip
real. Nasceu como documento de passagem escrito pela sessão que construiu o gateway (`~/Desenv/JS/api-wpp-web`);
foi reescrito depois da implementação e dos testes, corrigindo o que o original supunha errado (seção 12).
**Leia também o README do gateway** (comandos, API de administração, confiabilidade das mensagens).

Funções e arquivos são citados por **nome**, não por número de linha (que envelhece rápido).

## 1. Contexto e objetivo

A API oficial do WhatsApp (Cloud API) baniu quase todas as BMs do vendas-web e não dá para criar novas. O gateway é o
**plano B**: um serviço que mantém um Chromium com o WhatsApp Web por chip e **imita a Cloud API** (mesmas rotas, mesmo
webhook assinado). O vendas-web escolhe **por número** se fala com a Meta ou com o gateway: a coluna
`telefones_produto.provedor` (`meta` padrão | `wpp_web`). Coluna `meta` = comportamento idêntico ao de antes.

Fora de escopo, de propósito: templates, catálogo, grupos, reações, `block_users`, vários gateways. O botão de link
(`cta_url`) vira texto. Os alertas ao admin (`ADMIN_PHONE_NUMBER_ID`) continuam na Meta.

## 2. O que foi implementado no vendas-web

| Área | O que mudou |
|---|---|
| Migration `076` | `telefones_produto.provedor`; `pedidos.phone_number_id` e `variantes_fluxo_cursor.phone_number_id` para `VARCHAR(50)` (o id do chip é `web-<numero>`). **Aplicada à mão em produção.** |
| Roteamento (`database.get_whatsapp_api_url`, `whatsapp.py`, `whatsapp_upload.receber_audio`, `tasks._checar_qualidade_telefone`) | URL por número: gateway para `wpp_web`, Graph API para o resto. Provedor em cache de **60 s** (não permanente: editar no admin vale sem reiniciar). Falha de banco não vira `meta` (propaga; usa cache vencido se houver). |
| Timeouts (`whatsapp._timeout_envio`) | Meta: 30 s. Gateway: 60 s texto / 180 s mídia (o gateway leva até 25 s para texto, 30 s para baixar o link e 120 s para enviar mídia, numa fila serial por chip). Com 30 s o app desistia antes do erro do gateway. |
| Link da Estante (`whatsapp.montar_link_estante`) | Número do gateway usa `pedidos.dns_origem` (o gateway não tem token por domínio) e, **quando o cliente veio direto pelo WhatsApp (pedido sem `dns_origem`)**, o domínio de `APP_BASE_URL`. Sem nenhum dos dois válidos (ex.: `APP_BASE_URL` ausente, o compose assume `http://localhost`), erro explícito e o fluxo `pedido` para. |
| Dedupe do webhook (`tasks._WEBHOOK_DEDUPE_TTL_S`) | 300 s → 25 h. O gateway reentrega por até 24 h e `mensagens_pedidos.message_id` não é UNIQUE. |
| Chip caído (`whatsapp.exigir_numero_operacional`) | Executor de ações, follow-ups e `responder` **não enviam** com o chip fora (`ChipForaDoArWhatsApp`, transiente). Com status ruim, o gateway é consultado na hora antes de bloquear (status velho não segura o envio). Follow-up que perde o chip **no meio** da sequência é dado como concluído (não reenvia o que já saiu). |
| Sorteio de número (`database.selecionar_telefone_produto`) | Chip do gateway só recebe lead novo se `status_api = 'CONNECTED'`. |
| Checagem rápida (`tasks.verificar_status_wpp_web`) | A cada **2 min**, só chips do gateway (consulta o gateway, nunca a Meta). Sem ela, uma queda só era percebida na checagem horária (:20). Não alerta o admin em falha (evita spam). |
| Admin (`admin/views.py`, `numeros_whatsapp.html`, `numero_qr.html`, `wpp_web_gateway.py`) | Seletor de provedor; cadastro coerente (`web-<telefone>` + `GATEWAY_TOKEN_WPP`, recusa incoerência); tela **Parear (QR)** (só admin) que cria o chip, **configura o webhook sozinho** e grava `status_api`; **Remover** um número do gateway desconecta o chip lá (só admin, com confirmação); **Recriar do zero** (só admin, na tela de QR) apaga a sessão do chip no gateway e recria vazio — ver seção 15. |
| Recursos só da Meta | Template, `block_users`: erro claro para número do gateway (não mandam o token do gateway à Meta). |
| Testes | `tests/whatsapp/` (pytest, sem banco nem rede). `pytest.ini` não precisa de ajuste: o `conftest.py` da pasta põe `app/` no `sys.path`. |

## 3. Variáveis de ambiente (vendas-web)

| Variável | Onde | Para quê |
|---|---|---|
| `WPP_WEB_API_URL` | app + 3 workers | Base do gateway, com `/vNN.N/` (ex.: `https://apiwppweb.site/v24.0/`). Vazio = número `wpp_web` não envia (erro explícito). |
| `GATEWAY_TOKEN_WPP` | app + 3 workers | Bearer do gateway (= `GATEWAY_TOKEN` do `.env` do gateway). É o `token_env_key` dos chips do gateway. |
| `WPP_WEB_WEBHOOK_URL` | app | URL que o gateway chama para entregar mensagens; o admin a grava no chip ao parear. O **host** precisa estar em `WhatsAppSecurity._HOST_SECRET_MAP` (dele sai o segredo que assina o webhook). |
| `APP_BASE_URL` | app + 3 workers | Já existia (e-mail de entrega, follow-ups da web). Passa a ser também o domínio do link da Estante para número do gateway quando o pedido não tem `dns_origem`. **Precisa ser a URL do site em produção**, não `http://localhost`. |
| `WHATSAPP_API_URL` | app + 3 workers | **Só dev**: `http://127.0.0.1:9/` bloqueia qualquer chamada à Meta. Vazio/ausente em produção = Graph API. |

Depois de mudar `config.py` ou o `.env`: `docker compose up -d --build` (o código fica dentro da imagem) e
`make reload-nginx` (container recriado ganha IP novo; sem isso, 502).

## 4. Contrato: o que o vendas-web envia e o que o gateway faz

Todas as chamadas usam `Authorization: Bearer <GATEWAY_TOKEN>`. Base: `<WPP_WEB_API_URL>` (qualquer `vNN.N` serve). O
`phone_number_id` de um chip é `web-<numero>` (ex.: `web-5561982402450`).

| Função no vendas-web | Chamada | No gateway |
|---|---|---|
| `enviar_mensagem` | `POST /{id}/messages` `type:text` | Texto, com "digitando" e atraso humanizados. Responde `messages[0].id` (wamid) |
| `enviar_audio` | `type:audio` `{link, voice:true}` | Baixa o `link` e envia como nota de voz (PTT). ogg/opus validado |
| `enviar_imagem` | `type:image` `{link}` | Baixa o link e envia |
| `enviar_documento` | `type:document` `{link, filename, caption}` | Baixa o link e envia como arquivo (PDF de 25 MB validado) |
| `enviar_botao_link` | `interactive/cta_url` | **Vira texto**: corpo, `👉 <botão>` e o link |
| `enviar_mensagem_digitando`, `marcar_como_lida` | `status:read` (+ `typing_indicator`) | "Lida" + "digitando…" (some em 25 s). Confirmados no celular |
| `enviar_reacao` | `type:reaction` | **501**. Sem chamadores |
| `bloquear/desbloquear_numero_whatsapp` | `/{id}/block_users` | **Não existe** no gateway; o vendas-web recusa antes de chamar |
| `enviar_produto_whatsapp` (template) | `type:template` | **501**; o vendas-web recusa antes com mensagem clara |
| `receber_audio` | `GET /{media_id}` | `{url, mime_type, sha256, file_size}`; o `url` aponta para `/media/{id}` |
| `receber_comprovante` | `GET <image.url>` com Bearer | Serve o arquivo com `Content-Length` |
| Checagem de status | `GET /{id}` | `status` (`CONNECTED` ou, quando alguém precisa agir, `LOGGED_OUT`, `QR`, `CONFLICT`, ...), `quality_rating: UNKNOWN` |

Erros vêm no formato da Graph API. O vendas-web só depende do status HTTP e de `is_transient`: chip desconectado
responde **503 transitório**; número fora do WhatsApp, 400 (`131026`); link de mídia ruim, 400 (`131053`); link fora do
ar, 503.

**`MEDIA_BASE_URL` (no `.env` do gateway) precisa ser o endereço do gateway como o worker do vendas-web o enxerga**:
vai no `url` de imagem/documento/áudio do webhook. O padrão (`http://127.0.0.1:3100`) faz o download do comprovante falhar
**em silêncio** (o fluxo só registra "sem comprovante").

## 5. O webhook que o gateway envia

Formato da Meta (`entry[0].changes[0].value`), o mesmo que `extrair_dados_mensagem` lê: `metadata.phone_number_id =
web-<numero>`, `contacts[0].profile.name` (**obrigatório**: sem ele a mensagem é descartada; o gateway sempre manda),
`messages[0].{from, id, timestamp, type, text|image|document|audio}`. Tipos: `text`, `image`, `document`, `audio`.

- `messages[0].id` é o **wamid**, estável para a mesma mensagem: chave de idempotência (cabe em `VARCHAR(100)`).
- Remetente `@lid` (sem telefone): `from` vem vazio e `contacts[0].user_id` traz o `@lid`; responder para ele funciona.
  O `from` com telefone chegou no formato de 12 dígitos (sem o 9º dígito), o mesmo que o checkout grava (validado só com
  `556181163324`); **não testado com número de celular que chegue com 13 dígitos**, e `contact_phone` é comparado por igualdade.
- Assinatura: `X-Hub-Signature-256: sha256=<HMAC-SHA256 do corpo bruto>` com o segredo configurado **por chip**.
- Não há `statuses` (entregue/lido/falha), reações nem chamadas. O vendas-web não usa nenhum deles.

## 6. Segredo e domínio do webhook

O vendas-web escolhe o segredo pelo **Host** da requisição (`_HOST_SECRET_MAP`) e rejeita host não mapeado
(segredo vazio → assinatura inválida → 401). Não existe fallback por telefone. O gateway chama um host já mapeado e usa
**o mesmo segredo** desse host; o admin faz isso sozinho ao parear (`wpp_web_gateway.garantir_webhook`), a partir de
`WPP_WEB_WEBHOOK_URL`.

**Decisão (20/09/2026): `kpnlivros.com.br`.** A BM desse domínio foi banida pela Meta, então ela não entrega mais
webhook ali e o `WHATSAPP_APP_SECRET_KPN` pode ser **substituído por um segredo aleatório só do gateway**
(`openssl rand -hex 32`). Assim o App Secret real da Meta não vai para o `chips.json` do servidor do gateway, e não é
preciso criar domínio, bloco de nginx nem variável nova (o host já está em `_HOST_SECRET_MAP` e a variável já está nos 4
serviços do compose). O domínio resolve para o Hetzner e o webhook passa pelo `location /` do bloco 443 dele.

Condições e cuidados:
- **Defina `WHATSAPP_APP_SECRET_KPN` ANTES de parear o primeiro chip e não o troque depois.** O admin lê esse valor no
  momento do pareamento e o grava no chip; se o segredo mudar depois, o chip fica com o antigo e o webhook passa a dar
  401 (a outbox espera). Para corrigir: `wpp chip webhook <numero> <url> --secret <novo>` ou `PATCH /admin/chips/:id`.
- Confirmar em produção que nenhum número ativo usa `WHATSAPP_ACCESS_TOKEN_KPN`:
  `SELECT id, telefone FROM telefones_produto WHERE token_env_key = 'WHATSAPP_ACCESS_TOKEN_KPN'`.
- **O certificado do KPN é RapidSSL manual (`kpnlivros_chain.pem`) e vence em 12/11/2026.** O `infra/certbot/renew.sh`
  não o renova (só `livrinhosdigitais.site` e `leituraemais.site` estão no Let's Encrypt). Vencido, o gateway recusa o TLS
  e as mensagens ficam na outbox e depois vão para `dead`, sem alerta. Migrar o KPN para o Let's Encrypt é um assunto
  à parte, a ser tratado antes dessa data (runbook em `infra/certbot/README.md`).
- Se o domínio for trocado no futuro, os chips já pareados **mantêm a URL antiga** (`garantir_webhook` só configura chip
  sem webhook próprio): trocar por `wpp chip webhook`/`PATCH`.

Rate limit do nginx é **por IP** e todos os chips chegam do mesmo IP do gateway; como a entrega é serial por chip, não
deve incomodar, e um 503 é reentregue pela outbox.

## 7. Estado do chip e como o vendas-web percebe

O gateway percebe uma queda **na hora** (ex.: logout pelo celular → `LOGGED_OUT`, `needs_action`). O vendas-web percebe
por três caminhos:

1. `tasks.verificar_status_wpp_web`, **a cada 2 min**: grava `status_api` e o alerta "Status mudou de CONNECTED para
   LOGGED_OUT" em `notificacoes_telefone`.
2. A checagem horária de qualidade (:20), que também cobre os números do gateway.
3. Na hora do envio: 503 transitório do gateway (e a guarda `exigir_numero_operacional`).

Enquanto `status_api != CONNECTED`, o número não recebe lead novo, não envia pelos fluxos automáticos e o admin mostra o
status. `connecting`/`disconnected` (o gateway reconecta sozinho) contam como `CONNECTED`: o envio nesse intervalo
recebe 503 e é repetido, e uma oscilação de segundos não bloqueia o número. `quality_rating` é sempre `UNKNOWN` (tratado
como neutro no admin). O gateway **não empurra** mudança de estado (só polling/SSE).

Depois de um logout, o chip precisa de **Reiniciar pareamento** na tela de QR para gerar um QR novo.

## 8. Onboarding e desligamento de um número (admin)

- **Cadastrar:** *Produto → Números WhatsApp → Adicionar*: Display phone (`5561982402450`), Provedor "WhatsApp Web".
  `api_phone_number_id` e o token são preenchidos (`web-<telefone>`, `GATEWAY_TOKEN_WPP`); id/token incoerentes são
  recusados.
- **Parear:** botão **Parear (QR)** (só admin). Cria o chip no gateway, configura o webhook, mostra o QR (renova sozinho a
  cada ~20 s) e grava `status_api` ao conectar. O QR é credencial: não compartilhar a tela.
- **Remover:** desvincula o aparelho no WhatsApp, apaga a sessão e o cadastro do chip no gateway e só então apaga a
  linha (se o gateway falhar, a linha **não** é removida). Só admin, com confirmação.
- **Cuidado com a frequência:** cada re-pareamento é um evento de desvincular + vincular no WhatsApp. Faça com
  motivo e uma vez; não há (e não deve haver) re-pareamento automático.

## 9. Idempotência e ordem

A entrega do gateway é **pelo menos uma vez** e em ordem por chip. Um mesmo wamid pode chegar de novo; o vendas-web
deduplica pelo wamid no Redis por 25 h. Mensagens recuperadas após uma queda chegam com o **horário original** em
`timestamp`, mas o vendas-web não usa `timestamp` (usa `NOW()`), então isso não afeta os fluxos.

## 10. Operação, segurança e produção

**Endereço do gateway em produção: `https://apiwppweb.site`** (DNS aguardando propagar; SSL). Então:

```
# vendas-web (.env, Hetzner)
WPP_WEB_API_URL=https://apiwppweb.site/v24.0/
GATEWAY_TOKEN_WPP=<GATEWAY_TOKEN do gateway>
WPP_WEB_WEBHOOK_URL=https://kpnlivros.com.br/api/v1/webhook-whatsapp
WHATSAPP_APP_SECRET_KPN=<openssl rand -hex 32>   # antes de parear o 1º chip; não trocar depois

# gateway (.env, servidor do gateway)
MEDIA_BASE_URL=https://apiwppweb.site
```

- **HTTPS é obrigatório para tráfego real.** Pela ligação vendas-web ↔ gateway passam o token, o QR (credencial), os
  telefones e textos dos clientes e os comprovantes. HTTP puro por IP serve apenas como teste de conectividade com chip
  descartável.
- O gateway expõe `/admin/*` com o mesmo token. **Só o backend do vendas-web chama**; o navegador nunca (o QR é
  renderizado no servidor). Restrinja o acesso ao IP de saída do `app` **e dos workers** do vendas-web (no proxy
  reverso do gateway e/ou no firewall do provedor). O IP `87.99.145.114` foi informado como o do vendas-web:
  **confirmar** que app e workers saem por ele.
- **Deploy HTTPS do gateway:** o projeto dele traz `deploy/setup-https.sh` (nginx + Let's Encrypt, renovação pelo
  `certbot.timer`): `./wpp up` e depois `sudo ./deploy/setup-https.sh apiwppweb.site <email>`. O script exige DNS já
  apontando para o servidor e 80/443 abertos, aborta se existir `docker-compose.override.yml` publicando 80/443, e
  **grava `MEDIA_BASE_URL=https://apiwppweb.site` no `.env` do gateway**. O `nginx.conf` dele **não tem allowlist de IP**:
  o único cadeado é o `GATEWAY_TOKEN`. Recomendado, depois de emitir o certificado, no firewall do provedor: porta 80
  aberta (a renovação precisa; ela só redireciona) e **443 só para o IP do vendas-web**.
- Antes de produção, no gateway: remover os bind mounts `./src ./cli ./test` do compose, build para a arquitetura do
  servidor (provavelmente amd64; o desenvolvimento foi em arm64).
- `chips.json` guarda `appSecret` e a senha do proxy em texto: o volume e seus backups são sensíveis.
- A outbox move mensagens não entregues por 24 h para `outbox/dead` **sem alerta**; hoje só aparece em
  `GET /admin/outbox`. Recomenda-se o gateway alertar quando `dead > 0`.
- O gateway não tem rate limit, aquecimento nem teto diário por chip: o controle de volume depende do vendas-web
  (o `LIMIT` do follow-up passa a ser importante).
- Risco inerente: automação não oficial viola os termos do WhatsApp; chips podem ser banidos. Comece com poucos números.

## 11. Decisões em aberto

1. ~~Domínio do webhook~~ — decidido: `kpnlivros.com.br` (seção 6). Pendente: migrar o certificado dele para o Let's Encrypt antes de 12/11/2026.
2. Firewall do `apiwppweb.site`: 443 restrita ao IP do vendas-web (seção 10); confirmar o IP de saída do `app` e dos workers.
3. Se os produtos que forem para o gateway ainda usam a ação de template (`enviar_produto_whatsapp`,
   `confirmacao_web`): ela não existe no gateway e deve ser trocada por `enviar_produto`/`enviar_mensagem`. No banco de
   dev o produto 1 ainda a tem (dado antigo).
4. Links de mídia das ações dos fluxos precisam estar no ar: o gateway os baixa. O áudio do follow-up de pagamento do
   produto 1 (`s3.projetosdobruno.com/...`) está fora do ar (também falharia na Meta).

## 12. Correções ao documento original (para quem leu a versão anterior)

- `_PHONE_SECRET_MAP` **não existe**; só `_HOST_SECRET_MAP`.
- `numero_empresa_operacional` **não** bloqueava o envio automático (só a tela de conversa do admin). Passou a bloquear via
  `exigir_numero_operacional`.
- `montar_link_estante` quebrava para número do gateway (dependia do token por domínio). Depois, o primeiro teste em
  produção mostrou outra lacuna: cliente que manda mensagem direto ao número (sem site) não tem `dns_origem`, e o
  fluxo `pedido` parava sem responder. Corrigido com o fallback em `APP_BASE_URL`. **O fluxo `pedido` do produto 1 em dev
  não tem a ação `enviar_produto`**, então esse caminho só apareceu em produção: confira as ações de cada produto.
- O cache do token é permanente por processo (não invalida ao editar no admin); o do provedor é de 60 s.
- `pedidos.phone_number_id` era `VARCHAR(20)`.
- `marcar_como_lida` não tinha timeout.
- Não foi necessário coluna `api_base_url`: um único gateway, configurado por `WPP_WEB_API_URL`.

## 15. Pareamento travado: sessão do Chromium corrompida (achado em produção, 22/09/2026)

Um segundo chip do produto 11, em produção, ficou preso em `INIT_FAILED` com o erro
`Cannot read properties of null (reading 'Socket')` (lido dentro da página pelo `whatsapp-web.js`, em
`window.require('WAWebSocketModel').Socket` — código do próprio WhatsApp Web, não do gateway). **Nem restart do
container, nem "Reiniciar pareamento" (que só reinicia o processo), nem trocar o IP de saída por um proxy
resolveram** — todos repetiam o mesmo erro, porque nenhum deles apaga a pasta de sessão do chip
(`/data/sessions/session-<id>`). Ela ficou com um perfil de Chromium corrompido desde a primeira tentativa
falha, e cada tentativa nova reaproveitava a mesma pasta.

**Diagnóstico que isolou a causa:** o mesmo `Client` do `whatsapp-web.js`, no mesmo servidor, com `NoAuth`
(sessão descartável, sem gravar nada em disco) gerou o QR de primeira. A única diferença para o gateway de
verdade é o `LocalAuth` (sessão persistente em disco) — confirmando que a pasta em si era o problema, não rede,
não IP, não versão do Chromium/Puppeteer (checados e descartados nessa ordem antes de chegar aqui).

**Conserto:** `DELETE /admin/chips/:id` (apaga a sessão inteira) seguido de `POST /admin/chips` (recria vazio).
Isso agora é um botão só, **"Recriar do zero"**, na tela de pareamento do admin (`wpp_web_gateway.recriar_do_zero`),
ao lado de "Reiniciar pareamento". Use-o quando o restart simples não resolver um chip travado.

## 13. Como validar (resumo do que foi feito com chip real, em dev)

Entrada de texto, áudio e imagem; saída de texto, áudio, imagem e PDF (até 25 MB); `boas_vindas`, `pedido` e
`comprovante` com bônus; `responder` por texto e por áudio (transcrição + IA); os 3 follow-ups; chip caído (envio
adiado, sem rajada); app fora do ar (a outbox reentrega uma vez só); logout pelo celular percebido; onboarding
completo pelo admin (remover, cadastrar, parear por QR, webhook automático).

**Não validado:** produção (servidor real, amd64, proxy, HTTPS, domínio); dimensionamento com vários chips (~800 MB de
RAM por chip; só houve 1); áudio que não seja ogg/opus; link de mídia expirado do CDN.

### Receita de teste local
- Gateway: `cd ~/Desenv/JS/api-wpp-web && ./wpp up`; `MEDIA_BASE_URL=http://api-wpp-web:3100` no `.env` do gateway.
- O gateway (outra rede Docker) precisa alcançar o `app`: `docker network connect vendas-web_webnet api-wpp-web` e um alias
  de rede no `app` igual a um host mapeado (ex.: `--alias lsnlivros.com.br`); `WPP_WEB_WEBHOOK_URL=http://lsnlivros.com.br:8000/api/v1/webhook-whatsapp`.
  Recriar o container `app` desfaz o alias: refaça (`disconnect` + `connect --alias app --alias vendas-web-app --alias lsnlivros.com.br`) e `make reload-nginx`.
- `WHATSAPP_API_URL=http://127.0.0.1:9/` no `.env` de dev, para que nenhum pedido da base de dev alcance a Meta.

## 14. Onde está cada coisa

Gateway: `src/adapters/meta/` (formato Meta) · `src/api/graph.js` · `src/api/admin.js` · `src/chips/manager.js` (ciclo de
vida, envio, recepção, recuperação) · `src/chips/state.js` · `src/webhook/outbox.js` (fila em disco) · `src/media/`.

vendas-web: `app/wpp_web_gateway.py` (cliente do admin do gateway) · `app/whatsapp.py` (envio, `exigir_numero_operacional`,
`_timeout_envio`) · `app/database.py` (`get_provedor_numero`, `get_whatsapp_api_url`, `selecionar_telefone_produto`) ·
`app/tasks.py` (`verificar_status_wpp_web`, dedupe) · `app/fluxos/_executor_acao.py` · `app/admin/views.py` (seção
"Números WhatsApp") · `migrations/076_telefones_produto_provedor.sql` · `tests/whatsapp/`.

## 16. LOGOUT forçado ao chegar contato novo (achado 21-23/09/2026, mitigado 24/09/2026)

**Status: mitigado — acompanhando calibração.** A hipótese original desta seção (colisão do handshake de contato
novo com uma resincronização do socket) não foi a causa que se confirmou — ver "Atualização (24/09/2026)" no fim da
seção, que tem a causa real, a correção já implantada e o fechamento do caso. O texto original abaixo fica como
registro do raciocínio da investigação (inclusive o que descartamos), não como o estado atual.

### O que aconteceu

Dois números caíram com `LOGOUT` forçado pelo WhatsApp (não foi queda de rede/proxy nosso — ver seção seguinte):
- `web-5561982402450`: dois LOGOUTs no mesmo dia (21/09, 11:38 e 19:11) e foi **banido pela Meta** logo depois.
- `web-5561982397693`: um LOGOUT em 22/09 às 10:40. Número não bloqueado; ficou intencionalmente sem reparear até essa
  investigação.

### Causa provável (achada no código, ainda não confirmada como causa do LOGOUT em si)

Em `node_modules/whatsapp-web.js/src/Client.js` (versão 1.34.7, fixada no gateway), o handler que reage à sincronização
do app (`onAppStateHasSyncedEvent`, ligado a `WAWebSocketModel.Socket.on('change:hasSynced', ...)`) reemite
`AUTHENTICATED`/`READY` **toda vez** que essa propriedade interna do WhatsApp Web oscila — não só no login — e não tem
nenhuma proteção contra reemissão. Isso produz, no log do gateway, `sessão autenticada`/`conectado como` em dobro (às
vezes triplo ou mais) sem que exista de fato uma segunda sessão concorrente.

**Evidência que liga isso ao LOGOUT:** nos 3 incidentes conhecidos (os dois LOGOUTs de `.402450` e o de `.397693`), os
três tiveram a reemissão em dobro nos 7-33 s **antes** do LOGOUT, e os três tiveram, nesse mesmo intervalo, a chegada
da primeira mensagem de um contato `@lid` **nunca visto antes** por aquele chip (sequência `e2e_notification` →
`notification_template` → "aguardando descriptografia" → `chat`).

**Mas contato novo sozinho não basta**: em ~48h de logs de produção, tivemos 14 e 42 eventos de contato novo nos dois
chips — só 1 e 2, respectivamente, viraram LOGOUT (~5-7%). Ou seja, contato novo parece ser **condição necessária, mas
não suficiente**. A hipótese de trabalho é que o LOGOUT só acontece quando esse handshake de contato novo **coincide**
com uma resincronização do socket que já ia acontecer de qualquer forma (o WhatsApp Web faz isso sozinho, de tempos em
tempos, normalmente sem problema nenhum — confirmamos reemissões duplas/triplas/até 5x que **não** viraram LOGOUT,
sempre quando não havia contato novo por perto no mesmo instante).

**Não confirmado ainda**: se essa colisão é o gatilho de verdade, ou se ela é só uma coincidência de tempo e o
verdadeiro gatilho é outra coisa que também tende a acontecer perto de contato novo. Não sabemos, também, se a
resincronização em si é normal do WhatsApp Web ou sintoma de alguma instabilidade nossa (proxy, rede) nesses momentos
específicos.

### O que já foi testado e descartado

- **Não é container duplicado nem restart/start nosso**: confirmado nos 3 incidentes (só um container rodando, sem
  restart/health-check nosso nos minutos antes).
- **Não é volume/velocidade de envio**: um dos LOGOUTs (19:11 de 21/09) aconteceu sem nenhum envio nosso no meio — só
  recebendo a mensagem do contato novo.
- **Apagar o `pedido` no vendas-web não recria o handshake `e2e_notification`** (testado em sandbox local): resetar o
  "novo cliente" do lado do vendas-web não mexe na sessão de criptografia já estabelecida entre as duas contas do
  WhatsApp. Ou seja, não dá pra "reciclar" um número de teste já usado só apagando o pedido — precisa de uma
  identidade WhatsApp genuinamente nova (número novo, ou reinstalação completa do app do outro lado).
- **Teste em sandbox local não reproduziu o LOGOUT**: gateway + vendas-web rodando localmente (branch atual,
  `docker network connect` com alias `lsnlivros.com.br`, `WHATSAPP_API_URL` apontando pro vazio pra não vazar pra
  Meta), chip de teste descartável, 4 contatos novos únicos + 1 rajada simultânea + reaproveitamento (que não conta,
  ver item acima) — 0 reproduções. Não é surpresa dado o ~5-7% de taxa observada em produção; a amostra local foi
  pequena demais pra concluir algo.

### Instrumentação ativa (só log, sem mudar comportamento)

Adicionamos uma linha `console.log('[hasSynced] <timestamp ISO/UTC> chip=<id>')` bem no início do handler
`onAppStateHasSyncedEvent` do `Client.js`, direto no container rodando (via `docker exec` + `node --check` +
`docker compose restart gateway`). **De propósito não entrou no git nem em `patches/`** do gateway — o
`scripts/apply-patches.sh` aplica tudo que estiver lá em qualquer build, dev ou produção, e essa linha é só um
instrumento temporário de investigação. Ela vive só na camada gravável do container atual: um rebuild da imagem a
apaga silenciosamente, sem precisar lembrar de remover nada.

Ativa em produção desde 23/09/2026 ~01:28 (chip `web-5521984072653`, o número de teste do sandbox, reaproveitado
como novo número de produção) e ~01:32 (chip `web-5561982397693`, reconectado depois do LOGOUT do dia 22/09).
**Atenção ao fuso**: o `[hasSynced]` usa `toISOString()` (UTC); o resto do log do gateway usa hora local
(America/Sao_Paulo, UTC-3) — subtrair 3h do `[hasSynced]` pra comparar.

**Regra combinada enquanto isso roda**: se um chip cair com LOGOUT durante essa janela de observação, **não reparear
manualmente** — preservar o estado e os logs pra análise antes de qualquer ação. Reparear repetido no mesmo dia foi
provavelmente parte do que levou ao banimento do `.402450`.

### Por que ainda não subimos uma correção de comportamento

Sabemos **onde** o sintoma (reemissão dupla) acontece no código com bastante confiança. Não sabemos se **corrigir**
esse ponto (ex.: ignorar reemissões depois da primeira) evitaria o LOGOUT — a reemissão no Node é uma reação a uma
resincronização real que já está acontecendo dentro da página do WhatsApp Web (fora do nosso controle); suprimir só o
`emit()` do lado do Node não necessariamente impede o servidor da Meta de perceber o mesmo estado e agir do mesmo
jeito. Sem nenhuma reprodução controlada (nem local nem em produção até agora) pra comparar antes/depois, subir uma
mudança de comportamento seria arriscar quebrar algo que hoje funciona na maioria das vezes, sem garantia de resolver
o problema de verdade.

Relacionado (não confirmado como a mesma causa, mas mesma área do código, upstream): PRs abertos e sem revisão no
repositório `wwebjs/whatsapp-web.js` — [#201925](https://github.com/wwebjs/whatsapp-web.js/pull/201925) (bug conhecido
no tratamento de `@lid` em `MsgKey`) e [#201893](https://github.com/wwebjs/whatsapp-web.js/pull/201893) (condição de
corrida durante autenticação/navegação). Nenhum dos dois descreve o sintoma exato (`sessão autenticada` em dobro →
LOGOUT), mas confirmam que essa área da lib tem bugs de concorrência conhecidos e não corrigidos na versão 1.34.7
(último release: abril/2026).

### Próximo passo (histórico — superado pela atualização abaixo)

Revisar os logs acumulados de produção no fim do dia 23/09/2026 (`docker compose logs gateway | grep -Ei
"hasSynced|e2e_notification|desconectado: LOGOUT"`, convertendo fuso) com bem mais volume de contato novo real (tráfego
de campanha das 6h-22h) do que deu pra reunir no sandbox. Decidir a partir daí: (a) se o padrão de colisão se confirma
com mais casos, desenhar uma correção com dado real pra comparar antes/depois; (b) se não, procurar outro fator comum
entre os poucos LOGOUTs que já aconteceram.

### Atualização (24/09/2026): a causa real era memória, não a colisão com contato novo — corrigido e implantado

Revisando o dia inteiro de 23/09 (dois chips em paralelo, tráfego real de campanha), a hipótese da colisão não se
sustentou: o `web-5561982397693` recebeu **56 contatos novos** no dia (contra 12 do outro chip) e teve **zero
LOGOUT** — se fosse sobre contato novo colidir com resincronização, esse chip deveria ter caído mais, não menos.

**Causa real, com evidência direta**: o produto "Fatia" manda sempre os mesmos 3 documentos (até 57 MB) pra cada
cliente novo, em poucos segundos. Isso faz a memória do Chromium do chip **dobrar e não voltar ao normal**
(medido: 747→1508 MB, preso lá por 9 minutos) até a página do WhatsApp Web quebrar — e é essa quebra (não a colisão
com contato novo) que gera a reemissão dupla/múltipla de `AUTHENTICATED`/`READY` que a seção original descreveu, e
o LOGOUT em seguida.

**Linha do tempo completa do `web-5521984072653` em 23/09** (achada revisando o dia inteiro, não só o momento da
queda): o chip ficou saudável por **11h08** depois de conectar às 01:28. A partir do meio-dia entrou num padrão de
piora progressiva — 3 ciclos de "health check trava → reinicia" com o tempo de recuperação encolhendo a cada vez
(2h48 → 10 min → 15 min) — até a rajada de PDF das 15:51-15:53 e o colapso às 16:00:52. Ou seja, o chip já vinha
degradando havia horas antes do evento fatal; não foi um evento isolado do nada.

**Confirmado banido pela Meta** (visto no aparelho físico em 24/09/2026) — o gateway não tem como distinguir um
banimento de um logout comum (os dois aparecem como `LOGOUT`, sem mais nenhuma atividade depois), então essa
confirmação só veio de conferir o celular.

**Correção implantada** (commit `9517536`, produção desde 24/09/2026 ~08h): cache de mídia de saída (por nome do
arquivo, não pelo link — sobrevive a link de rastreio de campanha mudando), espaçamento mínimo anti-spam entre
mensagens, e o principal — a fila de um chip pausa quando a memória dele passa de um teto (1300 MB) e escala pra
reiniciar o chip sozinho se piorar ainda mais (1600 MB) ou 1x por dia de madrugada (restart preventivo), tudo só com
o chip ocioso. Passou por 6 rodadas de code review antes de ir pro ar (achou e corrigiu, entre outras coisas, uma
falha em que o próprio restart proativo por memória nunca conseguia disparar no cenário em que mais fazia falta).
Detalhe de implementação em `~/Desenv/JS/api-wpp-web/README.md`, seção "Comportamento de envio (proteção contra ban)".

**Métricas do dia 23/09 inteiro** (2 chips em paralelo, tráfego real): pico de 1508 MB no chip que caiu, container
inteiro chegou a 3570 MB de pico — num servidor de ~3,9 GB de RAM, 2 núcleos, sem swap (adicionamos 2 GB de swap
como rede de segurança extra no deploy). Estimativa de capacidade: **~4 chips em 8 GB**, ~9 em 16 GB — ainda uma
extrapolação linear, vale recalibrar depois de rodar com mais chips de verdade.

**Pendências**:
- Calibrar os tetos de memória (1300/1600 MB) com mais dias de dado real (`./wpp metrics` em produção) — são
  estimativas iniciais, baseadas só neste incidente.
- Remover `web-5561982402450` e `web-5521984072653` do cadastro (botão "Remover" no admin — ver seção 8): não
  reconhecem mais o número, e a checagem de status a cada 2 min (`tasks.verificar_status_wpp_web`) continua
  consultando o gateway por eles indefinidamente enquanto a linha existir.
- O log de diagnóstico `[hasSynced]` mencionado acima era temporário (vivia só na camada gravável do container) e
  se perdeu no rebuild do deploy — não é mais necessário, já que a correção real não dependia dele.
