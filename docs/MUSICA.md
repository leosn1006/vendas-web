# Produto Música (Música de Presente)

A cliente responde um quiz sobre quem vai ganhar a música, uma IA escreve a letra, o gerador compõe 2 versões
e ela **ouve 40 s grátis de cada uma** antes de pagar. Pagou, recebe a música completa (ouvir, baixar) e os
itens que comprou. Veio do projeto do Bruno (`brunogpn/musica-presente`); a lógica de quiz, letra, geração,
prévia e videoclipe é dele, o encaixe (planos, checkout, pagamento, e-mail, Celery, Ads) é o do sistema.

## O que se vende (produto → planos → entregáveis, ver PLANOS.md)

Entregável `tipo = 'musica'` com um **recurso** (`entregaveis.recurso`, gravado também em `pedido_itens.recurso`),
como o `app_slug` dos apps. Lista em `app/musica/dominio/recursos.py`:

| Recurso | Papel no plano | O que libera |
|---|---|---|
| `musica` | principal | as 2 versões completas (ouvir, baixar, letra) |
| `videoclipe` | principal | fotos da cliente + música em vídeo vertical |
| `qrcode` | order bump | cartão para imprimir com o QR da página do presente |
| `entrega_email` | order bump | e-mail e/ou WhatsApp para quem recebe (agora ou na hora marcada), com aviso para quem comprou; **só o link** |
| `entrega_whatsapp` | — | recurso antigo, **não vendido**: o WhatsApp entrou no bump `entrega_email` (migration 091) |

Planos: **Música** (padrão) e **Música + Videoclipe**. Os preços são do plano e dos bumps (admin), nunca do código.
O admin recusa recurso no papel errado e item de música no plano padrão de produto com WhatsApp.

## O caminho da cliente

```
/musica/?ocasiao=mae  (landing; cria o rascunho 1004 com o GCLID)
  → /musica/criar     (quiz; e-mail obrigatório; WhatsApp opcional, que já abre preenchido no checkout)
  → /musica/p/<token> (letra → ajustes → "criar a música" → espera → prévia → escolha do plano)
  → /pay/<produto>?plano=...&musica=<token>   (checkout de sempre, com os order bumps)
  → /musica/compra/<guid>   (quem comprou: ouvir/baixar, QR, presente por e-mail, fotos do videoclipe)
  → /musica/m/<token>       (o presente: só a música e o vídeo; é para onde o QR e o e-mail apontam)
```

- **Checkout:** plano de música só abre com `?musica=` de uma música com a prévia pronta, do mesmo produto e
  ainda não comprada; sem isso volta para a prévia. `gerar_pix`/`gerar_cartao` conferem de novo
  (`musica_invalida`) e gravam o vínculo em **`musica_pedidos`** (um pedido → uma música; a mesma música pode ter
  mais de um PIX, o primeiro pago libera, e pagamento em dobro avisa a equipe).
- **Liberação:** `tasks.enviar_email_entrega` chama `musica.liberar_do_pedido` (ponto único, como os apps). Redes de
  segurança: a página da compra e `musica.manutencao` (beat, 5 min). Liberada = `musicas.liberada_em` + `pedido_id`.
- **E-mail de entrega:** o mesmo do sistema, com o botão "🎵 Ouvir minha música" para a área da compra.
- **Presente por e-mail (e/ou WhatsApp, ver a seção WhatsApp):** o e-mail sempre com cópia (cc) para quem comprou. Se não chegar (erro no envio, ou devolução do
  servidor de quem recebe — quase sempre caixa lotada — que a leitura da caixa do `admin@` reconhece pelo thread do
  envio), tenta de novo: até **4 envios no mesmo dia**, esperando 1 h, 2 h e 4 h. Depois, quem comprou recebe o link
  para mandar por conta própria e a equipe é avisada. Devolução da cópia de quem comprou não gera reenvio.
- **Estante 2:** card "Minha música". A Música fica fora do cross-sell de e-books (a compra começa no quiz).
- **Google Ads:** o GCLID fica no rascunho da landing (`musicas.pedido_origem_id`); se a compra criar pedido novo
  (ex.: voltou pelo lembrete), ele herda a campanha. Conversão pelo fluxo de sempre (planilha), valor real pago.
