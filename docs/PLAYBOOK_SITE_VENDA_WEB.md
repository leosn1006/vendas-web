# Playbook: criar um novo site de vendas web (padrão "Fatia de Bolo")

Este documento descreve o padrão usado para criar `fatia-e.html` (produto 12), pra ser
reaproveitado quando criarmos o site de venda web de outro produto da empresa.

Template de referência (leia antes de começar): `app/templates/fatia-e.html`
Outros exemplos do mesmo padrão: `app/templates/tempero-e.html`, `app/templates/pudim-e.html`

---

## 1. Decisões de negócio a alinhar ANTES de escrever qualquer código

Nunca assuma — pergunte ao usuário:

1. **Nome de marca** a usar na página (pode divergir do nome cadastrado no banco — confirme os dois).
2. **Preço** de venda web (pode divergir do preço/faixa usada no WhatsApp).
3. **Persona/rosto humano**: existe uma pessoa real associada ao produto (confeiteira, autora)?
   Existe foto real dela em algum asset já enviado (procure em `static/images/` por fotos de
   pessoas antes de assumir que precisa de placeholder)? Confirme o nome exato — pode haver
   diferença entre o "nome de marca" nas artes (ex: "Ju Negreiros") e o nome usado no tom de
   conversa do agente de vendas do WhatsApp (ex: "Juliana"), que costuma ser o mesmo nome
   abreviado — não são necessariamente pessoas diferentes.
4. **Bônus grátis vs. order bump pago**: no fluxo WhatsApp, alguns itens só são entregues como
   recompensa por enviar comprovante de pagamento. Isso NÃO deve virar um bônus grátis automático
   no checkout web (que já é gated por pagamento confirmado) — normalmente esse item deve virar
   um **order bump pago**, não um bônus grátis duplicado. Pergunte se não tiver certeza.
5. **Botão de ajuda via WhatsApp no checkout**: `checkout.html` é compartilhado por todos os
   produtos — adicionar esse botão afeta todo mundo. Alinhe o escopo antes de mexer.

## 2. Pesquisa técnica (fazer com Explore/leitura direta, não adivinhar)

- Leia o template mais recente e mais completo já existente (hoje: `fatia-e.html`) como base.
- Confirme como a rota da landing é registrada em `app/app.py` (padrão
  `GET /<slug>-e` → `rastrear_visita_funil` → cookie `pedido_web_<id>` → `render_template`).
- Confirme que `/pay/<id>` e o checkout (`app/web/checkout.py`, `checkout.html`) são genéricos —
  normalmente **não precisam de nenhuma mudança de código**, só de dados corretos no produto.
- Levante os assets já existentes do produto (`static/images/`, `static/audios/`,
  `static/arquivos/`) antes de pedir novos — geralmente já tem bastante coisa aproveitável do
  fluxo WhatsApp.
- Confira o estado atual da linha do produto em `produtos` (preço, `disponivel_web`, `url_pdf`,
  `email_remetente` etc.) — é comum estar com valores errados/copiados de outro produto.

## 3. Design system (paleta e componentes reaproveitáveis de `fatia-e.html`)

### Variáveis CSS (`:root`)
```css
--preto:        #0c0a09;   /* fundo base — mantém igual em todo site */
--preto-cl:     #1c1917;   /* fundo dos cards */
--cinza-borda:  #292524;
--verde:        #b45309;   /* cor primária do produto — TROCAR por produto (era canela aqui) */
--verde-esc:    #92400e;   /* tom escuro da cor primária */
--ambar:        #f59e0b;   /* accent quente — TROCAR por produto */
--rosa:         #ec4899;   /* accent do glow — TROCAR por produto */
--branco:       #f5f5f4;
--cinza-texto:  #a8a29e;
--sombra:       0 4px 24px rgba(0,0,0,0.5);
--btn-verde:    #16a34a;   /* opcional: cor separada só pros botões de CTA, pra testar sem mexer no resto */
--btn-verde-esc: #15803d;
```
Mantenha os NOMES das variáveis (`--verde`, `--ambar`, `--rosa`) mesmo trocando os valores hex —
isso permite copiar o CSS inteiro de uma seção pra outra sem precisar caçar cada `var()`.

