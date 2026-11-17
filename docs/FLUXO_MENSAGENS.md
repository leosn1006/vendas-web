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
   NÃO marca como lida nem mostra "digitando" (de propósito, migration 103):
   se a IA escala (estorno) e ninguém respondeu, tique azul parecia descaso
        │
        ▼
   Relê o pedido no banco (a task traz a foto do webhook: 13 e não pago
   enquanto o comprovante é processado)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  Estado 13 (comprovante em análise)?                │  texto que chegou junto com a imagem
│  SIM → reagenda em 20 s (até 5 vezes) e sai        │
└────────────────────────┬────────────────────────────┘
                         │ NÃO (ou passou do limite)
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
┌─────────────────────────────────────────────────────┐
│  Mensagem não pede resposta? (_mensagem_sem_resposta)│  emoji, ok, obrigada, amém,
│  SIM → SALVA + silencia (sem OpenAI, sem WhatsApp)  │  saudação sozinha NÃO; "segue o
└────────────────────────┬────────────────────────────┘  comprovante"/"já paguei" só se pago
                         │ NÃO
                         ▼
              Carrega produto + histórico (últimas 10 msgs,
              linhas técnicas traduzidas para "(Registro: ...)")
                         │
                         ▼
     Chama OpenAI (prompt + FAQ + PDF + regras + SITUAÇÃO DO PEDIDO)
                         │
     ┌──────────────┬────┴─────────┬───────────────────┬──────────────────────┐
     ▼              ▼              ▼                   ▼                      ▼
  responder    nao_responder   notificar_admin    risco_vida         registrar_pagamento_informado
  agenda envio  só salva       escala, sem        escala E envia     task confirmar_pagamento_informado
  (5–8 s)                      resposta           mensagem do CVV    em 30 s: relê, trava 3/4 → 13 e roda
                                                  (188)              o fluxo do comprovante sem arquivo
```

Regras de pagamento (nov/2026): a IA **nunca pede comprovante** nem nome do pagador/valor/horário (o bloco de
regras vem depois do FAQ e prevalece sobre ele). Pedido pago: comentário sobre o pagamento, valor ou chave Pix →
`nao_responder`. Pedido do WhatsApp aguardando pagamento (3/4): "já paguei" vale como comprovante (valor citado ou
preço do produto), com as mesmas ações do fluxo Comprovante (`confirmar_pagamento` em
`fluxo_comprovante_dinamico.py`). A trava é feita só na task, depois de 30 s: se a imagem do comprovante chegar
nesse meio-tempo, ela tem prioridade. Pedidos do site (100x) nunca recebem essa ferramenta.

Risco à vida com pedido já em análise (IA silenciada): a checagem determinística `fala_em_risco_a_vida` envia o
CVV mesmo assim.

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
| `estorno` / `insatisfacao` / `ajuda_pagamento` / `pergunta_sem_resposta` | agente OpenAI | escalação; a IA não responde |
| `risco_vida` | agente OpenAI | fala em suicídio/se machucar/violência; a IA responde com o CVV (188) e escala |