- **Analytics Web:** página `musica-v2` (o quiz antigo, de 12 telas, ficou como `musica`) — quiz 1–9 (a etapa leva o nome da tela), letra 20, prévia 30, clique em comprar 40.
- **NF-e:** produto com `nfe_automatica = 0` (admin → dados básicos, só admin) fica fora da emissão diária, por PIX
  e cartão. **A Música precisa ficar assim** até a decisão fiscal (música não é livro).

## Lembretes por e-mail (`musica.lembretes`, desde 27/10/2026)

Quem parou numa etapa recebe **3 e-mails: 15 min, 3 h e 24 h** depois de a música entrar nela
(`config.LEMBRETES_MINUTOS`), das **8h às 22h** (fora disso espera a manhã e, se venceram dois, sai só o mais recente),
por até 3 dias. Regras em `regras.etapa_lembrete` / `proximo_lembrete`; textos em `mensagens._LEMBRETES`.

| Etapa | Quando | Link do botão |
|---|---|---|
| `letra` | viu a letra e não criou a música | página da música (`/musica/p/<token>`) |
| `previa` | ouviu a prévia e não foi ao checkout | página da música |
| `checkout` | o checkout desta música abriu (`checkout_aberto_em`) ou ela tem pedido esperando pagamento (1002) | checkout reabrindo o pedido com o PIX ainda válido |

- Avançou de etapa: o relógio zera e passa a valer a sequência da nova. "Outra versão" (volta para a prévia) não zera,
  e voltar para uma etapa anterior (o PIX venceu) não reenvia: no máximo 3 por etapa, 9 no total.
- Não cobra a música antiga de quem refez e comprou outra com o mesmo e-mail.
- **Por pessoa (e-mail):** quem fez várias músicas recebe os lembretes de uma só — entre as que ainda têm lembrete pela
  frente, a que chegou mais longe no funil (checkout > prévia > letra) e, empatando, a mais recente
  (`regras.uma_por_email`); no mínimo 2 h entre dois lembretes para o mesmo e-mail; "não quero mais" e uma compra
  nas últimas 24 h param todas as músicas daquele e-mail.
- Para quando ela paga ou toca em "Não quer mais estes lembretes?" no rodapé (`/musica/p/<token>/sem-lembretes`:
  o link só pergunta; o botão confirma — leitores de e-mail abrem links sozinhos).
- Pedido de música **não** recebe o e-mail genérico de PIX não pago (`fluxo_followup_web`): a etapa `checkout` cuida.
- Só e-mail por enquanto (falta um template de WhatsApp aprovado para isso). Colunas na migration 095.

## Testes na landing (`inicio.html`)

- **Preço fora da landing (desde o deploy do commit 728c172 — use a data e hora do deploy como corte):** o cartão "Um presente que ninguém esquece" mostra "Você ouve antes e
  só paga se gostar" no lugar do valor; a prévia, o checkout e os e-mails continuam com o preço. Hipótese do Leo:
  quem ouve a própria música paga. Para voltar, descomente o bloco marcado "TESTE" em
  `inicio.html`. Medir em Analytics Web: visitas → "começaram o quiz" e prévia → checkout, antes × depois.
- **Marca no site e nos e-mails:** vem de `produtos.email_nome_remetente` ("Canção de Presente", migration 092); o
  nome interno do produto continua "Música de Presente".

## WhatsApp (número "Canção de Presente", só avisos)

- **Número:** +55 61 8269-6770, WABA `1060756910314417`, ID do número `1376511528883172`, token
  `WHATSAPP_ACCESS_TOKEN_LC` (app "WPP Luiz"). Cadastrado em `telefones_produto` (migration 091) com
  **`responde_mensagens = 0`**: fica fora do rodízio dos links de venda, do número gravado no pedido web e da regra
  "produto que vende pelo WhatsApp" da tela de planos; o orquestrador (`whatsapp_orquestrador._desviar_numeros_so_avisos`)
  entrega tudo o que chega dele à Música — nunca vira lead nem tem resposta da IA. Editável em Admin → Números.
