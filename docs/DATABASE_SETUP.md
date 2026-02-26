# 🚀 Setup do Banco de Dados MySQL - Guia Completo

## 📋 Pré-requisitos

- Docker e Docker Compose instalados
- Ubuntu (para persistência de dados)
- Permissões sudo

---

## 🗄️ Estrutura do Banco de Dados

O projeto usa MySQL 8.4 com as seguintes tabelas:

### Tabelas
- **produtos**: Catálogo de produtos (e-books, etc.)
- **estado_pedidos**: Estados do fluxo de vendas
- **pedidos**: Pedidos dos clientes
- **mensagens_pedidos**: Histórico de mensagens WhatsApp

---

## ⚙️ Configuração Passo a Passo

### 1. Criar o volume persistente no Ubuntu

```bash
# Criar diretório para dados do MySQL
sudo mkdir -p /var/lib/mysql-vendas

# Configurar permissões (UID 999 = usuário mysql no container)
sudo chown -R 999:999 /var/lib/mysql-vendas

# Verificar permissões
ls -la /var/lib/mysql-vendas
```

### 2. Configurar variáveis de ambiente

```bash
# Copiar template
cp .env.example .env

# Editar com suas credenciais
nano .env
```

**Configurações mínimas necessárias:**
```bash
# Senhas do MySQL (use senhas fortes!)
MYSQL_ROOT_PASSWORD=sua-senha-root-super-segura
MYSQL_PASSWORD=sua-senha-app-segura

# Log do Gunicorn (debug, info, warning, error, critical)
LOG_LEVEL=info

# WhatsApp (obtenha em developers.facebook.com)
WHATSAPP_VERIFY_TOKEN=seu-token-verificacao
WHATSAPP_APP_SECRET=seu-app-secret
WHATSAPP_ACCESS_TOKEN=seu-access-token
WHATSAPP_PHONE_NUMBER_ID=seu-phone-number-id
```

### Configuração de produtos por fluxo

A tabela `produtos` agora suporta campos de personalização por produto:

- `prompt_vendas`
- `prompt_followup`
- `url_audio_introducao`
- `url_audio_explicativo`
- `url_imagem_complementar`
- `url_arquivo_produto`
- `mensagem_introducao`

Esses campos permitem deixar os fluxos responsivos para diferentes produtos sem hardcode no Python.

### 3. Iniciar os containers

```bash
# Build e start em background
docker compose up -d --build

# Verificar se está rodando
docker compose ps

# Ver logs
docker compose logs -f db
```

**Saída esperada:**
```
vendas-mysql     | [Server] X Plugin ready for connections.
vendas-web-app   | [INFO] Listening at: http://0.0.0.0:8000
vendas-web-nginx | nginx: [notice] start worker processes
```

### 4. Verificar inicialização do banco

```bash
# Aguardar o health check
docker compose ps

# Verificar execução das migrations
docker compose logs db | grep "docker-entrypoint-initdb.d"

# Conectar ao MySQL
docker compose exec db mysql -uappuser -p vendasdb
```

**Dentro do MySQL:**
```sql
-- Ver tabelas criadas
SHOW TABLES;

-- Ver produtos
SELECT * FROM produtos;

-- Ver estados de pedidos
SELECT * FROM estado_pedidos;

-- Sair
EXIT;
```

### 5. Testar a aplicação

```bash
# Verificar health check
curl http://localhost/health

# Ver logs da aplicação
docker compose logs -f app
```

---

## 🔧 Comandos Úteis

### Gerenciamento de Containers

```bash
# Parar tudo
docker compose down

# Reiniciar apenas o app (sem perder dados do BD)
docker compose restart app

# Ver logs em tempo real
docker compose logs -f

# Ver apenas logs do MySQL
docker compose logs -f db

# Entrar no container da aplicação
docker compose exec app bash

# Entrar no container do MySQL
docker compose exec db bash
```

### Operações no Banco de Dados

```bash
# Backup do banco
docker compose exec db mysqldump -uroot -p vendasdb > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup com compressão
docker compose exec db mysqldump -uroot -p vendasdb | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Restore de backup
docker compose exec -T db mysql -uroot -p vendasdb < backup_20260215_120000.sql

# Restore de backup comprimido
gunzip < backup_20260215_120000.sql.gz | docker compose exec -T db mysql -uroot -p vendasdb
```

### Queries Úteis

```bash
# Ver todos os pedidos
docker compose exec db mysql -uappuser -p -e "
USE vendasdb;
SELECT p.id, p.contact_name, p.contact_phone, ep.descricao as estado, p.data_pedido
FROM pedidos p
JOIN estado_pedidos ep ON p.estado_pedido_id = ep.id
ORDER BY p.data_pedido DESC;
"

# Contar pedidos por estado
docker compose exec db mysql -uappuser -p -e "
USE vendasdb;
SELECT ep.descricao, COUNT(*) as total
FROM pedidos p
JOIN estado_pedidos ep ON p.estado_pedido_id = ep.id
GROUP BY ep.descricao;
"

# Ver últimas mensagens
docker compose exec db mysql -uappuser -p -e "
USE vendasdb;
SELECT * FROM mensagens_pedidos ORDER BY data_mensagem DESC LIMIT 10;
"
```

---

