# Melhorias Landing Page — Guia Pães Sem Glúten e Sem Lactose

## Status das melhorias

| # | Melhoria | Status |
|---|---|---|
| 1 | CTA no hero | ✅ Feito |
| 2 | "Sem lactose" no posicionamento | ✅ Feito |
| 3 | Seção da autora (Luiza) | ✅ Feito |
| 4 | Garantia de 30 dias | ❌ Mantido 7 dias (lei brasileira exige mínimo 7d) |
| 5 | Fotos reais nos depoimentos | ⏳ Pendente (amanhã) |
| 6 | Botão sticky no rodapé | ✅ Feito |
| 7 | Fonte mínima 13px (hoje tem 10-11px em vários lugares) | ✅ Feito |
| 8 | Contador de urgência | ✅ Feito |
| 9 | Fortalecer os bônus | ✅ Feito |

---

## Detalhes de cada melhoria pendente

### 4 — Garantia de 30 dias
- **Onde:** seção `.garantia-box`
- **O que muda:** trocar "Garantia de 7 Dias" por "Garantia de 30 Dias"
- **Por quê:** padrão do mercado de infoprodutos é 30 dias. Com 7 dias, a usuária sente risco. Com 30 dias, o argumento "não tenho o que perder" fica muito mais forte para R$19,90.

### 5 — Fotos reais nos depoimentos
- **Onde:** seção `.depoimentos-lista` — os avatares são iniciais (M, C, R) em círculo verde
- **O que muda:** substituir os círculos coloridos por `<img>` com foto real (mesmo pequena, 36x36px)
- **Por quê:** mulheres 35+ confiam muito mais em rostos reais do que em iniciais. Aumenta significativamente a credibilidade dos depoimentos.
- **Como fazer:** salvar fotos em `/static/images/depoimento-maria.jpg` etc. e trocar o HTML

### 6 — Botão sticky no rodapé
- **Onde:** novo elemento fixo `position: fixed; bottom: 0`
- **O que muda:** botão "COMPRAR POR R$19,90" aparece fixo na parte inferior da tela após 30% de scroll
- **Por quê:** em mobile a usuária lê a página e quando quer comprar precisa voltar a encontrar o botão. O sticky resolve isso sem esforço.

### 7 — Fontes pequenas demais
- **Onde:** vários lugares com `font-size: 10px`, `11px`
  - `.strip-label` → 10px
  - `.section-label` → 11px
  - `.hero-badge` → 11px
  - `.oferta-bonus .bonus-label` → 10px
  - `.footer-links` → 11px
- **O que muda:** elevar para mínimo 13px nos elementos secundários
- **Por quê:** público 40-55 anos tem dificuldade com fontes pequenas. Prejudica leitura e experiência.

### 8 — Contador de urgência
- **Onde:** na seção de oferta, acima do preço
- **O que muda:** adicionar `<div id="timer">` com contador regressivo de 15-30 minutos (reinicia a cada visita via `sessionStorage`)
- **Por quê:** cria senso de urgência e movimento visual que prende atenção. Funciona muito bem para produtos lowcost de impulso.
- **Texto sugerido:** "⏰ Oferta expira em: 14:32"

### 9 — Fortalecer os bônus
- **Onde:** `.oferta-bonus` na seção de oferta
- **O que muda:**
  - Trocar "Livro de Bolos Sem Glúten" por nome mais específico com exemplo de receita
  - Sugestão: **"Livro de Bolos Sem Glúten e Sem Lactose** — incluindo o Bolo de Chocolate Fofinho que ninguém acredita que é sem glúten"
  - Considerar adicionar um 2º bônus: "Lista de Compras Pronta para o Mercado" (simples de criar, alto valor percebido)
- **Por quê:** bônus genérico não agrega valor percebido. Nomear receitas específicas desperta desejo imediato.

---

## Melhorias já implementadas (detalhes)

### 1 — CTA no hero ✅
- Botão `QUERO APRENDER A FAZER EM CASA →` adicionado abaixo da imagem da capa
- Animação de pulso suave (laranja)
- Microcopy: "🔒 Pagamento seguro via PIX · Acesso imediato"

### 2 — "Sem lactose" no posicionamento ✅
- `<title>` e `<meta description>` atualizados
- Hero badge: "Sem Glúten · Sem Lactose · Acesso imediato"
- `hero-sub` com "sem glúten e sem lactose" em negrito
- Seção DOR: lactose adicionada, faixa etária corrigida para 35 anos
- Seção SOLUÇÃO: "100% sem glúten e sem lactose"
- Card de benefício "Saúde em Primeiro Lugar"
- Box da oferta: título e subtítulo

### 3 — Seção da autora (Luiza) ✅
- Inserida entre SOLUÇÃO e BENEFÍCIOS
- Foto circular 80x80px com borda verde (`/static/images/luiza.jpg`)
- 3 parágrafos da história baseados no áudio transcrito
- Citação destacada com borda lateral verde
