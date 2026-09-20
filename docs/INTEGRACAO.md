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
| Link da Estante (`whatsapp.montar_link_estante`) | Número do gateway usa `pedidos.dns_origem` (o gateway não tem token por domínio). Sem `dns_origem` válido, erro explícito. |
| Dedupe do webhook (`tasks._WEBHOOK_DEDUPE_TTL_S`) | 300 s → 25 h. O gateway reentrega por até 24 h e `mensagens_pedidos.message_id` não é UNIQUE. |
| Chip caído (`whatsapp.exigir_numero_operacional`) | Executor de ações, follow-ups e `responder` **não enviam** com o chip fora (`ChipForaDoArWhatsApp`, transiente). Com status ruim, o gateway é consultado na hora antes de bloquear (status velho não segura o envio). Follow-up que perde o chip **no meio** da sequência é dado como concluído (não reenvia o que já saiu). |
| Sorteio de número (`database.selecionar_telefone_produto`) | Chip do gateway só recebe lead novo se `status_api = 'CONNECTED'`. |
| Checagem rápida (`tasks.verificar_status_wpp_web`) | A cada **2 min**, só chips do gateway (consulta o gateway, nunca a Meta). Sem ela, uma queda só era percebida na checagem horária (:20). Não alerta o admin em falha (evita spam). |
| Admin (`admin/views.py`, `numeros_whatsapp.html`, `numero_qr.html`, `wpp_web_gateway.py`) | Seletor de provedor; cadastro coerente (`web-<telefone>` + `GATEWAY_TOKEN_WPP`, recusa incoerência); tela **Parear (QR)** (só admin) que cria o chip, **configura o webhook sozinho** e grava `status_api`; **Remover** um número do gateway desconecta o chip lá (só admin, com confirmação). |
| Recursos só da Meta | Template, `block_users`: erro claro para número do gateway (não mandam o token do gateway à Meta). |
| Testes | `tests/whatsapp/` (pytest, sem banco nem rede). `pytest.ini` não precisa de ajuste: o `conftest.py` da pasta põe `app/` no `sys.path`. |

## 3. Variáveis de ambiente (vendas-web)

| Variável | Onde | Para quê |
|---|---|---|
| `WPP_WEB_API_URL` | app + 3 workers | Base do gateway, com `/vNN.N/` (ex.: `https://apiwppweb.site/v24.0/`). Vazio = número `wpp_web` não envia (erro explícito). |
| `GATEWAY_TOKEN_WPP` | app + 3 workers | Bearer do gateway (= `GATEWAY_TOKEN` do `.env` do gateway). É o `token_env_key` dos chips do gateway. |
| `WPP_WEB_WEBHOOK_URL` | app | URL que o gateway chama para entregar mensagens; o admin a grava no chip ao parear. O **host** precisa estar em `WhatsAppSecurity._HOST_SECRET_MAP` (dele sai o segredo que assina o webhook). |
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
- `montar_link_estante` quebrava para número do gateway (dependia do token por domínio).
- O cache do token é permanente por processo (não invalida ao editar no admin); o do provedor é de 60 s.
- `pedidos.phone_number_id` era `VARCHAR(20)`.
- `marcar_como_lida` não tinha timeout.
- Não foi necessário coluna `api_base_url`: um único gateway, configurado por `WPP_WEB_API_URL`.

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
