# Integração NF-e Modelo 55 — SVRS/DF

Módulo de emissão de Nota Fiscal Eletrônica (NF-e) Modelo 55 integrado ao sistema `vendas-web`. Emite NF-e para pagamentos recebidos via PIX e cartão, multi-tenant (uma linha de configuração por empresa emitente).

---

## Contexto

| Item | Detalhe |
|---|---|
| Empresas emitentes | LSN Livros (pessoal, `tenant_slug=lsn-livros`) e LBE Livros LTDA (`tenant_slug=lbe-livros`) — ver [Multi-tenant](#multi-tenant) |
| Regime tributário | Lucro Presumido (CRT=3) |
| UF emitente | DF (cUF=53) |
| Autoridade SEFAZ | SVRS — SEFAZ Virtual do Rio Grande do Sul |
| Modelo | NF-e 55 (produto/mercadoria) |
| Certificado | A1 (.pfx), um por tenant |

> **Por que NF-e e não NFS-e?** Livros digitais são classificados como mercadoria (NCM 49011000) pela Receita Federal — NF-e modelo 55, não NFS-e municipal.

> **Por que DIY e não SaaS?** Volume alto de notas de baixo valor torna o custo por nota de um SaaS proibitivo. O desenvolvimento se paga rápido.

---

## Multi-tenant

Cada linha de `nfe_configuracao` é uma empresa emitente independente: próprio CNPJ, certificado `.pfx`, contador de numeração (`ultimo_numero_nfe`), tributação e `ambiente`. `produtos.nfe_config_id` liga cada produto ao tenant que deve emitir a nota dele (join usado nas queries de elegibilidade de cartão).

| `id` | `tenant_slug` | CNPJ | Uso |
|---|---|---|---|
| 1 | `lsn-livros` | 64.980.953/0001-46 | Pessoal (Leonardo) |
| 2 | `lbe-livros` | 68.184.503/0001-06 | LBE Livros LTDA |

⚠️ **`ambiente` é por linha, não global.** Errar esse campo numa empresa não afeta a outra — mas errar num ambiente de *desenvolvimento* apontando pra `1` (produção) manda NF-e real pra SEFAZ de verdade. Ver [Isolamento de ambientes](#isolamento-de-ambientes-produção-vs-desenvolvimento) — é a causa raiz do maior incidente já registrado nesse módulo.

---

## Regras de Negócio

Implementadas em `buscar_pagamentos_pix_sem_nfe()` / `buscar_pagamentos_cartao_sem_nfe()` (`app/database.py`) e usadas por `tasks.emitir_nfe_diaria_lbe`:

1. **Só emite depois de 2 dias corridos do pagamento** (`dias_minimos=2`, reduzido de 7 em 13/09/2026 para regularizar mais rápido enquanto a empresa está no início do cadastro) — janela de garantia/devolução do PIX. Emitir antes disso arriscaria ter que desfazer uma nota já autorizada (ver seção de cancelamento abaixo, que na prática quase nunca é viável).
2. **Valor mínimo R$2,00** (`valor_minimo=2.0`) — descarta pagamentos de teste.
3. **`dhEmi` (data de emissão da nota) = data do pagamento, não a data em que a rotina realmente roda.** Confirmado com o contador: no DF a competência fiscal é a data do fato gerador (o pagamento), e o prazo de escrituração é **até o dia 20 do mês subsequente** à competência. Isso significa que pagamentos de início de mês têm bastante folga; pagamentos de fim de mês processados só quando o backlog "andar" podem ficar apertados — vale monitorar o backlog, não deixar crescer indefinidamente.
4. **Devolução parcial de PIX**: emite pelo saldo líquido (`valor - devoluções liquidadas`), não pelo valor bruto.
5. **Devolução total de PIX**: não emite (`valor_liquido <= 0`, excluído via `HAVING`).
6. **`LIMIT 500` por execução, separado para PIX e para cartão.** Se o backlog elegível for maior que 500, sobra para a próxima rodada (a ordenação é `ORDER BY id ASC`, então processa sempre os mais antigos primeiro — determinístico e estável entre execuções).
7. **Cartão**: só produtos com `nfe_config_id` apontando pro tenant em questão, pedido pago (`estado_id=1000`), cobrança aprovada na Cielo (`status_cielo=2`).
8. **Pagador com CNPJ (14 dígitos) não emite NF-e** — decisão do contador (14/09/2026). A SEFAZ rejeita (`cStat=232`, "IE do destinatário não informada") tanto `indIEDest=9` quanto `=2` sem uma IE real, que não coletamos no checkout (é venda B2C via PIX/cartão, não B2B). Em vez de tentar e ser rejeitado, esses pagamentos ficam de fora da seleção de elegíveis desde a origem (`buscar_pagamentos_pix_sem_nfe`/`buscar_pagamentos_cartao_sem_nfe`) — nunca geram tentativa nem número de NF-e.
9. **Cancelamento de NF-e não é uma ferramenta viável pro fluxo normal.** O prazo legal de cancelamento (evento 110111) no DF/SVRS é de **24 horas** após a autorização. Como a nota só é emitida no mínimo 2 dias depois do pagamento, qualquer cancelamento estaria sempre fora do prazo. Devoluções pós-emissão são tratadas só financeiramente (tabela `devolucoes_pix`), sem tocar a NF-e.

---

## Interpretação de `cStat` (autorizado vs rejeitado)

**`cStat=100` e `cStat=150` são AMBOS autorização válida**, com protocolo real (`nProt`) — `_C_STAT_AUTORIZADOS = {'100', '150'}` em `app/fiscal/nfe_service.py`. `cStat=150` ("Autorizado o uso da NF-e, autorização fora do prazo regulamentar") indica que o `dhEmi` (data do pagamento, usada como data de emissão) está fora do prazo regulamentar de transmissão — **confirmado empiricamente em 14/09/2026 (produção): o prazo é de 7 dias**. Pagamento com até 7 dias de idade na hora da transmissão sai `cStat=100`; com 8 dias ou mais sai `cStat=150` (ainda autorizado, só com esse aviso). Não é problema com os dados enviados. Qualquer outro `cStat` é rejeição de fato.

> Isso reforça a importância de manter o backlog de emissão sob controle — se o atraso entre pagamento e emissão passar de 7 dias (por acúmulo de fila, rotina parada, etc.), as notas ainda saem, só que como "fora do prazo".

> Histórico: até 12/09/2026 o código só tratava `cStat==100` como autorizado; `150` caía no branch de rejeição sem gravar `n_prot`/`dh_recbto`/`xml_nfe_proc` (embora os dados estivessem disponíveis na resposta e recuperáveis via `nfe_log_comunicacao.soap_response`). Corrigido — ver `scripts/corrigir_nfe_fora_de_prazo_lbe.py` para o script de recuperação usado.

---

## Isolamento de Ambientes (Produção vs Desenvolvimento)

**Incidente de 10-13/09/2026** (referência para não repetir): o banco de **desenvolvimento** (neste Mac) tinha `nfe_configuracao.ambiente=1` (produção) para a LBE, com o certificado real, enquanto o BB Pay e o banco de dados dev são propositalmente isolados de produção. Um teste manual (`make emitir-nfe-agora`) rodado duas vezes seguidas nesse ambiente de dev emitiu **1002 NF-e reais e válidas** direto na SEFAZ de produção, para clientes reais — sem que o banco de **produção** soubesse. Quando a rotina de produção rodou pela primeira vez, colidiu (`cStat=539`, duplicidade de numeração) porque a SEFAZ já tinha essas notas.

**Regra daqui pra frente**: `nfe_configuracao.ambiente` em qualquer banco que não seja o de produção real deve **sempre ser `2` (homologação)**. Antes de rodar `make emitir-nfe-agora` ou qualquer teste manual da rotina de NF-e, confirmar:
```sql
SELECT tenant_slug, ambiente FROM nfe_configuracao;
```
Se algum tenant estiver com `ambiente=1` fora do servidor de produção, corrigir antes de continuar.

A recuperação desse incidente (reconciliar as 1002 notas reais no banco de produção usando o dev como fonte da verdade) está em `scripts/backfill_nfe_lbe_producao.py`.

---

## Arquitetura

```
vendas-web/
├── app/
│   ├── fiscal/
│   │   ├── certificado.py           # carrega .pfx → PEM (mTLS + assinatura)
│   │   ├── nfe_chave.py             # gera chave de acesso 44 dígitos (cNF via secrets.randbelow)
│   │   ├── nfe_xml_builder.py       # monta XML infNFe 4.00 com nfelib (PIX e cartão)
│   │   ├── nfe_assinador.py         # assina XML (RSA-SHA1, enveloped, C14N 1.0)
│   │   ├── nfe_validador.py         # valida XML contra XSD oficial (nfelib)
│   │   ├── nfe_soap.py              # cliente SOAP raw (requests + mTLS) + parser de retorno
│   │   └── nfe_service.py           # orquestradores emitir_nfe / emitir_nfe_cartao
│   ├── database.py                  # funções NF-e: config, seleção de elegíveis, CRUD nfe_emitidas
│   ├── tasks.py                     # emitir_nfe, emitir_nfe_cartao, emitir_nfe_diaria_lbe
│   ├── celery_app.py                # beat schedule (00h10 SP) + task routes NF-e
│   └── fluxos/
│       └── fluxo_pix_bb.py          # emissão automática por-PIX-imediato: DESABILITADA (comentada)
├── migrations/
│   ├── 039_nfe.sql                  # schema base: nfe_configuracao, nfe_emitidas, nfe_log_comunicacao
│   ├── 048_nfe_configuracao_parametros.sql  # c_benef, aliq_icms_deson, IBS/CBS (Reforma Tributária)
│   ├── 049_produtos_nfe_config_id.sql       # liga produto → tenant emissor
│   ├── 069_nfe_emitidas_cartao.sql          # suporte a NF-e de pagamento por cartão
│   ├── 070_pagamento_pix_tenant_slug.sql    # tenant_slug em pagamento_pix (multi-conta BB)
│   └── 072_nfe_execucoes.sql                # relatório consolidado de cada rodada da rotina
├── scripts/
│   ├── testar_certificado_nfe.py    # teste: carrega .pfx
│   ├── testar_status_svrs.py        # teste: ping SVRS (cStat=107)
│   ├── testar_emissao_nfe.py        # teste: fluxo completo sem banco (CNPJ pessoal, homologação)
│   ├── emitir_nfe_pix.py            # emite em homologação p/ um pagamento_pix real (não grava no banco)
│   ├── backfill_nfe_lbe_producao.py # recuperação do incidente de 09/2026 (ver histórico acima)
│   └── corrigir_nfe_fora_de_prazo_lbe.py  # recupera notas com cStat=150 mal classificadas
├── Makefile                          # target `emitir-nfe-agora` (chama a task diretamente, sem esperar o beat)
└── docker-compose.yml                 # NF_CERT_SENHA / NF_CERT_SENHA_LBE nos workers
```

---

## Banco de Dados

### `nfe_configuracao` — dados do emitente (multi-tenant, ver [Multi-tenant](#multi-tenant))

| Coluna | Descrição |
|---|---|
| `tenant_slug` | Identificador único, ex: `lbe-livros` |
| `cnpj` | 14 dígitos sem formatação |
| `ie` | Inscrição estadual |
| `crt` | Regime: `3` = Lucro Presumido |
| `certificado_path` / `certificado_senha_env` | Caminho do `.pfx` e **nome** da env var com a senha (nunca a senha em si) |
| `serie_padrao` | Série da NF-e, ex: `'001'` |
| `ultimo_numero_nfe` | Contador atual — incrementado com `SELECT FOR UPDATE`. **Compartilhado entre homologação e produção na mesma linha** — não há separação de contador por ambiente, só o endpoint SOAP muda |
| `ambiente` | `1` = produção, `2` = homologação — ver aviso de isolamento acima |
| `x_prod`, `ncm`, `cfop`, `cst_*`, `c_benef`, `aliq_icms_deson`, `mot_des_icms`, `cst_ibs_cbs`, `c_class_trib` | Tributação (livros: imunidade ICMS art. 150 VI-d + `cBenef=DF811004`; IBS/CBS Reforma Tributária CST=410) |
| `ca_bundle_path` | Path do CA ICP-Brasil para verify SSL em produção |

### `produtos.isbn` / `produtos.nome_nfe`

Descrição do produto na nota (`xProd`) usa `nome_nfe` (ou `nome` como fallback) + ISBN quando presente. Cascata em `montar_nfe()`: `pagamento.get('nome_nfe') or pagamento.get('x_prod') or config.get('x_prod') or 'Livro Digital'`. **Para isso funcionar a query que busca o pagamento precisa fazer `LEFT JOIN produtos`** — `buscar_pagamento_pix_por_id` sempre fez; `buscar_pagamento_cartao_por_id` não fazia (bug corrigido em 13/09/2026, notas de cartão saíam com descrição genérica sem ISBN).

### `nfe_emitidas` — histórico de NF-e (PIX e cartão)

| Coluna | Descrição |
|---|---|
| `pagamento_pix_id` | UNIQUE, nullable — preenchido para NF-e de PIX |
| `pagamento_cartao_id` | UNIQUE (`uq_nfe_cartao`), nullable — preenchido para NF-e de cartão. **Um pagamento_cartao só pode ter UMA linha aqui, para sempre** — mesmo uma linha `rejeitada`/`erro` bloqueia um novo INSERT pra esse mesmo cartão (constraint UNIQUE, não filtra por status). Pra reprocessar um cartão travado assim: `UPDATE ... SET pagamento_cartao_id = NULL` na linha antiga (não dá pra simplesmente mudar o status). |
| `chave_acesso` | 44 dígitos, UNIQUE |
| `numero` / `serie` | Não são únicos por constraint no banco — a unicidade real é garantida pela SEFAZ (rejeita duplicata com `cStat=539`) |
| `status_emissao` | `pendente` → `enviando` → `autorizada` / `rejeitada` / `erro` |
| `c_stat` / `x_motivo` | Retorno da SEFAZ — ver [Interpretação de cStat](#interpretação-de-cstat-autorizado-vs-rejeitado) |
| `n_prot` / `dh_recbto` | Protocolo e data/hora de autorização |
| `xml_assinado` | XML da NF-e assinado, gravado **antes** de enviar (sobrevive mesmo se a chamada à SEFAZ falhar) |
| `xml_nfe_proc` | `<nfeProc>` = NFe + protNFe — usado pelo DANFE (`/admin/fiscal/nfe/<id>/danfe`, gera o PDF on-demand) |
| `tentativas` / `ultimo_erro` | Diagnóstico |

### `nfe_log_comunicacao` — log SOAP completo

Guarda `soap_request`/`soap_response` de cada chamada. **Fonte de recuperação**: se uma nota foi mal classificada localmente mas a SEFAZ já tinha respondido, os dados completos (incluindo `nProt`) ainda estão aqui e são reparseáveis com `fiscal.nfe_soap._parsear_ret_envi_nfe` (foi assim que o incidente do `cStat=150` foi corrigido sem perder nada).

### `nfe_execucoes` — relatório de cada rodada da rotina diária (migration 072)

Uma linha por execução de `tasks.emitir_nfe_diaria_lbe`: elegíveis vs. disparados (PIX e cartão,
separado), se bateu no `LIMIT 500`, contagem de autorizadas (100 vs 150), rejeitadas, erros, já
emitidas, valor total autorizado, último número da rodada, e um `detalhe_rejeicoes_json` com
motivo de cada rejeição/erro. Preenchida em duas etapas: `criar_execucao_nfe()` no início
(`status='em_andamento'`) e `finalizar_execucao_nfe()` no callback do chord, quando todas as
emissões da rodada já terminaram de verdade. Consultável em `/admin/fiscal/nfe/execucoes`.

### Vínculo com `pagamento_pix`

`pagamento_pix.nfe_emitida_id` — `NULL` = pendente, preenchido = autorizada. Idempotência: a seleção de elegíveis já filtra por isso.

---

## Fluxo de Emissão (rotina diária, LBE)

```
Celery beat, todo dia às 00h10 SP (crontab(hour=0, minute=10) — CUIDADO: quando
celery_app.conf.timezone está setado, o Beat interpreta o crontab DIRETO nesse
fuso, sem conversão de UTC; não somar/subtrair fuso manualmente no crontab)
  └─▶ tasks.emitir_nfe_diaria_lbe   [queue: normal — unificado em 13/09/2026,
      antes rodava em 'baixa' separado das emissões individuais, dificultando achar log]
        ├─ buscar_pagamentos_pix_sem_nfe(tenant='lbe-livros', dias_minimos=2,
        │      valor_minimo=2.0, limite=500)
        ├─ buscar_pagamentos_cartao_sem_nfe(config_id=2, dias_minimos=2,
        │      valor_minimo=2.0, limite=500)
        ├─ criar_execucao_nfe() — grava início da rodada em nfe_execucoes
        ├─ monta um celery.group() com uma signature emitir_nfe.s(...)/emitir_nfe_cartao.s(...)
        │      por elegível (tudo [queue: normal])
        └─ chord(group)(finalizar_execucao_nfe_diaria.s(execucao_id)) — dispara o grupo e
               encadeia o fechamento do relatório pra depois que TODAS terminarem

emitir_nfe / emitir_nfe_cartao  (app/fiscal/nfe_service.py)
  1. busca nfe_configuracao pelo config_id
  2. busca o pagamento (idempotência: nfe_emitida_id/pagamento_cartao_id já linkado? retorna sem reemitir)
  3. valida env var da senha + existência do certificado (falha rápido, antes de reservar número)
  4. incrementar_numero_nfe() — SELECT FOR UPDATE, commita imediatamente (número nunca reusado)
  5. gerar_chave() — 44 dígitos, cNF aleatório (secrets.randbelow), cDV módulo 11
  6. [dentro de certificado_temp]
     ├─ montar_nfe() — nfelib dataclasses → lxml namespace fix
     ├─ assinar_nfe() — RSA-SHA1, enveloped, C14N 1.0
     ├─ validar_nfe() — XSD nfe_v4.00.xsd (falha ANTES de gastar número)
     ├─ criar_nfe_pendente() / inserir_nfe_emitida_cartao() → status='enviando'
     └─ enviar_autorizacao() — SOAP indSinc=1
  7. processar retorno (_processar_retorno / _processar_retorno_cartao):
     ├─ cStat=104 + prot em {100,150} → autorizada: salva nfeProc, vincula pagamento
     ├─ cStat=104 + prot fora disso   → rejeitada: salva cStat+xMotivo (SEM nProt/xml_proc)
     ├─ cStat=103                    → aguardando_retorno (assíncrono raro)
     └─ outros                       → rejeitada
  8. gravar_log_soap() — sempre, mesmo em erro
  9. retorna um dict {status, nfe_id, c_stat, x_motivo} — SEMPRE, mesmo em erro
     permanente ou após esgotar retries (nunca deixa exceção escapar da task,
     senão o chord acima trava e o relatório não fecha)

finalizar_execucao_nfe_diaria(resultados, execucao_id)  [queue: normal]
  └─▶ agrega os resultados (contagem por status/cStat, soma valor autorizado via
      join com pagamento_pix/pagamento_cartao) e fecha a linha em nfe_execucoes
      — ver /admin/fiscal/nfe/execucoes
```

**Relatório de cada rodada**: `/admin/fiscal/nfe/execucoes` — elegíveis vs. disparados, autorizadas
(cStat 100 vs 150), rejeitadas, erros, valor total autorizado, se bateu no limite de 500. Não
substitui os logs de warning/error (que continuam existindo linha a linha) — é a visão consolidada
"o que essa rodada fez", sem precisar vasculhar log ou banco na mão.

**Disparo manual** (fora do horário agendado, mesmo código): `make emitir-nfe-agora` → `docker compose exec worker-normal celery -A celery_app call tasks.emitir_nfe_diaria_lbe --queue normal`. O disparo em si só enfileira o grupo — o resultado real leva o tempo de processar todos os itens; acompanhar pela tela de execuções ou via banco (`SELECT status_emissao, c_stat, COUNT(*) ... GROUP BY`) é mais confiável que log, porque os workers rodam com `--loglevel=warning` (`docker-compose.yml`) e `logger.info(...)` (autorizada) não aparece no `docker logs`, só no arquivo `/app/storage/logs/log_worker_normal_<data>_001.log` (nível INFO, configurado em `app/logging_setup.py` via `LOG_LEVEL`).

> `app/fluxos/fluxo_pix_bb.py` tem um bloco de emissão **imediata** por-PIX (logo após buscar da API do BB) — está **comentado**, desabilitado deliberadamente. Comentar o `beat_schedule` só impede o disparo automático/agendado; não impede um disparo manual via `make emitir-nfe-agora`, que chama a task direto via Celery.

---

## Certificado Digital A1

Um `.pfx` (PKCS#12) por tenant, montado read-only via volume Docker. Senha nunca em código/log/git — só o **nome** da env var fica no banco (`certificado_senha_env`), o valor vem do `.env` do servidor:

```
.env (não sobe pro git)
  NF_CERT_SENHA_LBE=suasenha

nfe_configuracao (banco)
  certificado_senha_env = 'NF_CERT_SENHA_LBE'

nfe_service.py (em runtime)
  senha = os.getenv(config['certificado_senha_env'])
```

---

## Assinatura Digital

`signxml 5.0` com subclasse para contornar o bloqueio de SHA1 (exigido pelo MOC NF-e 4.00):

| Parâmetro | Valor | Motivo |
|---|---|---|
| Algoritmo de assinatura | RSA-SHA1 | Exigência MOC NF-e 4.00 |
| Algoritmo de digest | SHA-1 | Exigência MOC NF-e 4.00 |
| Canonicalização | C14N 1.0 | Exigência MOC NF-e 4.00 |
| Método | Enveloped | `<Signature>` irmã de `<infNFe>` dentro de `<NFe>` |

### Problema de namespace resolvido

`nfelib` (xsdata) serializa com prefixo (`<ns0:infNFe xmlns:ns0="...">`); a SEFAZ exige sem prefixo (`<NFe xmlns="..."><infNFe>`). Solução em `nfe_xml_builder.py`: serializar com xsdata, extrair `infNFe` com lxml, remontar `<NFe>` com `nsmap={None: NS}`.

---

## Endpoints SVRS

| Operação | Homologação | Produção |
|---|---|---|
| Status do serviço | `nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/...` | `nfe.svrs.rs.gov.br/ws/NfeStatusServico/...` |
| Autorização | `nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/...` | `nfe.svrs.rs.gov.br/ws/NfeAutorizacao/...` |
| Ret. autorização | `nfe-homologacao.svrs.rs.gov.br/ws/NfeRetAutorizacao/...` | `nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/...` |
| Consulta | `nfe-homologacao.svrs.rs.gov.br/ws/NfeConsulta/...` | `nfe.svrs.rs.gov.br/ws/NfeConsulta/...` |
| Eventos (cancelamento/CCe) | `nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/...` | `nfe.svrs.rs.gov.br/ws/recepcaoevento/...` |
| Inutilização | `nfe-homologacao.svrs.rs.gov.br/ws/NfeInutilizacao/...` | `nfe.svrs.rs.gov.br/ws/NfeInutilizacao/...` |

Seleção automática via `nfe_configuracao.ambiente` (`app/fiscal/nfe_soap.py:84-85`). **Eventos (cancelamento/CCe) e Inutilização têm as URLs mapeadas mas nenhuma função implementada ainda** — ver [Próximas Etapas](#próximas-etapas).

**Consulta pública de NF-e** (`nfe.fazenda.gov.br` e o portal da Receita-DF) só aceita busca pela chave de acesso completa de 44 dígitos — não existe busca por CNPJ+número+série sem certificado digital nesses portais públicos. Pra descobrir se um número específico já foi usado sem ter a chave, a única forma correta seria implementar o webservice `NFeDistribuicaoDFe` (Distribuição de DFe) — não existe no código hoje.

---

## Dados do Destinatário (B2C)

- **CPF/CNPJ**: `pagamento_pix.cpf_cnpj` ou `pedidos.cpf_cnpj_pagador` (cartão)
- **Nome**: uppercase forçado em `montar_nfe()` (PIX já vem em caixa alta da fonte/banco; cartão vem como o cliente digitou no checkout — padronizado desde 13/09/2026). Em homologação, `xNome` é sobrescrito pela string fixa exigida pela SEFAZ (`cStat=598` se diferente)
- **indIEDest**: `9` = Não contribuinte

---

## Idempotência e Concorrência

1. **`pagamento_pix.nfe_emitida_id`** / **`nfe_emitidas.pagamento_cartao_id` (UNIQUE)**: checado antes de tentar emitir
2. **`IntegrityError` capturado** no service se dois workers tentarem o mesmo pagamento ao mesmo tempo
3. **`incrementar_numero_nfe` com `FOR UPDATE`**: número nunca gerado duas vezes — mas **só protege dentro do mesmo banco**. Dois bancos diferentes (ex: dev com `ambiente=1` e produção) compartilhando a mesma SEFAZ real **não têm proteção nenhuma entre si** — cada um tem seu próprio contador, cego ao do outro. Isso é o que causou o incidente de 09/2026 (ver [Isolamento de Ambientes](#isolamento-de-ambientes-produção-vs-desenvolvimento)).

---

## Tasks Celery

| Task | Fila | Retries | Descrição |
|---|---|---|---|
| `tasks.emitir_nfe_diaria_lbe` | normal | 0 | Orquestrador diário (beat 00h10 SP) — busca elegíveis e dispara um `chord` com as duas abaixo |
| `tasks.emitir_nfe` | normal | 3 (60s→120s→240s) | Emissão individual, PIX — sempre retorna um dict, nunca deixa exceção escapar (chord-safe) |
| `tasks.emitir_nfe_cartao` | normal | 3 (60s→120s→240s) | Emissão individual, cartão — mesma garantia de retorno |
| `tasks.finalizar_execucao_nfe_diaria` | normal | 0 | Callback do chord — fecha o relatório em `nfe_execucoes` depois que todas as emissões da rodada terminam |

**Erros permanentes** (não retentam, notificam admin): `RuntimeError` (config/senha ausente), `ValueError` (XSD inválido, pagamento não encontrado).
**Erros transientes** (retentam com backoff): timeout de rede, HTTP 5xx, SEFAZ indisponível.

---

## Scripts

```bash
# Testes de infraestrutura (certificado, conectividade) — CNPJ pessoal, homologação
NF_CERT_SENHA="suasenha" python scripts/testar_certificado_nfe.py
NF_CERT_SENHA="suasenha" python scripts/testar_status_svrs.py
NF_CERT_SENHA="suasenha" python scripts/testar_emissao_nfe.py

# Emite em HOMOLOGAÇÃO pra um pagamento_pix real da LBE, sem gravar no banco
# (gera XMLs + DANFE em testes-nfe/pix-<ID>/, útil pra mandar exemplo pro contador)
DB_HOST=localhost NF_CERT_PATH=/tmp/lbe-livros.pfx python scripts/emitir_nfe_pix.py [PIX_ID]

# Disparo manual da rotina diária, produção — MESMO código do beat, ver aviso de ambiente acima
make emitir-nfe-agora
```

Scripts standalone rodam **fora do Docker** (no host do servidor) — usam o `.venv` próprio em `~/vendas-web/.venv` (dependências do `requirements.txt` também precisam estar instaladas ali, fora do container). `DB_HOST=db` (nome do serviço Docker) não resolve fora da rede Docker — os scripts corrigem automaticamente para `localhost`.

---

## Estado Atual (13/09/2026)

- ✅ LBE em produção real (`ambiente=1`), rotina diária ativa, ~2400 NF-e emitidas
- ✅ PIX e cartão funcionando, `cStat=100` e `150` tratados corretamente como autorização
- ✅ Descrição de produto (ISBN/nome_nfe) correta em ambas as vias de pagamento
- ✅ Janela de elegibilidade em 2 dias (reduzida de 7); fila unificada em `normal`; relatório de
  cada rodada em `/admin/fiscal/nfe/execucoes` (chord — só fecha depois que tudo termina de verdade)
- ⚠️ LSN (CNPJ pessoal) ainda em homologação (`ambiente=2`) — sem rotina automática ativa
- ⚠️ IBS/CBS (Reforma Tributária) configurado com valores confirmados pelo contador em setembro/2026, mas a legislação/alíquotas ainda estão em transição — revisar periodicamente

---

## Próximas Etapas

| Etapa | Descrição |
|---|---|
| Admin UI | Listar NF-e emitidas, detalhes, download XML, retentar manualmente |
| Inutilização de numeração | Formalizar (evento de Inutilização) qualquer gap de número que fique definitivamente sem uso — hoje não há gaps conhecidos, mas o mecanismo não existe se precisar |
| CCe (Carta de Correção) | Só serve para dados não-fiscais (endereço, informações complementares) — não resolve numeração nem valor. Não implementado; baixa prioridade dado o volume de erros desse tipo até hoje |
| Consulta de Distribuição de DFe | Permitiria descobrir programaticamente que números já existem pra um CNPJ/série sem precisar de chave — teria evitado horas de investigação no incidente de 09/2026. Não implementado |
| Trava de segurança ambiente | Considerar um guard no código que impeça `ambiente=1` fora do hostname de produção real, pra tornar o incidente de isolamento estruturalmente impossível em vez de depender de disciplina manual |
| API REST | `/api/fiscal/` com Bearer token para uso multi-tenant externo |