### Fonte maior (público 35+)
```css
html { font-size: 115%; }
```
Todo o resto do CSS usa `rem`, então isso escala o site inteiro de uma vez.

### Glow badge (pílula com brilho animado, estilo Google One)
Estrutura em 3 camadas — o halo é pintado ANTES da pílula sólida na ordem do DOM, então a pílula
cobre o miolo do halo e só a borda borrada fica visível:
```html
<div class="glow-badge-holder">
    <div class="glow-badge-stack">
        <div class="glow-badge-halo"></div>
        <div class="glow-badge"><h2>Título da seção</h2></div>
    </div>
</div>
```
**Regra importante**: só o `<h2>` vai dentro do `.glow-badge`. Se colocar `<div class="divider">`
e `<p>` juntos ali dentro, em telas estreitas (mobile) a caixa fica quase quadrada e o
`border-radius: 999px` transforma a pílula num CÍRCULO feio em vez de uma elipse alongada. O
divisor e o parágrafo de subtítulo ficam FORA do badge, como texto centralizado normal, logo
abaixo do `.glow-badge-holder`.

CSS completo (copiar de `fatia-e.html`, seção "GLOW BADGE"): classes `.glow-badge-holder`,
`.glow-badge-stack`, `.glow-badge-halo`, `.glow-badge`, `.glow-badge h2`, `@keyframes glowShift`.

### Degradê ambiente nas laterais (`body::after`)
Fixo na tela, some sozinho quando a área útil ocupa a tela toda (mobile):
```css
body::after {
    content: '';
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 2;
    background:
        linear-gradient(to right, rgba(180,83,9,0.32), transparent calc((100vw - 1080px) / 2)),
        linear-gradient(to left, rgba(236,73,153,0.28), transparent calc((100vw - 1080px) / 2));
    mix-blend-mode: screen;
}
```
Troque `1080px` pelo `max-width` padrão que você usar nas seções (ver abaixo) e as cores rgba
pelos equivalentes da paleta do produto.

### Max-width consistente no desktop
Todas as seções de conteúdo largo (persona, categorias, bônus, "o que você recebe", carrossel,
lista de dores) devem usar o **mesmo** `max-width` no breakpoint desktop (`fatia-e.html` usa
`1080px`) — senão as bordas esquerda/direita ficam desalinhadas seção a seção ao rolar a página.
Seções "coluna de leitura" mais estreitas (preço, FAQ, calculadora, garantia) podem ficar mais
estreitas e centralizadas (`720px`) de propósito — isso é intencional, não é bug.

### Carrossel orbital (opcional — usar se o produto tiver variedade visual, ex. sabores)
Foto central circular + ícones (miniaturas de foto real, não emoji) numa meia-lua aberta pra
baixo, clique troca a foto em destaque do lado esquerdo. Ver classes `.orbit-*` em `fatia-e.html`.
Pontos de atenção já resolvidos lá que valem reaproveitar direto:
- O ícone no topo do arco (ângulo 270°) precisa de `margin-top` extra no `.orbit-circle` pra não
  ser cortado pela borda do container (a distância do `translate()` + raio do ícone ultrapassa o
  raio do círculo).
- O anel colorido usa um wrapper com `overflow:hidden; height:50%` pra virar meia-lua em vez de
  círculo fechado.

### Botões de CTA
Classes `.hero-cta-btn`, `.btn-hero`, `.btn-cta`, `.sticky-bar a` — todas usam gradiente
`var(--verde)`→`var(--verde-esc)` com `box-shadow` pulsante. Se quiser testar uma cor diferente
só nos botões (sem mexer no resto da paleta), use `--btn-verde`/`--btn-verde-esc` como no exemplo.

### Estrutura de seções (ordem usada em `fatia-e.html`)
urgency-bar → hero (foto + CTA + nota de voz) → proof-bar (números) → pain-sec (dores numeradas,
sem emoji — ver seção 5) → galeria/carrossel → inside-sec (o que vem na compra) → steps-sec (como
funciona, numerado) → persona-sec → categorias (accordion) → bonus-sec → calculadora de renda →
offer-sec (preço) → guar-sec (garantia 7 dias) → faq-sec → final CTA → footer → sticky-bar mobile.

## 4. Conteúdo/copy — checklist de confiança (público 35+, baseado em análise de conversas reais)