- **Templates aprovados** (pt_BR, parâmetros posicionais, rodapé "Canção de Presente"; conferidos em 22/10/2026):
  - `musica_pronta` (Utilidade) — quem comprou, ao confirmar o pagamento (tarefa `musica.whatsapp_comprador`):
    {{1}} primeiro nome de quem pagou, {{2}} para quem ("sua mãe Helena"), {{3}} link da área da compra. Vai para o
    WhatsApp do **checkout** (que já abre com o do quiz, se ela informou lá — desde 26/10/2026).
  - `presente_surpresa` (Marketing) — quem ganha, no mesmo agendamento do e-mail (`musica.manutencao`, 5 em 5 min):
    {{1}} quem ganha, {{2}} quem mandou; botão "Ouvir minha música" com a etiqueta (payload) = token da música.
    Ao tocar, a Música responde com o link da página do presente (texto livre, no máximo 1 vez por hora).
  - `entrega_feita` (Marketing) — quem comprou, quando a Meta avisa que o presente chegou ("entregue"/"lido", uma vez);
    sem WhatsApp do comprador (ou se falhar), vai por e-mail.
- **Não chegou** (erro no envio ou "failed" da Meta): quem comprou recebe e-mail com o botão
  `/musica/compra/<guid>/enviar` (abre o WhatsApp dela na conversa de quem ganha, com mensagem e link prontos) e pode
  corrigir o número na área da compra.
- **Aviso da Meta antes do wamid gravado** (o "failed" pode vir logo após o envio): é lido de novo 1 min depois,
  uma vez (tarefa `musica.reler_status_whatsapp`).
- **Erro passageiro da Meta** (rede, 5xx) no `presente_surpresa`: tenta de novo nas próximas rodadas (até 3 vezes,
  `presente_wa_status` = `erro1`/`erro2`); depois, vale o caminho do "não chegou". O `musica_pronta` tenta de novo
  na própria tarefa. O remetente é sempre o número de avisos do produto da música (mesmo pausado).
- **Corrigir e tentar de novo:** só o canal que não chegou sai outra vez (o e-mail que chegou não é reenviado, nem o
  WhatsApp que saiu).
- **Order bump:** "Entrega para quem vai receber (e-mail e/ou WhatsApp)" — pelo menos um dos dois, com "Confirmo que
  este WhatsApp é de quem vai receber".
- **Liga/desliga:** `MUSICA_WHATSAPP_ATIVO` (desligado: o campo some da área da compra e nada é enviado). No dev, mesmo
  ligado, o endereço da Meta é o endereço morto do `config.py` (regra do projeto): o envio cai no caminho de falha.
- **Dev:** o hook `.claude/hooks/bloquear_api_meta_dev.sh` libera só consultas de leitura (templates, números,
  debug_token, contas da empresa, objeto por ID) — nunca envio.

## O quiz (9 telas, `app/musica/dominio/quiz.py`)

1. Para quem é (inclui Neto(a), Sogra/Sogro, **Mais de uma pessoa** e **Para mim**) · 2. Nome(s), apelido e
pronúncia (até 4 pessoas) · 3. Ocasião · 4. Lembranças (3 perguntas guiadas + medidor) · 5. Frase que não pode faltar
(opcional) · 6. Tom · 7. Estilo (com amostra) · 8. Voz · 9. Seu nome, e-mail e WhatsApp (opcional).

- **As opções dependem das anteriores**, tudo em dados no `quiz.py`: cada relação tem marcadores (`RELACOES`); cada
  ocasião e tom diz para quem aparece (`para`/`exceto`, tons também `exceto_ocasioes`); as vozes dependem do estilo
  (`VOZES_POR_ESTILO`: dupla só no sertanejo, "com coral" no gospel). Voltar e trocar uma resposta apaga as
  escolhas seguintes que deixaram de combinar. Página de ocasião da landing (`?ocasiao=`) pula a tela 3 só se a
  ocasião combinar com a relação.
- **O navegador manda** `pessoas` e `lembrancas_partes`; o servidor monta `nome`/`apelido`/`pronuncia`/`lembrancas`
  como antes (`regras.montar_respostas`) e guarda `pessoas` para a IA tratar o plural. "Para mim": `de` = o nome.
