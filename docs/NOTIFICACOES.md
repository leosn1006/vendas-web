# Sistema de Notificações de Erro via WhatsApp

Este documento explica como usar o sistema de notificações de erro implementado no projeto.

## 📋 Visão Geral

O sistema permite que você receba notificações de erros diretamente no seu WhatsApp pessoal, facilitando o monitoramento da aplicação em produção.

### Características:

- ✅ **Exceções customizadas** com formatação rica
- ✅ **Rate limiting** automático (máx. 10 notificações/hora)
- ✅ **Deduplicação** de erros repetidos (cache de 5 minutos)
- ✅ **Níveis de severidade** (CRÍTICO, ALTO, MÉDIO, BAIXO)
- ✅ **Contexto rico** com traceback e informações adicionais
- ✅ **Decorator** para facilitar uso em rotas
- ✅ **Handler global** para capturar erros não tratados

---

## ⚙️ Configuração

### 1. Adicionar variável de ambiente

No arquivo `.env`, adicione seu número de WhatsApp:

```bash
# Número do admin para receber notificações
ADMIN_WHATSAPP_NUMBER=5511999999999
```

**Formato:** Código do país + DDD + número (sem espaços ou caracteres especiais)

### 2. Verificar outras variáveis (já existentes)

```bash
WHATSAPP_TOKEN=seu_token
PHONE_NUMBER_ID=974838442380155
```

---

## 🚀 Como Usar

### 1. Decorator em Rotas (Recomendado)

Use o decorator `@notificar_erro()` nas rotas críticas:

```python
from notificacoes import notificar_erro

@app.post("/api/v1/webhook-whatsapp")
@notificar_erro()  # Qualquer erro será notificado
def webhook_receive():
    # Seu código aqui
    pass
```

### 2. Exceções Customizadas

Levante exceções específicas com contexto rico:

```python
from excecoes import ErroBancoDados, ErroWhatsApp, ErroOpenAI

# Erro de banco de dados
raise ErroBancoDados(
    mensagem="Falha ao salvar pedido",
    query="INSERT INTO pedidos...",
    contexto={
        'Cliente': 'João Silva',
        'Valor': 'R$ 150,00'
    },
    severidade='CRÍTICO'
)

# Erro do WhatsApp
raise ErroWhatsApp(
    mensagem="Não foi possível enviar mensagem",
    numero_destino="5511999999999",
    severidade='ALTO'
)

# Erro da OpenAI
raise ErroOpenAI(
    mensagem="API da OpenAI retornou erro 429",
    modelo="gpt-4o-mini",
    severidade='MÉDIO'
)
```

### 3. Notificação Manual (sem exceção)

Envie notificações sem interromper o fluxo:

```python
from notificacoes import notificador
from excecoes import ErroNotificavel

def funcao_com_fallback():
    try:
        # Tenta operação principal
        api_externa.enviar()
    except Exception as e:
        # Notifica mas continua com fallback
        erro = ErroNotificavel(
            mensagem="API externa falhou, usando cache",
            severidade='MÉDIO',
            contexto={'Cache': 'redis'}
        )
        notificador.notificar_erro(erro)

        # Usa fallback
        return usar_cache()
```

### 4. Handler Global (Recomendado)

Adicione no `app.py` para capturar TODOS os erros:

```python
from notificacoes import notificador
from excecoes import ErroNotificavel

@app.errorhandler(Exception)
def handle_exception(e):
    """Captura todos os erros não tratados."""
    if isinstance(e, ErroNotificavel):
        notificador.notificar_erro(e)
    else:
        contexto = {
            'Aplicação': 'vendas-web',
            'Ambiente': 'produção'
        }
        notificador.notificar_erro(e, contexto_adicional=contexto)

    return {'error': 'Erro interno'}, 500
```

---

## 📊 Níveis de Severidade

