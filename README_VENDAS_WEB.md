# Arquitetura — vendas-web

Sistema de vendas com dois canais: **WhatsApp** e **Web (checkout PIX)**.

---

## Arquitetura Geral

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Nginx (80/443)  ←  SSL termination, proxy reverso  │
└──────────────────────────┬──────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Flask App  │  (Gunicorn, porta 8000)
                    └──────┬──────┘
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──┐  ┌──────▼──┐  ┌─────▼──────┐
       │ Blueprint│  │Blueprint│  │  Routes    │
       │  /admin  │  │  /web   │  │  (app.py)  │
       └──────────┘  └─────────┘  └────────────┘
```

---

## Infraestrutura (Docker)

| Container | Papel |
|---|---|
| `nginx` | Proxy reverso + SSL (80/443) |
| `app` | Flask via Gunicorn |
| `worker` | Celery worker (concurrency=2) |
| `beat` | Celery beat (agendador de tarefas periódicas) |
| `flower` | Monitor de tarefas Celery (porta 5555) |
| `db` | MySQL 8.4 |
| `redis` | Broker Celery |

---

## Módulos da Aplicação (`app/`)

### Flask — Blueprints e Rotas

**`app.py`** — rotas principais:
- `GET/POST /api/v1/webhook-whatsapp` — entrada dos eventos do WhatsApp
- `POST /api/v1/webhook/gravar-lide` — captura de leads externos
- `/`, `/portifolio`, `/politica-privacidade`, etc. — páginas públicas

**Blueprint `/web`** (`app/web/__init__.py`):
- `GET /pay/<produto_id>` — checkout web
- `POST /api/v1/pix/gerar` — gera PIX (Banco do Brasil)
- `GET /api/v1/pix/status/<txid>` — status do pagamento
- `GET /api/v1/produto/pdf/<pedido_id>` — entrega do produto digital

**Blueprint `/admin`** (`app/admin/views.py`):
- Dashboard, CRUD de produtos e usuários
- Conversas (visualizar e enviar mensagens manuais)
- Fluxos dinâmicos (adicionar/editar/remover ações)
- Upload de arquivos (imagens, áudios, PDFs)
- Analytics por produto
- Números WhatsApp, mensagens sugeridas, FAQ

---

### Fluxos de Automação (`app/fluxos/`)

Cada fluxo é executado por uma **Celery task** assíncrona:

| Task | Fluxo | Trigger |
|---|---|---|
| `enviar_introducao_dinamico` | `fluxo_introducao_dinamico.py` | 1º contato via WhatsApp |
| `enviar_pedido_dinamico` | `fluxo_pedido_dinamico.py` | Pedido registrado |
| `responder_mensagem` | `fluxo_responder.py` | Mensagem recebida (IA) |
| `conferir_comprovante_dinamico` | `fluxo_comprovante_dinamico.py` | Imagem recebida (IA valida) |
| `transcrever_audio` | `fluxo_transcrever.py` | Áudio recebido |
| `followup_pagamento_dinamico` | `fluxo_followup_dinamico.py` | Agendado (beat) |
| `enviar_confirmacao_web` | `fluxo_confirmacao_web_dinamico.py` | Pagamento PIX confirmado |
| `processar_uploads_google_ads` | `fluxo_upload_google_ads.py` | Agendado (beat) |
| `processar_uploads_google_sheets` | idem | Agendado (beat) |

---

### Agentes de IA (`app/agente_*.py`)

| Agente | Função |
|---|---|
| `agente_resposta_produto` | Gera resposta contextual por produto (OpenAI) |
| `agente_gera_mensagem_inicial` | Cria mensagem de abertura personalizada |
| `agente_valida_comprovante` | Analisa imagem de comprovante de pagamento |
| `agente_transcricao` | Transcreve áudios recebidos |
| `agente_verifica_interesse` | Detecta intenção de compra na conversa |

---

### Banco de Dados

11 migrations em `migrations/`, principais tabelas:

| Tabela | Conteúdo |
|---|---|
| `produtos` | Configurações por produto (preço, IA, PIX, Google Ads) |
| `pedidos` | Cada lead/pedido com estado e GCLID |
| `acoes_fluxo_produto` | Ações dinâmicas por fluxo (editáveis via admin) |
| `mensagens_whatsapp` | Histórico de conversas |
| `usuarios` | Acesso ao painel admin |
| `telefones_produto` | Números WhatsApp Business por produto |
| `mensagens_sugeridas` | Respostas rápidas configuráveis |
| `faq_produto` | Base de conhecimento para o agente de IA |

---

### Fluxo de uma Venda Completa (WhatsApp)

```
Lead chega via WhatsApp
        │
        ▼
