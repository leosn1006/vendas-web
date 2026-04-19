# Checklist de Retomada — Rate Limit WhatsApp (19/04/2026)

## Estado atual do sistema

| Serviço | Status |
|---|---|
| vendas-web-app + nginx | ✅ Rodando (recebe webhooks, retorna 200 para Meta) |
| vendas-mysql / redis / flower | ✅ Rodando |
| vendas-worker | ⏸ Parado (`docker compose stop worker`) |
| vendas-beat | ⏸ Parado (`docker compose stop beat`) |

## Código desabilitado temporariamente (3 `return`)

| Arquivo | Função | O que faz |
|---|---|---|
| `app/whatsapp_orquestrador.py` | `recebe_webhook` | Não enfileira nenhuma task |
| `app/whatsapp.py` | `notificar_admin_via_template` | Notificação ao admin desabilitada |
| `app/whatsapp.py` | `notificar_admin_erro_sistema` | Notificação de erro ao admin desabilitada |

---

## Checklist para retomar (quando quality rating voltar ao verde)

### 1. Verificar quality rating
- Painel Meta Business → WhatsApp → Números de telefone
- Todos devem estar **verdes** antes de prosseguir

### 2. Remover os 3 `return` temporários

**`app/whatsapp_orquestrador.py`** (~linha 47):
```python
# REMOVER esta linha:
return "modo de manutenção — processamento suspenso"
```

**`app/whatsapp.py`** — `notificar_admin_via_template` (~linha 379):
```python
# REMOVER esta linha:
return  # temporariamente desabilitado — rate limit
```

**`app/whatsapp.py`** — `notificar_admin_erro_sistema` (~linha 424):
```python
# REMOVER esta linha:
return  # temporariamente desabilitado — rate limit
```

### 3. Implementar `WhatsAppRateLimitError` (previne recorrência)

Ver implementação detalhada no plano de sessão Claude. Resumo:
- Detectar código 131056 em `enviar_mensagem` → lançar `WhatsAppRateLimitError`
- Absorver como `WARNING` em `_executor_acao.py` (não falha o fluxo)
- Não notificar admin nem fazer retry em `tasks.py`

### 4. Fazer deploy e reiniciar worker e beat
```bash
docker compose up -d --build app
docker compose start worker beat
```

### 5. Testar
1. Enviar mensagem de teste com número **diferente do admin**
2. Confirmar que a resposta chega normalmente
3. Confirmar que erros de rate limit aparecem como `[WARNING]`, não `[ERROR]`

---

## Causa raiz

Loop de notificações admin → muitas mensagens para o mesmo número em pouco tempo
→ rate limit do par (business → admin) → erros 131056 em cascata
→ quality rating de um número ficou amarelo

**Solução permanente:** `WhatsAppRateLimitError` trata o erro 131056 como throttling
esperado (warning), sem notificar admin nem retentar, quebrando o loop.
