# 🛒 Vendas Web - Sistema de Vendas com WhatsApp

Sistema de vendas integrado com WhatsApp Business API, desenvolvido em Python (Flask) com MySQL para persistência de dados.

## 📋 Índice

- [Características](#-características)
- [Tecnologias](#-tecnologias)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação](#-instalação)
- [Uso](#-uso)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Documentação](#-documentação)
- [Comandos Úteis](#-comandos-úteis)

---

## ✨ Características

- 🤖 **Integração com WhatsApp Business API** - Recebe e envia mensagens
- 🗄️ **Banco de Dados MySQL** - Persistência de pedidos e mensagens
- 🐳 **Docker** - Ambiente containerizado completo
- 🔒 **Segurança** - Validação HMAC de webhooks
- 🚀 **Produção Ready** - Gunicorn + Nginx com SSL
- 📊 **Pool de Conexões** - Gerenciamento eficiente do BD
- 🔄 **Auto-migrations** - Scripts SQL executados automaticamente

---

## 🛠️ Tecnologias

- **Backend:** Python 3.12, Flask 3.1.2
- **Servidor:** Gunicorn, Nginx 1.27
- **Banco de Dados:** MySQL 8.4
- **Containerização:** Docker, Docker Compose
- **Integrações:** WhatsApp Business API, OpenAI (opcional)

---

## 📦 Pré-requisitos

- Docker e Docker Compose instalados
- Ubuntu Linux (para persistência de dados)
- Conta WhatsApp Business API
- Permissões sudo

---

## 🚀 Instalação

### 1. Clonar o repositório

```bash
git clone git@github.com:leosn1006/vendas-web.git
cd vendas-web
```

### 2. Configurar variáveis de ambiente

```bash
# Copiar template
cp .env.example .env

# Editar com suas credenciais
nano .env
```

**Variáveis obrigatórias:**
```bash
# WhatsApp Business API
WHATSAPP_VERIFY_TOKEN=seu-token-verificacao
WHATSAPP_APP_SECRET=seu-app-secret
WHATSAPP_ACCESS_TOKEN=seu-access-token
WHATSAPP_PHONE_NUMBER_ID=seu-phone-number-id

# MySQL (use senhas fortes!)
MYSQL_ROOT_PASSWORD=senha-root-segura
MYSQL_PASSWORD=senha-app-segura
```

### 3. Configurar volume do MySQL (Ubuntu)

```bash
# Criar diretório para persistência
sudo mkdir -p /var/lib/mysql-vendas

# Configurar permissões (UID 999 = mysql no container)
sudo chown -R 999:999 /var/lib/mysql-vendas
```

### 4. Iniciar os containers

```bash
# Build e start
docker compose up -d --build

# Verificar status
docker compose ps

# Ver logs
docker compose logs -f

# Ver só logs do ForkPoolWorker-1
docker compose logs -f worker | grep "ForkPoolWorker-1"

# Ver só logs de tasks bem sucedidas
docker compose logs -f worker | grep "succeeded"

# Ver só erros
docker compose logs -f worker | grep -E "ERROR|CRITICAL|failed"
```

### 5. Verificar instalação

```bash
# Testar conexão com BD
docker compose exec app python scripts/verificar_bd.py

# Verificar health check
curl http://localhost/health

# Ver logs da aplicação
docker compose logs -f app
```

---

## 💻 Uso

### Instalação Local (Desenvolvimento)

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
export DB_HOST=localhost
export DB_USER=appuser
export DB_PASSWORD=sua-senha
# ... outras variáveis

# Rodar aplicação
python app/app.py
```

### Docker (Produção)

```bash
# Iniciar tudo
docker compose up -d --build

# Parar tudo
docker compose down

# Remover volumes antigos (⚠️ isso apaga dados!)
# 1. Parar containers e remover volumes
x# 2. Remover volume persistente manualmente (pode precisar de sudo no Ubuntu)
sudo rm -rf /var/lib/mysql-vendas/*
# 3. Recriar permissões corretas (usuário mysql = UID 999)
    sudo chown -R 999:999 /var/lib/mysql-vendas
# 4. Subir containers com BD limpo
docker compose up -d

# Acessar Mysql com Dbeaver
# Aba main da conexão
Connection name: Vendas Web (SSH)
Host: localhost
Port: 3306
Database: vendasdb
Username: appuser
Password: [valor de MYSQL_PASSWORD do .env]

#aba ssh
Use SSH Tunnel
Host/IP: [IP_DO_SEU_SERVIDOR]
Port: 22
Username: root (ou seu usuário SSH)
Authentication Method: Public Key ou Password
Private Key: [caminho para ~/.ssh/id_rsa]

# Reiniciar apenas app
docker compose restart app

# Ver logs em tempo real
docker compose logs -f app
docker compose logs -f db
docker compose logs -f nginx
```

---

## 📁 Estrutura do Projeto

```
vendas-web/
├── app/                          # Código da aplicação
│   ├── app.py                    # Entry point Flask
│   ├── config.py                 # Configurações
│   ├── database.py               # Conexão com MySQL ✨
│   ├── seguranca.py              # Validação WhatsApp
│   ├── webhook_whatsApp.py       # Handler de webhooks
│   ├── enviar_mensagem_whatsApp.py  # Envio de mensagens
│   ├── agente_vendas.py          # Agente IA (em desenvolvimento)
│   └── templates/                # Templates HTML
│
├── static/                       # Arquivos estáticos
│   └── images/
│
├── migrations/                   # Scripts SQL ✨
│   └── 001_script.sql
│
├── scripts/                      # Scripts utilitários
│   ├── gerar_token.py
│   └── verificar_bd.py           # Teste de BD ✨
│
├── docs/                         # Documentação
│   ├── DATABASE_SETUP.md         # Setup do MySQL ✨
│   ├── SEGURANCA.md
│   └── WEBHOOK_WHATSAPP.md
│
├── infra/                        # Infraestrutura
│   └── nginx/
│       ├── default.conf
│       └── certs/
│
├── docker-compose.yml            # Orquestração
├── Dockerfile                    # Build da aplicação
├── requirements.txt              # Dependências Python
├── .env.example                  # Template de variáveis ✨
├── .gitignore
├── CODE_REVIEW.md                # Review original
├── CODE_REVIEW_ATUALIZADO.md     # Review atualizado ✨
└── README.md
```

---

## 📚 Documentação

- **[DATABASE_SETUP.md](docs/DATABASE_SETUP.md)** - Guia completo de setup do MySQL
- **[CODE_REVIEW_ATUALIZADO.md](CODE_REVIEW_ATUALIZADO.md)** - Code review e melhorias
- **[WEBHOOK_WHATSAPP.md](docs/WEBHOOK_WHATSAPP.md)** - Configuração do webhook
- **[SEGURANCA.md](docs/SEGURANCA.md)** - Práticas de segurança

---

## 🔧 Comandos Úteis

### Docker

```bash
# Ver todos os containers
docker compose ps

# Logs em tempo real
docker compose logs -f

# Logs de um container específico
docker compose logs -f app
docker compose logs -f db
docker compose logs -f nginx

# Entrar em um container
docker compose exec app bash
docker compose exec db bash

# Rebuild de um serviço específico
docker compose up -d --build app
```

### Banco de Dados

```bash
# Conectar ao MySQL
docker compose exec db mysql -uappuser -p vendasdb

# Ver tabelas
docker compose exec db mysql -uappuser -p -e "USE vendasdb; SHOW TABLES;"

# Backup do banco
docker compose exec db mysqldump -uroot -p vendasdb > backup_$(date +%Y%m%d).sql

# Restore de backup
docker compose exec -T db mysql -uroot -p vendasdb < backup_20260215.sql

# Verificar saúde do BD
docker compose exec app python scripts/verificar_bd.py
```

### SSL/TLS

```bash
# Verificar certificado
openssl x509 -in infra/nginx/certs/cert.crt -text -noout

# Verificar MD5 (certificado e chave devem ser iguais)
openssl x509 -noout -modulus -in infra/nginx/certs/cert.crt | openssl md5
openssl rsa -noout -modulus -in infra/nginx/certs/server.key | openssl md5
```

### Git

```bash
# Configurar SSH
ssh-keygen -t ed25519 -C "seu-email@exemplo.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Ver chave pública (adicionar no GitHub)
cat ~/.ssh/id_ed25519.pub

# Clonar com SSH
git clone git@github.com:leosn1006/vendas-web.git
```

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

**Última Atualização:** 19/02/2026
