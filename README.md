# 🛒 Vendas Web

Sistema de vendas via WhatsApp Business API com Flask, Celery e MySQL, orientado por fluxos e configuração por produto.

## ✅ Visão geral

- Webhook recebe mensagens e orquestra o fluxo por estado do pedido.
- Processamento assíncrono via Celery (`worker`) com Redis.
- Persistência no MySQL (`pedidos`, `mensagens_pedidos`, `produtos`).
- Fluxos usam parâmetros da tabela `produtos` (sem hardcode/fallback silencioso).
- Stack de execução: Gunicorn + Nginx + Docker Compose.

## 🧱 Arquitetura rápida

- `app/app.py`: API Flask + endpoints de webhook/health.
- `app/whatsapp_orquestrador.py`: roteamento por estado/tipo de mensagem.
- `app/fluxos/`: regras de negócio (`introducao`, `pedido`, `comprovante`, `responder`, etc.).
- `app/agente_resposta_produto.py`: agente de resposta contextual (prompt + FAQ + conteúdo do produto).
- `app/agente_verifica_interesse.py`: classificador enxuto de intenção (`sim`/`não`).
- `migrations/001_script.sql`: schema e seed inicial.

## 📦 Pré-requisitos

- Docker e Docker Compose
- Conta WhatsApp Business API
- Chave da OpenAI (fluxos com IA)

## 🚀 Subir ambiente

```bash
# 1) Configure o .env
cp .env.example .env

# 2) Suba os serviços
docker compose up -d --build

# 3) Verifique saúde
docker compose ps
curl http://localhost/health
```

## 🔐 Variáveis de ambiente mínimas

Use os nomes esperados no `docker-compose.yml`:

```bash
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=

MYSQL_ROOT_PASSWORD=
MYSQL_PASSWORD=

OPENAI_API_KEY=
LOG_LEVEL=info
```

## 🗃️ Configuração por produto (obrigatória)

Os fluxos leem campos da tabela `produtos`. Com campo ausente, o fluxo lança erro para evitar envio incorreto.

Principais campos usados hoje:

- **Responder**: `prompt_vendas`, `url_faq_produto`, `url_arquivo_produto`
- **Introdução**: `url_audio_introducao`, `url_audio_explicativo`, `url_imagem_complementar`, `mensagem_introducao`
- **Pedido**: `url_arquivo_produto`, `caption_arquivo_produto`, `nome_arquivo_produto`, `url_audio_pedido_entregue`, `mensagem_pedido_enviado_sem_interesse`, `mensagem_para_pagamento`, `chave_pix`
- **Comprovante**: `pix_destinatario_esperado`, `valor_minimo_pagamento`, `mensagem_pagamento_confirmado`, `mensagem_comprovante_invalido`, `url_arquivo_surpresa`, `caption_arquivo_surpresa`, `nome_arquivo_surpresa`

## 🔁 Fluxos principais

- `fluxo_introducao`: primeira sequência de contexto (áudios/imagem/mensagem)
- `fluxo_pedido`: classifica interesse, envia produto, orienta pagamento
- `fluxo_comprovante`: valida comprovante, confirma pagamento e entrega surpresa
- `fluxo_responder`: respostas livres com contexto completo do produto

## 🗄️ Migrations

As migrations ficam em `migrations/` e seguem a numeração `NNN_descricao.sql`.

### Executar uma migration

```bash
docker compose exec -T db mysql -u appuser -pu9p1s8a0 vendasdb < migrations/006_faq_produto.sql
```

> **Dica:** troque `006_faq_produto.sql` pelo arquivo desejado. A flag `-T` é necessária quando a execução não é interativa (terminal sem TTY).

### Verificar se a coluna/tabela foi criada

```bash
# listar colunas de uma tabela
docker compose exec db mysql -u appuser -pu9p1s8a0 vendasdb -e "DESCRIBE produtos;"

# listar todas as tabelas
docker compose exec db mysql -u appuser -pu9p1s8a0 vendasdb -e "SHOW TABLES;"
```

### Histórico de migrations aplicadas

| Arquivo | Descrição |
|---|---|
| `001_script.sql` | Schema e seed inicial |
| `002_*.sql` | ... |
| `003_*.sql` | ... |
| `004_*.sql` | ... |
| `005_acoes_fluxo_produto.sql` | Tabela `acoes_fluxo_produto` (fluxos dinâmicos) |
| `006_faq_produto.sql` | Coluna `faq` na tabela `produtos` |

---

## 🧪 Comandos úteis

