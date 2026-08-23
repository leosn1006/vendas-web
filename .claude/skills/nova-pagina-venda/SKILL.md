---
name: nova-pagina-venda
description: Cria um novo site de vendas 100% web (landing + checkout PIX) para um produto da empresa, seguindo o design system e o padrão técnico validado em app/templates/fatia-e.html (glow badges animados, paleta customizável por produto, carrossel orbital opcional, integração com o checkout genérico já existente). Use quando o usuário pedir para criar, montar ou fazer "o site de vendas web" / "a landing" de um novo produto, ou pedir para replicar o padrão do Fatia de Bolo em outro produto.
---

# Nova página de vendas web

Guia de referência completo (design system em detalhe, checklist de confiança, exemplos de CSS):
[docs/PLAYBOOK_SITE_VENDA_WEB.md](../../../docs/PLAYBOOK_SITE_VENDA_WEB.md). Leia esse arquivo
antes de escrever código — este SKILL.md é só o roteiro de execução.

Template de referência canônico: `app/templates/fatia-e.html`.

## Fase 0 — Ambiente

Confirme com o usuário (ou releia memória do projeto) se o Docker local é ambiente de dev
isolado ou compartilha credenciais reais de pagamento/Google. Isso muda o quanto dá pra agir sem
pedir confirmação a cada passo (rebuild de container, gerar PIX de teste, etc).

## Fase 1 — Alinhar decisões de negócio (perguntar, não assumir)

Use AskUserQuestion pra confirmar, um de cada vez ou agrupado:
- Nome de marca da página (pode divergir do nome no banco).
- Preço de venda web.
- Existe persona/pessoa real do produto? Tem foto real já enviada em `static/images/`?
- Algum item do fluxo WhatsApp que só era liberado com comprovante deve virar order bump pago em
  vez de bônus grátis automático?

## Fase 2 — Pesquisa técnica (Explore ou leitura direta)

1. Leia `app/templates/fatia-e.html` inteiro como referência de estrutura/CSS/JS.
2. Confira a rota da landing mais recente em `app/app.py` (padrão `GET /<slug>-e`).
3. Confirme que `/pay/<id>` e `checkout.html` não precisam de mudança de código — só de dados.
4. Levante assets já existentes do produto (`static/images/`, `static/audios/`,
   `static/arquivos/`) antes de pedir novos.
5. Consulte o estado atual da linha do produto em `produtos` — geralmente tem campos errados
   copiados de outro produto (`url_pdf`, `email_remetente` etc).

## Fase 3 — Implementação

Progresso a acompanhar:
```
- [ ] Copiar fatia-e.html -> app/templates/<slug>-e.html, adaptar copy/imagens/paleta
- [ ] Adicionar rota GET /<slug>-e em app/app.py
- [ ] Ajustar produtos: preco, descricao, disponivel_web=1, url_pdf, imagem_checkout,
      email_remetente/nome/cores, url_pagina_vendas
- [ ] Cadastrar produto_bonus (grátis) e revisar produto_bump (pago)
- [ ] Converter imagens novas pra WebP, descartar original
- [ ] Rebuild + deploy do container app
- [ ] Testar (curl + Playwright, desktop e mobile)
```

Pontos do design system que já foram resolvidos no template de referência e **não devem ser
reinventados** — só copiar e trocar as cores hex mantendo os nomes das variáveis CSS:
- Glow badge: **só o `<h2>` vai dentro da pílula** — divider/parágrafo ficam fora, senão a
  pílula vira círculo em telas estreitas.
- `html { font-size: 115%; }` pra legibilidade.
- `max-width` consistente (mesmo valor) em todas as seções largas do desktop.
- Degradê lateral (`body::after`) usando `calc((100vw - <max-width>px) / 2)` pra sumir sozinho
  quando não sobra margem.
- Se usar carrossel orbital: ícone do topo do arco precisa de `margin-top` extra no container pra
  não ser cortado.

Ver o playbook completo pra trechos de CSS prontos pra copiar.

## Fase 4 — Teste

Rode um script Playwright (Chromium headless local, `pip install playwright` já disponível neste
ambiente) cobrindo desktop (~1440px) e mobile (~390px): screenshot, zero erros de console, zero
overflow horizontal, e testar as interações principais da página (accordion, carrossel se
houver, calculadora, CTA navegando pro checkout). Detalhes e ressalvas sobre screenshots
full-page no playbook, seção 6.

## Fase 5 — Fechar com o usuário

Resuma o que foi feito e peça validação visual antes de considerar a página pronta pra tráfego
pago. Nunca habilite valor de teste de checkout (`CHECKOUT_VALOR_TESTE_PRODUTO_<id>`) sem avisar,
e desative de novo depois do teste.
