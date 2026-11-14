# SMS (Comtele) e link curto

SMS do sistema, genérico para qualquer produto (desde 14/11/2026). Primeiro uso: **lembretes da Música** para quem
ouviu a prévia e não pagou. Motivo: e-mail pouca gente olha, e follow-up agressivo pelo WhatsApp arrisca a BM.

## Como funciona

- **Fornecedor:** Comtele, API nova (`POST https://api.comtele.com.br/messages/sms/send`, header `x-api-key`).
  Cliente em `app/sms/comtele.py`.
- **Quem usa monta o texto**, e `sms.servico.enviar(...)` faz o resto:
  1. normaliza o número (por enquanto só celular brasileiro);
  2. cria o **link curto**;
  3. grava em `sms_envios` **antes** de enviar;
  4. agenda a tarefa `sms.enviar` (fila normal).
- **Novas tentativas só quando é certo que a Comtele não aceitou:** sem conexão, HTTP 429 ou 503, em 1, 2 e 4 min.
  - Sem resposta (timeout de leitura) ou HTTP 500/502/504 podem ser SMS já aceito. Esses viram `falhou` com
    "pode ter saído", em vez de repetir um SMS cobrado. O relatório de entrega corrige para `entregue` se vier.
  - Envio parado em `enviando` há mais de 1 h (worker caiu no meio) vira `falhou` pelo `sms.manutencao` (a cada
    30 min), também sem reenviar.
- Não sai: número que não é celular, link sem domínio, ou o mesmo celular recebeu SMS há menos de `minimo_minutos`
  (a Música usa 2 h, o mesmo intervalo dos e-mails). Esse limite é **por celular**: duas músicas com e-mails
  diferentes não somam SMS no mesmo número.
- **Texto sem acento e com no máximo 160 caracteres** (`sms/texto.py`). Um acento muda a codificação: o limite cai
  para 70 e o SMS passa a custar 2 ou 3 vezes. Texto que não cabe **não sai** (fica `falhou`); nunca mandamos 2 partes.
- **Não lemos respostas** e o texto não tem "SAIR". Na Música, quem toca em "não quero mais lembretes" no e-mail
  também para o SMS (o SMS sai junto com o e-mail). Bloqueio pontual: no painel da Comtele (número bloqueado não é
  cobrado).
- **Dev:** com `AMBIENTE=desenvolvimento`, só os números de `SMS_DEV_PERMITIDOS` recebem de verdade. Os outros ficam
  `ignorado_dev`, com o texto no log e no admin.

## Status de `sms_envios`

| status | significado |
|---|---|
| `pendente` | na fila |
| `enviando` | tarefa em curso |
| `enviado` | a Comtele aceitou |
| `entregue` | a operadora confirmou |
| `falhou` | recusa da Comtele, da operadora ou texto longo; ver `erro` |
| `ignorado_dev` | dev, número fora da lista |

**Relatório de entrega:** `POST /sms/comtele/status/<SMS_WEBHOOK_SEGREDO>`, cadastrado no painel da Comtele como URL
de callback de status. O casamento é feito pelo nosso id (`custom`/`Sender`) ou, sem ele, pelo telefone (envio mais
recente das últimas 48 h). O formato que o painel novo manda ainda não foi visto: o payload cru vai para o log, para
ajustarmos `servico.registrar_entrega`. Pelo telefone, o aviso vai para o envio mais antigo ainda sem resposta. Se o painel novo não tiver callback, o plano B é consultar o relatório da
Comtele a cada 15 min.

## Link curto (`/m/<codigo>`, `app/links_curtos.py`)

- **Código:** 7 caracteres com maiúsculas, minúsculas e números, **sem 0 O 1 l I**. São 57 símbolos, cerca de
  1,9 trilhão de códigos.
  - Maiúscula ≠ minúscula (`codigo` em `utf8mb4_bin`).
  - O código nunca forma `aws`, `dump`, `backup` nem `config`, que o nginx derruba (444) como robô.
