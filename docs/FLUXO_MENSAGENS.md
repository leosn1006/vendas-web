# Fluxo de Mensagens WhatsApp

Descreve como uma mensagem percorre o sistema, desde o webhook até a resposta ao cliente.

---

## 1. Webhook — porta de entrada (`whatsapp_orquestrador.py`)

```
WhatsApp envia mensagem
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  Número está em _NUMEROS_BLOQUEADOS?                │  hardcoded — autoresponders conhecidos
│  SIM → descarta sem salvar nada                     │
└────────────────────────┬────────────────────────────┘
                         │ NÃO
                         ▼
                  Extrai dados + busca/cria pedido
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  pedido.bloqueado = 1?                              │  bloqueado manualmente pelo admin
│  SIM → descarta sem salvar nada                     │
└────────────────────────┬────────────────────────────┘
                         │ NÃO
                         ▼
┌─────────────────────────────────────────────────────┐
│  Imagem/doc com 3+ envios nos últimos 5min?         │  loop de comprovante
│  SIM → notifica admin (loop_autoresponder)          │
│        descarta sem salvar                          │
└────────────────────────┬────────────────────────────┘
                         │ NÃO
                         ▼
              Roteia para o fluxo correto:

              estado 1    → enviar_introducao_dinamico
              estado 2    → enviar_pedido_dinamico
              estado 1000 → responder_mensagem
              demais      → responder_mensagem    (texto)
                          → conferir_comprovante  (imagem/doc)
```

---

## 2. fluxo_responder — agente de IA (`fluxos/fluxo_responder.py`)

Só chega aqui após o roteamento do webhook.

```
Mensagem chega via Celery
        │
        ▼
   Marca como lida no WhatsApp (best-effort, não bloqueia)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  Pedido tem notificação em_analise?                 │  admin está atendendo manualmente
│  SIM → SALVA mensagem + silencia IA (sem OpenAI)   │
└────────────────────────┬────────────────────────────┘
                         │ NÃO
                         ▼
┌─────────────────────────────────────────────────────┐
│  Total de mensagens do pedido >= 40?                │  "namorando o agente"
│  SIM → SALVA + notifica admin (loop_excesso_msg)   │
│        + silencia IA                               │
└────────────────────────┬────────────────────────────┘
                         │ NÃO
                         ▼
┌─────────────────────────────────────────────────────┐
│  Texto > 10 chars E igual ao último texto (10min)?  │  autoresponder empresarial
│  SIM → SALVA + notifica admin (loop_repetidas_msg) │
│        + silencia IA                               │
└────────────────────────┬────────────────────────────┘
                         │ NÃO
                         ▼
              Carrega produto + histórico (últimas 10 msgs)
                         │
                         ▼
                  Chama OpenAI → gera resposta
                         │
                         ▼
              Agenda envio com delay humanizado (5–8s)
```

---

## 3. Tipos de bloqueio — comparativo

| | `_NUMEROS_BLOQUEADOS` | `pedido.bloqueado` | Notificação `em_analise` |
|---|---|---|---|
| Configurado em | código (hardcoded) | banco (admin) | banco (automático) |
| Escopo | telefone | pedido específico | pedido específico |
| Salva mensagem? | não | não | sim |
| Gasta token OpenAI? | não | não | não |
| Admin é notificado? | não | não | já estava |
| Quem aciona | dev | admin (tela de conversa ou notificações) | sistema |
| Caso de uso | número com autoresponder comprovado | excesso de mensagens, "namorador" | escalação, erro do agente |

---

## 4. Tipos de notificação admin

| Motivo | Gerado em | Significado |
|---|---|---|
| `loop_autoresponder` | webhook | 3+ comprovantes em 5 min |
| `loop_excesso_msg` | fluxo_responder | pedido atingiu 40 mensagens |
| `loop_repetidas_msg` | fluxo_responder | texto idêntico repetido em 10 min (> 10 chars) |
| `escalonamento` | agente OpenAI | cliente pediu estorno, insatisfação etc. |