| Nível | Emoji | Quando Usar |
|-------|-------|-------------|
| **CRÍTICO** | 🚨 | Sistema não consegue funcionar (BD inacessível, config faltando) |
| **ALTO** | ⚠️ | Funcionalidade importante falhou (pagamento, envio de mensagem) |
| **MÉDIO** | ⚡ | Problema com fallback disponível (API lenta, cache usado) |
| **BAIXO** | ℹ️ | Informativo (limites próximos, avisos) |

---

## 🛡️ Rate Limiting

O sistema possui proteções automáticas:

- **Máximo:** 10 notificações por hora
- **Deduplicação:** Erros idênticos em 5 minutos = 1 notificação
- **Forçar envio:** Use `forcar=True` para ignorar limites

```python
# Ignorar rate limiting (usar com cuidado!)
notificador.enviar_notificacao(mensagem, forcar=True)
```

---

## 🧪 Testar o Sistema

Execute o script de teste:

```bash
cd ~/vendas-web
docker compose exec app python scripts/exemplo_notificacoes.py
```

Você deve receber uma mensagem de teste no WhatsApp.

---

## 📱 Exemplo de Mensagem Recebida

```
🚨 ERRO NO SISTEMA

Severidade: CRÍTICO
Horário: 16/02/2026 14:32:18

Erro: Falha ao conectar com banco de dados

Contexto:
• Host: db
• Porta: 3306
• Tentativas: 3

Traceback:
`File "database.py", line 45, in get_connection`
`mysql.connector.errors.OperationalError: Can't connect to MySQL server`
```

---

## 📝 Exemplos Práticos

### Webhook do WhatsApp

```python
@app.post("/api/v1/webhook-whatsapp")
@notificar_erro()
def webhook_receive():
    # Qualquer erro aqui será notificado automaticamente
    body = request.get_json()
    return recebe_webhook(body), 200
```

### Função com tratamento específico

```python
from excecoes import ErroBancoDados

def criar_pedido(dados):
    try:
        cursor.execute(query, dados)
        db.commit()
    except Exception as e:
        raise ErroBancoDados(
            mensagem="Falha ao criar pedido",
            query=query,
            contexto={
                'Cliente': dados['telefone'],
                'Valor': dados['total']
            },
            severidade='CRÍTICO'
        )
```

---

## 🔐 Segurança

- ❌ **NUNCA** faça commit do `.env` com seu número pessoal
- ✅ Use `.env.example` como template
- ✅ Configure `ADMIN_WHATSAPP_NUMBER` apenas em produção
- ✅ O sistema respeita rate limiting para evitar spam

---

## 🐛 Troubleshooting

### Não estou recebendo notificações

1. **Verifique as variáveis de ambiente:**
   ```bash
   docker compose exec app python -c "import os; print(os.getenv('ADMIN_WHATSAPP_NUMBER'))"
   ```

2. **Teste manualmente:**
   ```bash
   docker compose exec app python scripts/exemplo_notificacoes.py
   ```

3. **Verifique os logs:**
   ```bash
   docker compose logs app | grep NOTIFICAÇÃO
   ```

### Rate limit atingido

Aguarde 1 hora ou use `forcar=True` apenas para testes:

```python
notificador.enviar_notificacao(mensagem, forcar=True)
```

---

## 📚 Arquivos do Sistema

```
app/
├── excecoes.py          # Exceções customizadas
├── notificacoes.py      # Gerenciador de notificações
└── app.py               # Handler global (adicionar)

scripts/
└── exemplo_notificacoes.py  # Exemplos de uso e teste

.env
└── ADMIN_WHATSAPP_NUMBER    # Seu número (adicionar)
```

---

## ✨ Dicas

1. **Cole o decorator** nas rotas mais críticas primeiro
2. **Use exceções customizadas** para ter mensagens mais ricas
3. **Monitore o rate limiting** - ajuste se necessário
4. **Teste antes de deploy** com `exemplo_notificacoes.py`
5. **Use severidade apropriada** para facilitar triagem

---

**Pronto!** Agora você tem um sistema profissional de monitoramento 24/7 no seu bolso! 🎉