- **No texto vai sem `https://`**, por exemplo `lsnlivros.com.br/m/k7Hq2Rx`. O celular reconhece como link.
- **Cada acesso fica em `links_curtos_acessos`** (código tentado, se existe, IP, navegador, robô).
  - Robôs (pré-visualização do WhatsApp/iMessage, verificadores de e-mail, curl) não contam como clique.
  - Código inexistente ou expirado leva à página inicial do domínio.
  - Os acessos são apagados em 90 dias (`sms.limpeza`, 04h23), porque IP é dado pessoal.
- **Sem bloqueio por IP:** as operadoras põem milhares de clientes no mesmo IP (CGNAT). O admin mostra os códigos
  inexistentes por dia e os IPs que mais erram. Se aparecer um pico, a verificação do Turnstile é o próximo passo.
- **Serve qualquer canal:** `links_curtos.criar(url, origem, ref_tipo, ref_id, expira_em)`.

## Música

- SMS **junto com cada e-mail de lembrete** das etapas `previa` e `checkout`: até 3 por etapa, 6 por visita, das 8h
  às 22h, como os e-mails. A etapa `letra` não recebe.
- O número é o WhatsApp do quiz ou do checkout (`regras.celular_br`). O quiz avisa: "Vamos te avisar por SMS quando
  sua música estiver pronta."
- Textos em `musica/mensagens.lembrete_sms`, **um para cada lembrete**. A marca vem primeiro, porque o remetente
  é um número curto compartilhado com outras empresas (o 70101, no teste de 14/11), e o link fica sozinho no fim:

  | Lembrete | Texto |
  |---|---|
  | 1º (15 min) | `Cancao de Presente: {nome}, a musica do Cesar ficou pronta e esta guardada pra voce. Ouca de novo e finalize: {link}` |
  | 2º (3 h) | `Cancao de Presente: {nome}, a musica do Cesar continua guardada. Falta so finalizar pra emocionar quem voce ama: {link}` |
  | 3º (24 h) | `Cancao de Presente: {nome}, ainda da tempo! A musica do Cesar esta esperando por voce. Finalize aqui: {link}` |

  - "da/do/de" conforme o quiz; "a sua musica" (e "pra ouvir inteira" no 2º) quando é para a própria pessoa.
  - Sem urgência falsa: a música fica guardada 90 dias.
  - Se não couber em 160, encurta nesta ordem: o nome de quem recebe vira só o primeiro, sai o nome de quem fez, sai
    a marca e, por último, corta o nome de quem recebe.
- O link leva ao mesmo destino do e-mail (prévia ou checkout com o PIX ainda válido).

## Acompanhamento

**Admin → 💬 SMS enviados** (só administradores):
- enviados, entregues, clicaram, pagaram depois (músicas liberadas depois do SMS) e custo estimado
  (`partes × SMS_CUSTO_UNITARIO`);
- a conversão da Música **com celular × sem celular**;
- a lista de envios;
- os acessos ao link curto.

## Configuração (`.env`, nos serviços app e worker-* do `docker-compose.yml`)

| variável | uso |
|---|---|
| `CONTENT_SMS_API` | chave da API nova da Comtele (Configurações → Chaves de API) |
| `SMS_ATIVO` | `1` liga, `0` desliga tudo |
| `SMS_COMTELE_ROTA` | id da rota da Comtele (padrão 17, o do exemplo deles; conferir no painel) |
| `SMS_WEBHOOK_SEGREDO` | segredo no caminho do webhook de entrega |
| `SMS_DEV_PERMITIDOS` | dev: números que recebem de verdade (com 55, separados por vírgula) |
| `SMS_CUSTO_UNITARIO` | custo por parte para o admin (padrão 0,12) |

## Colocar no ar

1. Migration `106_sms_links_curtos.sql`.
2. `.env` de produção: `CONTENT_SMS_API`, `SMS_WEBHOOK_SEGREDO` (gerar um novo) e conferir `SMS_COMTELE_ROTA`.
3. `docker compose up -d --build app worker-urgente worker-normal worker-baixa beat` e `make reload-nginx`.
4. Painel da Comtele: URL de callback de status =
   `https://<domínio>/sms/comtele/status/<SMS_WEBHOOK_SEGREDO>`.
5. Créditos na Comtele.