## 🐞 Troubleshooting

### Problema: Container do MySQL não inicia

**Verificar logs:**
```bash
docker compose logs db
```

**Causas comuns:**
1. **Permissões incorretas do volume**
   ```bash
   sudo chown -R 999:999 /var/lib/mysql-vendas
   ```

2. **Porta 3306 já em uso**
   ```bash
   # Ver o que está usando a porta
   sudo lsof -i :3306

   # Parar MySQL local se houver
   sudo systemctl stop mysql
   ```

3. **Variáveis de ambiente não configuradas**
   ```bash
   # Verificar .env
   cat .env | grep MYSQL
   ```

### Problema: Migrations não executadas

**Verificar:**
```bash
# Ver se o script existe
ls -la migrations/

# Ver logs de inicialização
docker compose logs db | grep "init"

# Executar manualmente
docker compose exec db mysql -uroot -p vendasdb < migrations/001_script.sql
```

### Problema: Aplicação não conecta ao BD

**Verificar:**
```bash
# Testar conexão do container app
docker compose exec app python -c "from app.database import db; print(db.test_connection())"

# Ver variáveis de ambiente no container
docker compose exec app env | grep DB_

# Ver se o DB está no health check OK
docker compose ps
```

### Problema: "Lost connection to MySQL server"

**Causas:**
- MySQL reiniciando
- Timeout de conexão
- Pool de conexões esgotado

**Solução:**
```bash
# Verificar status do MySQL
docker compose exec db mysqladmin -uroot -p ping

# Ver processos no MySQL
docker compose exec db mysql -uroot -p -e "SHOW PROCESSLIST;"

# Reiniciar aplicação
docker compose restart app
```

---

## 🔒 Segurança em Produção

### Checklist de Segurança

- [ ] **Senhas fortes** no `.env` (mínimo 16 caracteres)
- [ ] **Backup automático** configurado (cron job)
- [ ] **Firewall** permitindo apenas portas 80/443
- [ ] **Volume criptografado** (opcional, mas recomendado)
- [ ] **Logs rotation** configurado
- [ ] **Monitoramento** de espaço em disco

### Exemplo de Backup Automático (cron)

```bash
# Editar crontab
crontab -e

# Adicionar linha (backup diário às 3h da manhã)
0 3 * * * cd /caminho/do/projeto && docker compose exec -T db mysqldump -uroot -p${MYSQL_ROOT_PASSWORD} vendasdb | gzip > /backups/mysql/vendas_$(date +\%Y\%m\%d).sql.gz

# Manter apenas últimos 7 dias
0 4 * * * find /backups/mysql/ -name "vendas_*.sql.gz" -mtime +7 -delete
```

### Configurar SSL interno (MySQL)

Para conexões MySQL ainda mais seguras (opcional):
```yaml
# docker-compose.yml
services:
  db:
    command: >
      --ssl-ca=/etc/mysql/certs/ca.pem
      --ssl-cert=/etc/mysql/certs/server-cert.pem
      --ssl-key=/etc/mysql/certs/server-key.pem
```

---

## 📊 Monitoramento

### Ver Status do Sistema

```bash
# Uso de disco do volume MySQL
df -h /var/lib/mysql-vendas

# Tamanho do banco de dados
docker compose exec db mysql -uroot -p -e "
SELECT
    table_schema AS 'Database',
    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)'
FROM information_schema.tables
WHERE table_schema = 'vendasdb'
GROUP BY table_schema;
"

# Ver tamanho de cada tabela
docker compose exec db mysql -uroot -p -e "
SELECT
    table_name AS 'Table',
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'Size (MB)'
FROM information_schema.tables
WHERE table_schema = 'vendasdb'
ORDER BY (data_length + index_length) DESC;
"
```

### Métricas de Performance

```bash
# Ver conexões ativas
docker compose exec db mysql -uroot -p -e "SHOW STATUS LIKE 'Threads_connected';"

# Ver queries lentas
docker compose exec db mysql -uroot -p -e "SHOW VARIABLES LIKE 'slow_query_log';"

# Status geral
docker compose exec db mysql -uroot -p -e "SHOW STATUS;"
```

---

## 🎓 Próximos Passos

Após configurar o banco de dados:

1. **Testar integração**: Enviar mensagens de teste via WhatsApp
2. **Monitorar logs**: Verificar se está salvando no BD
3. **Implementar lógica de negócio**: Ver [CODE_REVIEW_ATUALIZADO.md](CODE_REVIEW_ATUALIZADO.md)
4. **Adicionar testes**: Criar testes unitários
5. **Configurar backup**: Schedule automático

---

## 📚 Referências

- [MySQL Docker Hub](https://hub.docker.com/_/mysql)
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [MySQL 8.4 Reference](https://dev.mysql.com/doc/refman/8.4/en/)
- [Flask-MySQL Integration](https://flask.palletsprojects.com/en/3.0.x/)

---

## ❓ Precisa de Ajuda?

Se encontrar problemas:

1. Verificar logs: `docker compose logs -f`
2. Consultar [CODE_REVIEW_ATUALIZADO.md](CODE_REVIEW_ATUALIZADO.md)
3. Ver seção de Troubleshooting deste guia
4. Verificar permissões do volume

**Última Atualização:** 15/02/2026
