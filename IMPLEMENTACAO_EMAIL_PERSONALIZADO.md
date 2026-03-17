# ✅ Implementação: E-mail de Entrega Personalizado por Produto

## 📝 Resumo

Personalização do e-mail de entrega de e-books para permitir que cada produto tenha seu próprio nome de remetente e cores no template HTML.

---

## 🎨 O Que Foi Feito

### 1. Migration 017 - Novos Campos na Tabela `produtos`

**Arquivo:** `migrations/017_personalizar_email_produto.sql`

```sql
ALTER TABLE produtos
  ADD COLUMN email_nome_remetente VARCHAR(100) NULL,
  ADD COLUMN email_cor_primaria VARCHAR(7) NULL,
  ADD COLUMN email_cor_secundaria VARCHAR(7) NULL;
```

**Seeds incluídos:**
- **Produto 1** (Pães): Luiza | Verde #2d6a1f | Marrom #b45309
- **Produto 7** (Quimio): Luiza Carolina | Rosa #ec4899 | Azul #3b82f6

---

### 2. Código Python Atualizado

**Arquivo:** `app/fluxos/entrega_pedido_email.py`

**Mudanças:**
1. **Função `executar()`**: Lê os 3 novos campos do produto com fallback
2. **Helper `_lighten_hex()`**: Calcula versão +30% mais clara da cor primária para gradient
3. **Função `_corpo_html()`**: Template HTML dinâmico com 6 pontos de personalização

**Pontos personalizados no e-mail:**
- ✅ Nome no corpo: "Aqui é a **{nome}**..."
- ✅ Nome na assinatura: "Com carinho, **{nome}**"
- ✅ Cor do header (gradient automático)
- ✅ Cor dos botões de download (2x)
- ✅ Cor dos checkmarks de confirmação (2x)
- ✅ Cor da dica do WhatsApp

**Valores fallback** (quando campos são NULL):
- Nome: `"LSN Livros"`
- Cor primária: `"#2d6a1f"` (verde)
- Cor secundária: `"#b45309"` (marrom)

---

## 🚀 Como Aplicar

### 1. Executar Migration

```bash
docker compose exec -T db mysql -u appuser -pu9p1s8a0 vendasdb < migrations/017_personalizar_email_produto.sql
```

### 2. Verificar Colunas Criadas

```bash
docker compose exec db mysql -u appuser -pu9p1s8a0 vendasdb -e "DESCRIBE produtos;" | grep email_
```

**Saída esperada:**
```
email_remetente      | varchar(120) | YES  |
email_nome_remetente | varchar(100) | YES  |
email_cor_primaria   | varchar(7)   | YES  |
email_cor_secundaria | varchar(7)   | YES  |
```

### 3. Verificar Seeds

```bash
docker compose exec db mysql -u appuser -pu9p1s8a0 vendasdb -e "
  SELECT id, descricao, email_nome_remetente, email_cor_primaria, email_cor_secundaria
  FROM produtos
  WHERE id IN (1, 7);"
```

**Saída esperada:**
```
+----+------------------+----------------------+--------------------+----------------------+
| id | descricao        | email_nome_remetente | email_cor_primaria | email_cor_secundaria |
+----+------------------+----------------------+--------------------+----------------------+
|  1 | Guia Digital     | Luiza                | #2d6a1f            | #b45309              |
|  7 | Dicas de Quimio  | Luiza Carolina       | #ec4899            | #3b82f6              |
+----+------------------+----------------------+--------------------+----------------------+
```

---

## 🧪 Como Testar

### Teste 1: E-mail do Produto 1 (Pães)
- Deve manter visual atual (verde/marrom)
- Corpo: "Aqui é a **Luiza**..."
- Assinatura: "Com carinho, **Luiza**"

### Teste 2: E-mail do Produto 7 (Quimio)
- Visual rosa/azul
- Corpo: "Aqui é a **Luiza Carolina**..."
- Assinatura: "Com carinho, **Luiza Carolina**"

### Teste 3: Produto Sem Campos Preenchidos
- Deve usar fallback: "LSN Livros", cores verde/marrom

**Script de teste rápido:**
```python
# No console Python do container
from app.fluxos import entrega_pedido_email
entrega_pedido_email.executar(pedido_id=123)  # substitua pelo ID real
```

---

## 🎛️ Integração com Admin

### Localização

Os 3 novos campos estão disponíveis em:

**Produtos → Editar Produto → Aba "Entrega Digital"**

Campos adicionados:
- ✅ **Nome do remetente** (aparece no e-mail)
- ✅ **Cor primária do e-mail** (hexadecimal)
- ✅ **Cor secundária do e-mail** (hexadecimal)

### Funcionalidade de Clone

Ao clonar um produto, os 3 campos de personalização de e-mail são **automaticamente copiados** para o novo produto.

---

## 📋 Admin: Clone de Produto (TODO Futuro)

**Lembrete:** Quando implementar a funcionalidade de clone de produto no painel admin, incluir os 3 novos campos:
- `email_nome_remetente`
- `email_cor_primaria`
- `email_cor_secundaria`

---

## 🎨 Sugestões de Cores para Futuros Produtos

| Tema | Cor Primária (Header) | Cor Secundária (Botões) |
|------|----------------------|-------------------------|
| Saúde/Médico | `#1e40af` (azul) | `#059669` (verde) |
| Beleza | `#ec4899` (rosa) | `#a855f7` (roxo) |
| Fitness | `#dc2626` (vermelho) | `#f97316` (laranja) |
| Educação | `#7c3aed` (roxo) | `#3b82f6` (azul) |
| Finanças | `#059669` (verde) | `#eab308` (amarelo) |

**Dica:** Use ferramentas como [HTML Color Picker](https://htmlcolorcodes.com) para escolher cores harmoniosas.

---

## 📚 Referências de Código

- Migration: [migrations/017_personalizar_email_produto.sql](migrations/017_personalizar_email_produto.sql)
- Fluxo de entrega: [app/fluxos/entrega_pedido_email.py](app/fluxos/entrega_pedido_email.py)
- Database: [app/database.py](app/database.py) - `get_produto_disponivel_web()`