- Selos de segurança perto do botão de compra: arquivo seguro/sem vírus, acesso vitalício, pronto
  pra impressão em A4.
- Garantia incondicional de 7 dias (substitui o "veja antes de pagar" do WhatsApp).
- Seção de persona com pessoa real (foto real, não fabricar).
- Lista bem clara do que vem na compra, sem deixar dúvida do tipo "manda só uma parte ou tudo?".
- Calculadora de ROI simples (custo x venda x volume).
- **Nunca inventar depoimentos/avaliações fictícias.** Se não existe histórico de vendas real do
  produto ainda, prefira omitir a seção de depoimentos a inventar uma — sinalize como pendente.
- Emoji como ícone de lista: evite. Prefira reaproveitar um componente visual do próprio design
  system (ex: os círculos numerados de `.step-num`, aplicados também na lista de dores) — mais
  consistente entre dispositivos e mais "sério" que emoji solto.

## 5. Passo a passo de implementação

1. Copiar `fatia-e.html` (ou o template mais recente) pra `app/templates/<slug>-e.html`; adaptar
   copy, imagens, cores, contagem de bônus/e-books.
2. Adicionar rota `GET /<slug>-e` em `app/app.py`, copiando o bloco de `fatia_e()`.
3. Ajustar a linha do produto em `produtos` (via admin ou SQL direto no ambiente de dev):
   `preco`, `descricao`, `disponivel_web=1`, `url_pdf`, `imagem_checkout`, `email_remetente`,
   `email_nome_remetente`, `email_cor_primaria/secundaria`, `url_pagina_vendas`.
4. Cadastrar `produto_bonus` (itens grátis) e revisar/cadastrar `produto_bump` (upsell pago) —
   sem esquecer de excluir o próprio produto da lista de bumps se ele já existir como bump em
   outro produto.
5. Converter imagens novas pra WebP e descartar o PNG/JPG original (ver script abaixo).
6. Rebuild + deploy: `docker compose build app && docker compose up -d app`.
7. Testar: `curl` simples pra status 200 + rodar a suíte Playwright (seção 6) pra desktop e
   mobile antes de considerar pronto.

### Script de conversão de imagem (PNG/JPG → WebP)
```python
from PIL import Image
im = Image.open('nome-do-arquivo.png').convert('RGB')
im.save('nome-do-arquivo.webp', 'WEBP', quality=88)
```
Depois `rm` no arquivo original.

## 6. Teste automatizado (Playwright)

Existe um navegador headless disponível no host (`playwright` instalado via pip, Chromium via
`p.chromium.launch()`). Não precisa Docker nem hosts fake — o nginx local responde direto em
`http://localhost/<rota>` sem precisar de Host header especial (confirmado: existe um vhost
padrão que atende esse caso).

Checklist mínimo do teste (adaptar de uma sessão anterior — pedir pro agente montar um script
Python com Playwright cobrindo):
- Screenshot desktop (~1440px) e mobile (~390px).
- Sem erros de console/página.
- Sem overflow horizontal (`document.documentElement.scrollWidth == clientWidth`).
- Interações: abrir FAQ, abrir accordion de categoria, clicar em ícone de carrossel (se houver) e
  confirmar troca de imagem, mexer no slider da calculadora e confirmar que o valor muda, clicar
  no CTA principal e confirmar que navega pra `/pay/<id>`.

**Cuidado com `full_page=True` em páginas muito altas**: pode gerar blocos brancos falsos no
screenshot por causa de elementos `position:fixed` + `mix-blend-mode`/`filter` (é um artefato da
ferramenta, não bug real). Se aparecer uma área branca suspeita, confirme com
`window.scrollTo({top: Y, behavior: 'instant'})` (não use scroll `smooth`, senão o print pode
capturar a animação no meio do caminho) + screenshot normal de viewport antes de reportar como bug.

## 7. Ambiente

Confirme sempre, no início da sessão, se o stack Docker local é ambiente de desenvolvimento
isolado (banco e credenciais de pagamento próprios) ou se compartilha credenciais reais de
produção (BB Pay, Google Sheets/Ads) mesmo rodando localmente — isso muda o quão à vontade dá pra
gerar PIX de teste, rodar rebuild/restart sem pedir confirmação, etc. Não assuma either way.
