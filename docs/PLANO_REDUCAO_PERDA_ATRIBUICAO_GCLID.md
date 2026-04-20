# Plano: Redução de Perda de Atribuição (15-20%) via Melhoria de Vínculo Lead-WhatsApp

**Data:** 20 de abril de 2026
**Status:** Planejado (aguardando aprovação)
**Impacto esperado:** reduzir perda de 15-20% para ~5-10%
**Complexidade:** Baixa a Média
**Risco de implementação:** Baixo (implementável em fases, com fallback ao fluxo atual)

---

## Problema

Hoje, o vínculo entre o lead gerado na landing (com `gclid`) e a primeira mensagem do cliente no WhatsApp depende de **igualdade exata do texto da mensagem**. Isso causa perda de ~15-20% de atribuições porque:

1. Cliente edita a mensagem pré-preenchida
2. Emoji varia entre plataformas/SO
3. Espaços e caracteres mudam
4. Mensagens genéricas causam colisão entre leads
5. Primeira interação é áudio/imagem/documento
6. Janela de 1 hora é curta para alguns casos

**Resultado:** pedido cai no fallback, é criado sem `gclid=None`, nunca entra no upload do Google Ads.

---

## Solução: Três Camadas Complementares

### Camada 1: Lead Token na Mensagem (PRINCIPAL)

**Objetivo:** carregar o identificador técnico do lead na própria mensagem.