- Progresso guardado no navegador por 24 h (`localStorage`); o checkout da Música abre com o nome e o e-mail do quiz.
- **Som** (`conteudo/estilos.json`): o gênero vem primeiro; o tom (`clima`) só descreve o sentimento — nunca um gênero
  ("ballad" no tom puxava tudo para balada); `negativo_estilo` (o que o Suno deve evitar em cada estilo) e
  `voz_estilo` (voz própria de um estilo, ex.: gospel = "powerful female worship vocals").
- **Amostras do "aperte o play"**: `docker compose exec app python -m musica.ferramentas.gerar_amostras --estilos
  rock,gospel` (11 créditos por estilo; grava em `storage/musica/amostras/<estilo>-1/-2.mp3`, sem mexer no site). A
  escolhida vai para `app/musica/static/estilos/<estilo>.mp3`. Rock e gospel refeitos em 22/10/2026; os outros 18
  gerados com as descrições novas, aguardando a escuta do Bruno.

## Arquitetura (`app/musica/`, portas e adaptadores)

```
dominio/        regras puras: modelos (status, resultados), regras (estilo, prévia, trava, presente),
                legenda (encaixe da letra), quiz, recursos
portas.py       GeradorMusica, EscritorLetra, Transcritor, Audio, Video, Repositorio, Agenda, Notificador
adaptadores/    gerador_apiframe (MVP) · gerador_suno (esqueleto) · gerador_simulado (dev/testes)
                letra_openai (+ LetraSimulada) · transcritor_openai · audio_ffmpeg · video_ffmpeg
                repositorio_mysql (todo o SQL) · agenda_celery · notificador (Gmail; WhatsApp desligado) · arquivos
fabrica.py      escolhe os adaptadores pelo .env — único lugar que conhece os provedores
casos_de_uso.py o fluxo inteiro; só fala com as portas
rotas.py        HTTP fino (erros jsonify 4xx, POST com origem_confiavel); tarefas.py: Celery fino
integracao.py   o que checkout, tasks, e-mail e Estante usam daqui
```

**Trocar a Apiframe por uma conta própria do Suno:** implementar os 3 métodos de `adaptadores/gerador_suno.py`
(`criar`, `consultar`, `webhook_valido`, devolvendo os objetos de `dominio/modelos.py`) e `MUSICA_GERADOR=suno`.
Nada mais muda. Antes, confirmar se existe acesso oficial do Suno por API para uso comercial.

**Letra:** a nossa integração OpenAI (`OPENAI_API_KEY`, `chat.completions`, saída `json_schema`), modelo em
`MUSICA_MODELO_LETRA` (padrão `gpt-6.1-sol`, o que venceu o teste do Bruno; testado em 17/10/2026 com o
`openai==1.59.7` atual). Regras de composição em `conteudo/instrucoes_letra.md`, estilos em `conteudo/estilos.json`.

**Filas:** letra na `urgente` (a cliente espera na tela); gerar/consultar (a cada 10 s, ou pelo webhook com
`MUSICA_URL_PUBLICA`), presentes e lembretes na `normal`; videoclipe e limpeza na `baixa` (concorrência 2 segura
o pico das datas fortes). Arquivos em `storage/musica/<token>/` (privado, volume do app e dos workers).

**Rotinas (beat):** `musica.manutencao` (5 min: presentes na hora marcada, destravar tarefa perdida, reconciliar
pagos), `musica.lembretes` (a cada 5 min; ver "Lembretes"),
`musica.limpeza` (04h13: apaga músicas não compradas de 90+ dias, banco e disco — promessa da privacidade).

**Custo e abuso:** cada quiz custa uma letra na OpenAI e cada prévia uma geração (~11 créditos). Limites por e-mail
ou IP em 24 h: `MUSICA_LIMITE_LETRAS_DIA` (5 quizzes) e `MUSICA_LIMITE_PREVIAS_DIA` (3 músicas — conta só o que a
cliente pediu, "criar a música" e "outra versão"; as novas tentativas automáticas depois de falha do gerador não
contam). 1 "outra versão", 2 ajustes de letra. **Turnstile ligado em produção** (`TURNSTILE_*`; o app avisa no log
se faltar).