whatsapp_orquestrador.py
  └── roteia por produto/fluxo
        │
        ├─► fluxo_introducao → apresenta produto
        │
        ├─► fluxo_pedido → registra pedido + gera PIX
        │
        ├─► fluxo_comprovante → valida pagamento via IA
        │
        ├─► fluxo_confirmacao_web → confirma venda + entrega PDF
        │
        ├─► fluxo_followup → sequência de follow-up agendada
        │
        └─► Google Ads / Google Sheets → conversão registrada
```

---

## Venda Web — Checkout PIX

### Fluxo Completo

```
Cliente (Browser)
     │
     ▼
GET /pay/<produto_id>          ← página de checkout
     │
     ▼  (preenche nome, whatsapp, email + captura gclid/utm)
POST /api/v1/pix/gerar         ← gera pedido + cobrança PIX
     │
     ├─► cria pedido no DB (estado 1001)
     ├─► chama BB Pay API → cria solicitação PIX
     ├─► salva txid + QR code (estado 1002)
     └─► retorna { txid, qrcode_base64, qrcode_texto, url_bbpay }
     │
     ▼  (cliente paga via QR code ou link BB Pay)
GET /api/v1/pix/status/<txid>  ← frontend faz polling
     │
     ├─► consulta BB Pay API (verifica codigoEstadoPagamento == 200)
     ├─► se pago: confirma no DB (estado 1000) + data_pagamento
     └─► dispara task Celery: enviar_confirmacao_web.delay(pedido_id)
     │
     ▼
[Celery Worker]
  fluxo_confirmacao_web_dinamico.executar(pedido_id)
     │
     ├─► lê ações de acoes_fluxo_produto (fluxo='confirmacao_web')
     ├─► executa cada ação via _executor_acao (envia PDF/áudio/msg via WhatsApp)
     └─► marcar_ebook_enviado() → registra data_envio_ebook
```

### Estados do Pedido (`pedidos.estado_id`)

| Código | Significado |
|---|---|
| `1001` | Pedido web criado (aguardando geração do PIX) |
| `1002` | Aguardando pagamento (PIX gerado, expira em 24h) |
| `1000` | **Pago e confirmado** |

### Rotas da API Web

| Método | Rota | Função |
|---|---|---|
| `GET` | `/pay/<produto_id>` | Renderiza página de checkout |
| `POST` | `/api/v1/pix/gerar` | Cria pedido + gera QR PIX |
| `GET` | `/api/v1/pix/pedido/<pedido_id>` | Retorna txid e estado do pedido |
| `GET` | `/api/v1/pix/status/<txid>` | Verifica se foi pago (polling) |
| `GET` | `/api/v1/produto/pdf/<pedido_id>` | Serve PDF do produto (legado) |
| `GET` | `/api/v1/produto/pdf/<pedido_id>/bonus` | Serve PDF bônus (legado) |

### Arquivos Envolvidos

| Arquivo | Responsabilidade |
|---|---|
| `app/web/__init__.py` | Rotas Flask (Blueprint `/web`) — roteamento puro |
| `app/web/checkout.py` | Orquestrador: gera PIX, verifica pagamento, entrega PDF |
| `app/web/bb_pay.py` | Client da API BB Pay (OAuth 2.0 + mTLS) |
| `app/fluxos/fluxo_confirmacao_web_dinamico.py` | Executa ações pós-pagamento (envia produto via WhatsApp) |
| `app/tasks.py` | Task Celery `enviar_confirmacao_web` (max 2 retries, 60s) |
| `app/database.py` | Funções DB do ciclo de vida do pedido web |

### Dados Capturados na Geração do Pedido

Todos salvos em `pedidos`:

| Campo | Origem |
|---|---|
| `contact_name` | Nome informado no checkout |
| `contact_phone` | WhatsApp informado no checkout |
| `email` | E-mail informado no checkout |
| `gclid` | Google Click ID (Google Ads) |
| `campaignid`, `adgroupid` | Rastreamento de campanha |
| `creative`, `matchtype`, `device` | Rastreamento de anúncio |
| `placement`, `video_id` | Rastreamento de posicionamento |

### BB Pay (Banco do Brasil)

- Autenticação: **OAuth 2.0 client_credentials** com **mTLS** (certificado `.pem` + `.key`)
- `criar_solicitacao()` → `POST /v2/solicitacoes` — gera QR PIX, validade 24h, pagamento único
- `consultar_pagamentos()` → `GET /v2/pagamentos` — confirma se `codigoEstadoPagamento == 200`

### Entrega do Produto (pós-pagamento)

O fluxo `confirmacao_web` é **totalmente dinâmico** — as ações ficam na tabela `acoes_fluxo_produto`
(coluna `fluxo = 'confirmacao_web'`) e são editáveis via admin em `/admin/produto/<id>/fluxos`.
Pode enviar qualquer combinação de mensagens, áudios, imagens ou arquivos via WhatsApp para o comprador.