**Mecânica:**
- Ao criar o pedido em [app/lead_incluir.py:78](../app/lead_incluir.py#L78), obter o `pedido_id`
- Adicionar `[ref:PEDIDO_ID]` ao final da `mensagem_sugerida` antes de devolver ao frontend
- Exemplo do que chega ao cliente:
  ```
  😊 Olá, tenho interesse nas receitas [ref:4821]
  ```

**Fluxo no webhook:**
1. Ao processar mensagem em [app/whatsapp_orquestrador.py:107](../app/whatsapp_orquestrador.py#L107)
2. **Novo passo 0:** tentar extrair `[ref:NNNN]` da mensagem recebida
3. Se encontrar: vincular direto por `pedido_id`, remover o token do texto para a conversa continuar normal
4. Se não encontrar: continuar com fluxo atual (telefone → normalização → fallback)

**Benefício:** maioria dos clientes não edita mensagem pré-preenchida. Esperado eliminar 60-70% das perdas.

**Arquivos afetados:**
- [app/lead_incluir.py](../app/lead_incluir.py) — linhas 49, 79-84
- [app/whatsapp_orquestrador.py](../app/whatsapp_orquestrador.py) — função `buscar_pedido` linha 107
- [app/database.py](../app/database.py) — nova função `vincular_pedido_por_id`

**Pseudo-código:**
```python
# Em lead_incluir.py, ao retornar a resposta:
pedido_id = criar_pedido(pedido)
resposta = {
    "whatsapp_numero": whatsapp_numero,
    "emojiEscolhido": emoji,
    "mensagemBaseWA": f"{texto} [ref:{pedido_id}]"  # ← adiciona token
}

# Em whatsapp_orquestrador.py, no buscar_pedido:
import re
match = re.search(r'\[ref:(\d+)\]', msg_enviado_cliente)
if match:
    pedido_id = int(match.group(1))
    pedido = get_pedido(pedido_id)
    if pedido and pedido['estado_id'] == 1:
        # vincular o contato ao pedido existente
        msg_limpa = re.sub(r'\[ref:\d+\]', '', msg_enviado_cliente).strip()
        return vincula_pedido_com_contato(pedido_id, ...)
```

**Trade-off:** alguns clientes podem achar `[ref:4821]` estranho. Alternativas:
- `#4821` ou `cod:4821` para algo mais discreto
- Usar quebra de linha: `Mensagem\n#4821`

---

### Camada 2: Normalização de Texto (FALLBACK MELHORADO)

**Objetivo:** quando o token não existir (cliente apagou), melhorar a busca por texto.

**Mecânica:**
- Ao criar o lead, gravar também uma versão normalizada da `mensagem_sugerida`
- Normalização:
  - minúsculas
  - remover emojis
  - remover espaços duplicados
  - normalizar Unicode (NFC)

- Ao buscar no webhook, comparar normalizado com normalizado

**Benefício:** captura a maioria das variações pequenas de edição do cliente sem depender do token.

**Arquivos afetados:**
- [app/lead_incluir.py](../app/lead_incluir.py) — linhas 49-84
- [app/database.py](../app/database.py) — coluna `mensagem_sugerida_normalizada` em pedidos (ou gerar em runtime)
- [app/whatsapp_orquestrador.py](../app/whatsapp_orquestrador.py) — função `buscar_pedido` linha 107

**Pseudo-código:**
```python
# Em lead_incluir.py:
def normalizar_mensagem(msg):
    import unicodedata
    import re
    msg = msg.lower()
    msg = re.sub(r'[^\w\s]', '', msg)  # remove emoji
    msg = ' '.join(msg.split())  # remove espaços duplicados
    msg = unicodedata.normalize('NFC', msg)
    return msg

mensagem_normalizada = normalizar_mensagem(texto)

# Em whatsapp_orquestrador.py:
msg_recebida_norm = normalizar_mensagem(msg_enviado_cliente)
pedido = get_ultimo_pedido_por_mensagem_sugerida_normalizada(msg_recebida_norm)
```

**Implementação:** pode ser feita em Python (sem alterar banco) ou com coluna extra no banco. Python é mais simples, mas banco é mais indexável.

---

### Camada 3: Registro de Mensagens Recebidas (ANALYTICS)

**Objetivo:** construir corpus real de como clientes chegam ao WhatsApp para embasamento de decisões.

**Mecânica:**
- Adicionar coluna `origem` à tabela `mensagens_sugeridas_produto`
  - `origem = 'sugerida'` — mensagens que o sistema gera (estado atual)
  - `origem = 'recebida'` — o que cliente realmente enviou (nova)

- Ao receber primeira mensagem de novo contato (estado 1, webhook), registrar o texto como `origem='recebida'`

**Benefício:**
- Visualizar no admin quais mensagens sugeridas são efetivamente usadas vs editadas
- Identificar mensagens genéricas com alta colisão
- Dados para melhorar o gerador de mensagens

**Arquivos afetados:**
- Migration nova: `024_analytics_mensagens_recebidas.sql`
- [app/database.py](../app/database.py) — nova função `registrar_mensagem_recebida`
- [app/whatsapp_orquestrador.py](../app/whatsapp_orquestrador.py) — chamar ao criar pedido no fallback

**SQL:**
```sql
ALTER TABLE mensagens_sugeridas_produto
ADD COLUMN origem ENUM('sugerida', 'recebida') DEFAULT 'sugerida';

ALTER TABLE mensagens_sugeridas_produto
ADD COLUMN data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

---

## Fluxo Proposto Completo

```
┌─ Cliente clica na landing
│
├─ Backend cria pedido com gclid
│  └─ mensagem_sugerida = "😊 Olá, tenho interesse [ref:4821]"
│
├─ Frontend abre WhatsApp com texto pré-preenchido
│
├─ Cliente envia (com ou sem edição)
│
└─ Webhook chega

   ┌─ Extrai [ref:NNNN]?
   │  ├─ SIM → Vincula por pedido_id → salva gclid ✅
   │  └─ NÃO → continua
   │
   ├─ Busca por telefone?
   │  ├─ SIM → Vincula → salva gclid ✅
   │  └─ NÃO → continua
   │
   ├─ Busca por mensagem normalizada?
   │  ├─ SIM → Vincula → salva gclid ✅
   │  └─ NÃO → continua
   │
   └─ Fallback: cria novo pedido sem gclid
      └─ Registra mensagem recebida para analytics
```

---

## Implementação: Fases Sugeridas

### Fase 1: Token (Semana 1)
- Modificar [app/lead_incluir.py](../app/lead_incluir.py)
- Modificar [app/whatsapp_orquestrador.py](../app/whatsapp_orquestrador.py)
- Adicionar função em [app/database.py](../app/database.py)
- Testar com traces de webhook
- **Impacto esperado:** redução de 60-70% das perdas

### Fase 2: Normalização (Semana 2)
- Adicionar coluna `mensagem_sugerida_normalizada` (opcional, se quiser indexar)
- Ou fazer normalização em Python no `buscar_pedido`
- Ajustar [app/database.py](../app/database.py) na busca por mensagem
- **Impacto esperado:** capturar mais 15-20% das perdas restantes

### Fase 3: Analytics (Semana 3)
- Migration para adicionar `origem` e `data_criacao`
- Função `registrar_mensagem_recebida` em [app/database.py](../app/database.py)
- Chamar função em [app/whatsapp_orquestrador.py](../app/whatsapp_orquestrador.py) no fallback
- View no admin para análise de mensagens recebidas

---

## Arquivos de Referência Atual

**Clique na landing:**
- [app/templates/pudim.html](../app/templates/pudim.html#L117) — captura gclid da URL

**Criação do lead:**
- [app/app.py](../app/app.py#L170) — rota POST `/api/v1/webhook/gravar-lide`
- [app/lead_incluir.py](../app/lead_incluir.py#L19) — função `persistir_lead`
- [app/agente_gera_mensagem_inicial.py](../app/agente_gera_mensagem_inicial.py#L71) — geração aleatória da mensagem

**Webhook do WhatsApp:**
- [app/app.py](../app/app.py#L74) — rota POST `/api/v1/webhook-whatsapp`
- [app/whatsapp_orquestrador.py](../app/whatsapp_orquestrador.py#L46) — `recebe_webhook`
- [app/whatsapp_orquestrador.py](../app/whatsapp_orquestrador.py#L107) — `buscar_pedido` (local das mudanças)

**Banco de dados:**
- [app/database.py](../app/database.py#L442) — `get_ultimo_pedido_por_mensagem_sugerida`
- [app/database.py](../app/database.py#L469) — `vincula_pedido_com_contato`
- [app/database.py](../app/database.py#L622) — `busca_vendas_pendentes_google` (só pega gclid não nulo)

---

## Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|-------|---|---|
| Cliente acha `[ref:NNNN]` estranho | Baixa | Usar formato menos visível (`#NNNN`) ou quebra de linha |
| Formato do token não funciona no WhatsApp | Muito baixa | Token é texto simples, WhatsApp suporta |
| Gera mais falsos positivos na busca normalizada | Baixa | Restringir por produto e telefone na query |
| Analytics salva muitos registros | Muito baixa | É só append na tabela existente |

---

## Métricas de Sucesso

- **Antes:** 15-20% de perda de atribuição
- **Esperado após Fase 1:** 5-10% de perda
- **Esperado após Fase 2:** 2-5% de perda
- **Esperado após Fase 3:** Base de dados para melhorar continua

---

## Próximos Passos

1. Discutir formato do token (ex: `[ref:4821]` vs alternativa)
2. Confirmar prioridade das fases
3. Estimar esforço de implementação
4. Iniciar Fase 1