**Configuração:** o que é do produto fica no banco — qual produto vende (o ativo/à venda cujo plano padrão tem item
de música), preços, remetente e a **empresa** dos termos e da privacidade (a configuração fiscal ligada ao produto,
`nfe_config_id`: a LBE Livros; ligar não emite nota, porque `nfe_automatica = 0`). No `.env`, só provedores, chaves
e limites.

**Videoclipe:** o navegador reduz e envia **uma foto por vez** (cada uma < 900 KB), abaixo do limite de 1 MB do nginx
— não precisa mexer no nginx. Montagem perdida (worker reiniciado) é retomada uma vez pela manutenção.

## Rodar no dev

```bash
docker compose exec -T db sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < migrations/089_musica.sql
# .env: MUSICA_GERADOR=simulado, MUSICA_LETRA_SIMULADA=1 (sem gastar crédito); o produto vem do banco
docker compose up -d --build app worker-urgente worker-normal worker-baixa beat && make reload-nginx
```

Abra `http://localhost/musica/`. No dev, os e-mails da Música só vão para o log. **Atenção:** o e-mail de
entrega do sistema (`entrega_pedido_email.py`) envia de verdade no dev — teste a confirmação de pagamento com um
e-mail seu. Testes: `pytest tests/musica`.

## Checklist para colocar no ar

1. Migrations **089** (estrutura) e **090** (cadastro do produto: 2 planos, 4 itens, empresa LBE, fora da NF-e,
   **disponível no site desligado**), depois `docker compose up -d --build app worker-urgente worker-normal
   worker-baixa beat` + `make reload-nginx`.
2. Admin → produto "Música de Presente": **chave PIX própria** de venda web (não a do produto 6), e-mail remetente
   (em "Enviar e-mail como" do `admin@`), e só então ligar "Disponível para venda no site".
3. `.env` de produção: `MUSICA_GERADOR=apiframe`, `APIFRAME_API_KEY` (a chave nova do Bruno), `TURNSTILE_SITE_KEY` e
   `TURNSTILE_SECRET` (Cloudflare, grátis; sem eles o app avisa no log), `MUSICA_URL_PUBLICA` opcional
   (`https://<domínio>`: a Apiframe avisa quando termina; sem ela, consulta a cada 10 s).
4. A Música abre em `/musica/` de **qualquer** domínio nosso. Para anunciar: planilha do Ads do produto por domínio.
5. **WhatsApp:** migration **091**; conferir (leitura) se a WABA `1060756910314417` está inscrita no app "WPP Luiz"
   (`GET /{waba}/subscribed_apps`) — se não, inscrever uma vez (`POST`), senão botões e avisos de entrega não chegam;
   `.env`: `MUSICA_WHATSAPP_ATIVO=1`. Teste real com números próprios: compra (`musica_pronta`), presente para outro
   número seu (`presente_surpresa` → `entrega_feita`; tocar o botão → link).
6. Uma compra real de ponta a ponta antes dos anúncios.

## Pendências (Leo e Bruno)

- **Estilos (26/10/2026):** a família sertaneja virou um "Sertanejo" só (romântico + universitário + arrocha; o Modão
  saiu) e o Piseiro entrou no Forró (`quiz.ESTILOS_ANTIGOS` troca os valores antigos na criação e na leitura). Os
  textos do gerador de sertanejo, forró, pagode, MPB, balada, funk, rap e bossa tiveram revisão leve (gospel e rock
  ficaram como revisados com o Bruno). **Falta:** gerar e ouvir as amostras novas de pelo menos Sertanejo e Forró
  (`musica.ferramentas.gerar_amostras --estilos sertanejo,forro`, ~11 créditos cada) e a revisão detalhada com o Bruno.

NF-e (conversa à parte); Suno direto (existe API oficial?) e direitos de uso comercial; revisão dos termos e da
privacidade por advogado; preços; WhatsApp (número + modelos aprovados na Meta → `MUSICA_WHATSAPP_ATIVO=1` e
implementar o envio em `adaptadores/notificador.py`); jingle para empresas (etapa 4 do plano do Bruno).
