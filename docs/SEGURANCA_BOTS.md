# Melhorias de Segurança - Proteção contra Scans e Bots

## 📋 O que foi implementado:

### 1. **Nginx com Rate Limiting** ([infra/nginx/default_seguro.conf](infra/nginx/default_seguro.conf))

#### Rate Limiting:
- **Geral:** 10 requisições/segundo por IP
- **API WhatsApp:** 5 requisições/segundo por IP
- **Burst:** Buffer para picos legítimos

#### Bloqueios Automáticos:
```nginx
# Retorna 444 (conexão fechada) para paths suspeitos
jasperserver, helpdesk, aspera, cf_scripts, WebObjects,
phpmyadmin, wp-admin, admin.php, etc.
```

#### User-Agents Bloqueados:
```nginx
nikto, sqlmap, nmap, masscan, acunetix, nessus
```

#### Headers de Segurança:
- `X-Frame-Options` → Previne clickjacking
- `X-Content-Type-Options` → Previne MIME sniffing
- `X-XSS-Protection` → Proteção contra XSS
- `Referrer-Policy` → Controla referrer

### 2. **Flask com Handler 404 Inteligente** ([app/app.py](app/app.py))

#### Não Notifica WhatsApp para:
- Paths suspeitos de scanners (jasperserver, helpdesk, etc)
- 404s causados por bots
- Requisições automatizadas

#### Notifica WhatsApp para:
- Erros 500 (exceções não tratadas)
- Erros na rota do webhook
- Erros de lógica de negócio

---

## 🚀 Como Aplicar:

### Opção 1: Substituir configuração atual (recomendado)
```bash
cd ~/vendas-web
mv infra/nginx/default.conf infra/nginx/default_backup.conf
mv infra/nginx/default_seguro.conf infra/nginx/default.conf
docker compose restart nginx
```

### Opção 2: Mesclar manualmente
Copie as seções de rate limiting e bloqueios do `default_seguro.conf` para seu `default.conf` atual.

---

## 📊 Monitoramento:

### Ver logs filtrados (sem scans de bots):
```bash
docker compose logs nginx | grep -v "444\|jasperserver\|helpdesk\|aspera"
```

### Ver apenas erros reais:
```bash
docker compose logs nginx | grep "500\|502\|503"
```

### Contar tentativas de scan bloqueadas:
```bash
docker compose logs nginx | grep -c "444"
```

---

## 🔐 Proteções Adicionais (Opcional):

### Fail2Ban (bloqueia IPs após tentativas repetidas)
```bash
sudo apt install fail2ban
```

Criar `/etc/fail2ban/jail.local`:
```ini
[nginx-scan]
enabled = true
port = http,https
filter = nginx-scan
logpath = /var/log/nginx/access.log
maxretry = 5
bantime = 3600
findtime = 300
```

### Firewall UFW (recomendado)
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### Cloudflare (proteção DDoS gratuita)
Configure seu DNS para apontar para Cloudflare:
- ✅ DDoS protection
- ✅ Web Application Firewall (WAF)
- ✅ Bot detection
- ✅ CDN gratuito

---

## 💡 Entendendo os Códigos HTTP:

| Código | Significado | O que o Nginx faz |
|--------|-------------|-------------------|
| **301** | Redirect permanente | HTTP → HTTPS (normal) |
| **404** | Não encontrado | Rota não existe (normal para scans) |
| **444** | Conexão fechada | Nginx bloqueia e nem processa (economiza recursos) |
| **429** | Too Many Requests | Rate limit atingido (proteção funcionando) |
| **500** | Erro interno | Problema real no servidor (NOTIFICA WhatsApp) |

---

## ✅ Resultados Esperados:

### Antes:
```
45.156.129.163 - GET /jasperserver/login.html - 404
45.156.129.162 - GET /helpdesk/WebObjects/ - 404
45.156.129.161 - GET /login.html - 404
→ Logs poluídos, recursos desperdiçados
```

### Depois:
```
45.156.129.163 - GET /jasperserver/login.html - 444 (BLOQUEADO)
45.156.129.162 - GET /helpdesk/WebObjects/ - 444 (BLOQUEADO)
45.156.129.161 - GET /login.html - 444 (BLOQUEADO)
→ IP bloqueado após 5 tentativas em 5 minutos
→ Logs limpos, WhatsApp só para erros reais
```

---

## 🎯 Resumo:

### ✅ O Sistema ESTÁ Seguro
- ❌ Nenhuma vulnerabilidade explorada (404 = não existe)
- ✅ Bots apenas fazem scan, mas não conseguem nada

### ⚠️ Melhorias Implementadas
- ✅ Rate limiting (previne DDoS)
- ✅ Bloqueio de paths suspeitos (economiza recursos)
- ✅ Handler 404 inteligente (não polui WhatsApp)
- ✅ Headers de segurança (proteção extra)

### 📱 Notificações WhatsApp Agora Mais Inteligentes
- ✅ Notifica: Erros 500, problemas no webhook, exceções de código
- ❌ NÃO notifica: Scans de bots, 404s de paths inexistentes

---

**Recomendação Final:** Aplique a nova configuração do Nginx e monitore os logs por 24h para confirmar que os scans estão sendo bloqueados eficientemente! 🚀