```bash
# Atalhos (Makefile)
make help
make upload-google-ads-now
make logs-worker
make logs-files
make restart-worker

# Logs
docker compose logs -f app
docker compose logs -f worker

# Rebuild de serviço específico
docker compose up -d --build app
docker compose up -d --build worker

# Verificar banco
docker compose exec app python scripts/verificar_bd.py

# Acessar MySQL
docker compose exec db mysql -uappuser -p vendasdb
```

## 🗂️ Logs rotacionados para auditoria

O sistema gera logs em arquivo com rotação diária (virada de dia), incluindo app e worker.

Padrão de nomes:

- `log_app_YYYY_MM_DD_001.log`
- `log_worker_YYYY_MM_DD_001.log`

Comandos úteis:

```bash
# Aplicar alterações de env/logging
docker compose up -d --force-recreate app worker

# Listar arquivos de log no container
docker compose exec worker ls -lah /app/storage/logs

# Conferir variáveis Google Ads no worker
docker compose exec worker env | grep GOOGLE_ADS
```

## 🧹 Reset de ambiente (desenvolvimento)

```bash
docker compose down -v
docker compose up -d --build
```

## 📚 Documentação complementar

- `docs/DATABASE_SETUP.md`
- `docs/WEBHOOK_WHATSAPP.md`
- `docs/SEGURANCA.md`
- `docs/NOTIFICACOES.md`

---

## 🐞 Troubleshooting

### MySQL não inicia

```bash
# Verificar logs
docker compose logs db

# Verificar permissões do volume
ls -la /var/lib/mysql-vendas

# Corrigir permissões
sudo chown -R 999:999 /var/lib/mysql-vendas
```

### Aplicação não conecta ao BD

```bash
# Testar conexão
docker compose exec app python scripts/verificar_bd.py

# Ver variáveis de ambiente
docker compose exec app env | grep DB_

# Verificar health check do MySQL
docker compose ps
```

### Webhook não recebe mensagens

```bash
# Ver logs do app
docker compose logs -f app

# Testar endpoint
curl -X GET "http://localhost/api/v1/webhook-whatsapp?hub.mode=subscribe&hub.verify_token=SEU_TOKEN&hub.challenge=CHALLENGE123"

# Verificar assinatura HMAC nos logs
docker compose logs app | grep "Hub-Signature"
```

### Nginx não funciona após build (precisa de restart)

**Problema resolvido!** ✅ A partir de agora o nginx aguarda o app estar saudável antes de iniciar.

**Como funcionava antes:**
- Nginx tentava resolver `app:8000` antes do app estar pronto
- Cacheia a falha de DNS
- Precisava de `docker compose restart nginx` para forçar nova resolução

**Solução implementada:**
- Health check no serviço `app` (rota `/health`)
- Nginx usa `depends_on` com `condition: service_healthy`
- Aguarda 30 segundos para app inicializar (`start_period`)

```bash
# Verificar status dos serviços
docker compose ps

# Ver se health checks estão OK
docker compose ps | grep -E "(healthy|unhealthy)"

# Testar health check manualmente
curl http://localhost/health
```

---

## 🔐 Segurança

- ✅ Validação HMAC-SHA256 dos webhooks
- ✅ Senhas em variáveis de ambiente (não no código)
- ✅ `.env` no `.gitignore`
- ✅ HTTPS configurado (Nginx)
- ⚠️ Configure rate limiting em produção
- ⚠️ Use senhas fortes (mínimo 16 caracteres)

---

## 🎯 Próximos Passos

- [ ] Implementar lógica de negócio completa (webhook ↔ BD)
- [ ] Adicionar agente de IA com OpenAI
- [ ] Criar testes unitários
- [ ] Implementar dashboard administrativo
- [ ] Adicionar monitoramento (Prometheus/Grafana)
- [ ] Configurar CI/CD pipeline

---

## 📄 Licença

Este projeto é privado.

---

## 👤 Autor

**Leo SN**
- Email: leosn1006@gmail.com
- GitHub: [@leosn1006](https://github.com/leosn1006)

---

## 🙏 Contribuindo

Para contribuir com este projeto:

1. Leia [CODE_REVIEW_ATUALIZADO.md](CODE_REVIEW_ATUALIZADO.md)
2. Crie uma branch (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

---
Arquiterura para followup

Celery Beat (agendador)
        │
        │ todo hora verifica horário comercial
        ▼
Celery Worker
        │
        │ busca pedidos estado=3, data_ultima_atualizacao > 4h
        ▼
    MySQL
        │
        │ para cada pedido encontrado
        ▼
    WhatsApp API (envia followup)

**Última Atualização:** 23/02/2026
