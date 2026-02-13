# Configuração do Webhook WhatsApp Business API

## 📋 Pré-requisitos

1. Ter uma conta Meta for Developers (https://developers.facebook.com)
2. Criar um App no Meta for Developers
3. Adicionar o produto "WhatsApp" ao seu App
4. Ter um número de telefone verificado no WhatsApp Business

---

## 🔑 Obtendo as Credenciais

### 1. **App Secret** (`WHATSAPP_APP_SECRET`)
   - Acesse: https://developers.facebook.com/apps
   - Selecione seu App
   - Vá em **Configurações** → **Básico**
   - Copie o valor de **"Chave secreta do app"**

### 2. **Access Token** (`WHATSAPP_ACCESS_TOKEN`)
   - No seu App, vá em **WhatsApp** → **Introdução**
   - Na seção "Token de acesso temporário", copie o token
   - ⚠️ **Importante**: Este é um token temporário (24h)
   - Para produção, gere um token permanente:
     - Vá em **WhatsApp** → **Configurações** → **API Setup**
     - Clique em "Generate Token" e salve com segurança

### 3. **Phone Number ID** (`WHATSAPP_PHONE_NUMBER_ID`)
   - No seu App, vá em **WhatsApp** → **Introdução**
   - Na seção "De", copie o **Phone Number ID**
   - Exemplo: `123456789012345`

### 4. **Business Account ID** (`WHATSAPP_BUSINESS_ACCOUNT_ID`)
   - No seu App, vá em **WhatsApp** → **Configurações**
   - Copie o **WhatsApp Business Account ID**

### 5. **Verify Token** (`WHATSAPP_VERIFY_TOKEN`)
   - Este você **cria** (pode ser qualquer string segura)
   - Exemplo: `meu_token_verificacao_12345`
   - Você vai usar esse mesmo valor ao configurar o webhook no Meta

---

## ⚙️ Configurando o Projeto

### 1. Copie o arquivo de exemplo
```bash
cp .env.example .env
```

### 2. Edite o arquivo `.env` com suas credenciais
```bash
nano .env
```

```env
WHATSAPP_VERIFY_TOKEN=meu_token_verificacao_12345
WHATSAPP_APP_SECRET=abc123def456...
WHATSAPP_ACCESS_TOKEN=EAABsbCS...
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321098765
```

### 3. Suba o container
```bash
docker-compose up -d --build
```

---

## 🌐 Configurando o Webhook no Meta

### 1. Torne seu servidor acessível publicamente
   - Use **ngrok** (para testes):
     ```bash
     ngrok http 80
     ```
   - Use seu domínio (produção): `https://seudominio.com`

### 2. Configure no Meta for Developers
   - Acesse: https://developers.facebook.com/apps
   - Selecione seu App
   - Vá em **WhatsApp** → **Configurações**
   - Na seção **Webhook**, clique em **"Editar"**

### 3. Preencha os campos:
   - **URL de retorno**: `https://seudominio.com/api/v1/webhook-whatsapp`
   - **Token de verificação**: O mesmo valor que você colocou em `WHATSAPP_VERIFY_TOKEN`
   - Clique em **"Verificar e salvar"**

### 4. Assine os eventos
   - Marque os eventos que deseja receber:
     - ✅ `messages` (mensagens recebidas)
     - ✅ `message_status` (status de entrega)
   - Clique em **"Salvar"**

---

## ✅ Como Funciona a Validação

### 1. **Verificação inicial (GET)**
Quando você configura o webhook, o WhatsApp faz uma requisição GET:
```
GET /api/v1/webhook-whatsapp?hub.mode=subscribe&hub.verify_token=SEU_TOKEN&hub.challenge=CHALLENGE_STRING
```
Seu servidor valida o `hub.verify_token` e retorna o `hub.challenge`.

### 2. **Recebimento de mensagens (POST)**
Quando alguém envia uma mensagem, o WhatsApp faz uma requisição POST:
```bash
POST /api/v1/webhook-whatsapp
Headers:
  X-Hub-Signature-256: sha256=HMAC_DO_PAYLOAD
Body:
  { ... dados da mensagem ... }
```
Seu servidor:
1. Calcula o HMAC-SHA256 do payload usando `WHATSAPP_APP_SECRET`
2. Compara com o valor do header `X-Hub-Signature-256`
3. Se válido, processa a mensagem

---

## 🧪 Testando o Webhook

### Teste manual com curl:
```bash
# 1. Simular verificação (GET)
curl "http://localhost/api/v1/webhook-whatsapp?hub.mode=subscribe&hub.verify_token=SEU_TOKEN&hub.challenge=teste123"

# Deve retornar: teste123
```

### Testar assinatura (POST):
```bash
# Calcular assinatura HMAC-SHA256
PAYLOAD='{"test": "data"}'
SECRET="seu-app-secret"
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')

# Fazer requisição
curl -X POST http://localhost/api/v1/webhook-whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=$SIGNATURE" \
  -d "$PAYLOAD"
```

---

## 🔒 Segurança

✅ **O que está implementado:**
- Validação de assinatura HMAC-SHA256 em todas as mensagens
- Verificação de token na configuração inicial
- Comparação segura usando `hmac.compare_digest()`
- Variáveis de ambiente para credenciais sensíveis

⚠️ **Boas práticas:**
- Nunca commite o arquivo `.env` no Git
- Use tokens permanentes em produção (não tokens temporários de 24h)
- Configure HTTPS em produção (obrigatório pelo WhatsApp)
- Monitore logs de tentativas de acesso inválidas

---

## 📚 Documentação Oficial

- [WhatsApp Business API - Webhooks](https://developers.facebook.com/docs/whatsapp/webhooks)
- [Meta for Developers - Webhooks](https://developers.facebook.com/docs/graph-api/webhooks)
- [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api)

---

## 🐛 Troubleshooting

### Erro: "Token de verificação inválido"
- Verifique se `WHATSAPP_VERIFY_TOKEN` no `.env` é igual ao configurado no Meta

### Erro: "Assinatura inválida"
- Verifique se `WHATSAPP_APP_SECRET` está correto
- Confira se não há espaços extras no `.env`
- Veja os logs: `docker-compose logs -f app`

### Webhook não recebe mensagens
- Verifique se os eventos estão assinados no Meta
- Teste com ngrok se estiver em desenvolvimento local
- Verifique os logs do Meta: Painel → Webhooks → Ver eventos recentes
