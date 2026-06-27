# Integração NF-e Modelo 55 — SVRS/DF

Módulo de emissão de Nota Fiscal Eletrônica (NF-e) Modelo 55 integrado ao sistema `vendas-web`. Emite automaticamente uma NF-e para cada pagamento PIX recebido, sem intervenção manual.

---

## Contexto

| Item | Detalhe |
|---|---|
| Empresa | LEONARDO SANTOS NEGREIROS — CNPJ 64.980.953/0001-46 |
| Regime tributário | Lucro Presumido (CRT=3), ex-MEI |
| UF emitente | DF (cUF=53) |
| Autoridade SEFAZ | SVRS — SEFAZ Virtual do Rio Grande do Sul |
| Modelo | NF-e 55 (produto/mercadoria) |
| Volume estimado | ~10.000 NF-e/mês |
| Certificado | A1 (.pfx), emitido após conversão MEI→PE |

> **Por que NF-e e não NFS-e?** Livros digitais são classificados como mercadoria (NCM 49011000) pela Receita Federal — NF-e modelo 55, não NFS-e municipal. Confirmar NCM/CFOP final com o contador.

> **Por que DIY e não SaaS?** 10.000 NF-e/mês × R$0,25 = R$2.500/mês. O desenvolvimento se paga em menos de 2 meses.

---

## Arquitetura

```
vendas-web/
├── app/
│   ├── fiscal/                      ← módulo fiscal (novo)
│   │   ├── __init__.py
│   │   ├── certificado.py           # carrega .pfx → PEM (mTLS + assinatura)
│   │   ├── nfe_chave.py             # gera chave de acesso 44 dígitos
│   │   ├── nfe_xml_builder.py       # monta XML infNFe 4.00 com nfelib
│   │   ├── nfe_assinador.py         # assina XML (RSA-SHA1, enveloped, C14N 1.0)
│   │   ├── nfe_validador.py         # valida XML contra XSD oficial (nfelib)
│   │   ├── nfe_soap.py              # cliente SOAP raw (requests + mTLS)
│   │   └── nfe_service.py           # orquestrador: une tudo e fala com o banco
│   ├── database.py                  # +11 funções NF-e adicionadas
│   ├── tasks.py                     # +2 tasks Celery (emitir_nfe, reprocessar_nfe_pendentes)
│   ├── celery_app.py                # +beat schedule + task routes NF-e
│   └── fluxos/
│       └── fluxo_pix_bb.py          # dispara emitir_nfe para cada PIX novo
├── migrations/
│   └── 039_nfe.sql                  # schema: nfe_configuracao, nfe_emitidas, nfe_log_comunicacao
├── scripts/
│   ├── testar_certificado_nfe.py    # teste: carrega .pfx
│   ├── testar_status_svrs.py        # teste: ping SVRS (cStat=107)
│   └── testar_emissao_nfe.py        # teste: fluxo completo sem banco
└── docker-compose.yml               # +NF_CERT_SENHA no worker-normal
```

---

## Banco de Dados

### `nfe_configuracao` — dados do emitente (multi-tenant)

Cada linha representa uma empresa emitente. Hoje há apenas uma (a própria empresa).

| Coluna | Descrição |
|---|---|
| `tenant_slug` | Identificador único, ex: `lsn-livros` |
| `api_key` | Chave SHA-256 para uso futuro da API REST |
| `cnpj` | 14 dígitos sem formatação |
| `ie` | Inscrição estadual (obrigatória para produção) |
| `crt` | Regime: `3` = Lucro Presumido |
| `certificado_path` | Caminho absoluto do .pfx dentro do container |
| `certificado_senha_env` | **Nome** da variável de ambiente que contém a senha (nunca a senha em si) |
| `serie_padrao` | Série da NF-e, ex: `'001'` |
| `ultimo_numero_nfe` | Contador atual — incrementado com `SELECT FOR UPDATE` |
| `ambiente` | `1` = produção, `2` = homologação |
| `x_prod` | Descrição padrão do produto na NF-e |
| `ncm`, `cfop`, `cst_*` | Tributação — definir com contador |
| `ca_bundle_path` | Path do CA ICP-Brasil para verify SSL em produção |

### `nfe_emitidas` — histórico de NF-e

| Coluna | Descrição |
|---|---|
| `pagamento_pix_id` | Âncora fiscal: UNIQUE, garante 1 NF-e por PIX |
| `chave_acesso` | 44 dígitos, UNIQUE |
| `status_emissao` | `pendente` → `enviando` → `autorizada` / `rejeitada` / `erro` |
| `c_stat` / `x_motivo` | Retorno da SEFAZ |
| `n_prot` | Número do protocolo de autorização |
| `xml_assinado` | XML da NF-e com assinatura digital |
| `xml_nfe_proc` | XML `<nfeProc>` = NFe + protNFe (para DANFE e consulta) |
| `tentativas` | Contador de tentativas de emissão |
| `ultimo_erro` | Mensagem do último erro (para diagnóstico) |

### `nfe_log_comunicacao` — log SOAP

Registra cada chamada à SEFAZ com request/response completos, duração e status HTTP. Útil para diagnosticar rejeições.

### Vínculo com `pagamento_pix`

```sql
ALTER TABLE pagamento_pix ADD COLUMN nfe_emitida_id INT NULL;
```

- `NULL` → NF-e ainda não emitida (ou rejeitada permanentemente)
- `NOT NULL` → NF-e autorizada; valor = `nfe_emitidas.id`

Este campo serve como **idempotência**: a task verifica se já está preenchido antes de tentar emitir.

---

## Fluxo de Emissão

```
Celery beat (a cada hora)
  └─▶ processar_pagamentos_pix
        └─▶ fluxo_pix_bb.executar()
              ├─ consulta PIX recebidos no BB
              ├─ salvar_pagamento_pix() → retorna pagamento_pix_id (novo) ou None (duplicata)
              └─ para cada PIX novo:
                   send_task('tasks.emitir_nfe', [pix_id], countdown=5s)

tasks.emitir_nfe  [queue: normal, max_retries=3, backoff: 60s→120s→240s]
  └─▶ fiscal.nfe_service.emitir_nfe(pagamento_pix_id)
        1. busca nfe_configuracao (tenant ativo)
        2. busca pagamento_pix por id
        3. checa idempotência: nfe_emitida_id preenchido? → retorna sem reemitir
        4. valida env var da senha (falha rápido antes de reservar número)
        5. incrementar_numero_nfe() — SELECT FOR UPDATE, commita imediatamente
        6. gerar_chave() — 44 dígitos, cDV módulo 11
        7. [dentro de certificado_temp]
           ├─ montar_nfe() — nfelib dataclasses → lxml namespace fix
           ├─ assinar_nfe() — RSA-SHA1, enveloped, C14N 1.0
           ├─ validar_nfe() — XSD nfe_v4.00.xsd (falha ANTES de gastar número)
           ├─ criar_nfe_pendente() → status='enviando'
           └─ enviar_autorizacao() — SOAP indSinc=1
        8. processar retorno:
           ├─ cStat=104 + prot=100 → autorizada: salva nfeProc, vincula PIX
           ├─ cStat=104 + prot≠100 → rejeitada: salva cStat+xMotivo
           ├─ cStat=103 → aguardando: salva nRec (assíncrono raro)
           └─ outros → rejeitada
        9. gravar_log_soap()

Celery beat (a cada 30 min)
  └─▶ reprocessar_nfe_pendentes
        └─ busca PIX das últimas 24h sem NF-e (status=erro ou sem tentativa)
        └─ despacha emitir_nfe para cada um
```

---

## Certificado Digital A1

O certificado `.pfx` (PKCS#12) fica em `infra/nginx/certs/` e é montado read-only nos containers via volume Docker:

```yaml
volumes:
  - ./infra/nginx/certs:/app/certs:ro
```

**Segurança da senha:**

```
.env (não sobe pro git)
  NF_CERT_SENHA=suasenhaaqui

docker-compose.yml (sobe pro git — sem valor)
  - NF_CERT_SENHA=${NF_CERT_SENHA:-}

nfe_configuracao (banco de dados)
  certificado_senha_env = 'NF_CERT_SENHA'   ← nome da variável, nunca a senha

nfe_service.py (em runtime)
  senha = os.getenv(config['certificado_senha_env'])   ← lê do ambiente
```

A senha **nunca aparece** em código, log, banco ou git.

---

## Assinatura Digital

O módulo usa `signxml 5.0` com subclasse para contornar o bloqueio de SHA1 (exigido pelo MOC NF-e 4.00):

| Parâmetro | Valor | Motivo |
|---|---|---|
| Algoritmo de assinatura | RSA-SHA1 | Exigência MOC NF-e 4.00 |
| Algoritmo de digest | SHA-1 | Exigência MOC NF-e 4.00 |
| Canonicalização | C14N 1.0 | Exigência MOC NF-e 4.00 |
| Método | Enveloped | `<Signature>` irmã de `<infNFe>` dentro de `<NFe>` |

> SHA-1 é considerado depreciado para segurança geral, mas é obrigatório para NF-e por exigência do governo federal. A subclasse `_NFeSigner` em `nfe_assinador.py` faz esse bypass de forma controlada.

### Problema de namespace resolvido

O `nfelib` (xsdata) serializa como:
```xml
<TNFe><ns0:infNFe xmlns:ns0="http://www.portalfiscal.inf.br/nfe">
```

A SEFAZ exige:
```xml
<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe ...>
```

Solução em `nfe_xml_builder.py`: serializar com xsdata, extrair `infNFe` com lxml, criar `<NFe>` com `nsmap={None: NS}`.

---

## Endpoints SVRS

| Operação | Homologação | Produção |
|---|---|---|
| Status do serviço | `nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/...` | `nfe.svrs.rs.gov.br/ws/NfeStatusServico/...` |
| Autorização | `nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/...` | `nfe.svrs.rs.gov.br/ws/NfeAutorizacao/...` |
| Ret. autorização | `nfe-homologacao.svrs.rs.gov.br/ws/NfeRetAutorizacao/...` | `nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/...` |
| Consulta | `nfe-homologacao.svrs.rs.gov.br/ws/NfeConsulta/...` | `nfe.svrs.rs.gov.br/ws/NfeConsulta/...` |
| Eventos | `nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/...` | `nfe.svrs.rs.gov.br/ws/recepcaoevento/...` |

A seleção é automática via campo `nfe_configuracao.ambiente` (`1`=produção, `2`=homologação).

---

## Tributação (Placeholders — Validar com Contador)

Enquanto o contador não define a tributação definitiva, o sistema usa valores conservadores:

| Imposto | Código | Significado |
|---|---|---|
| ICMS | CST=40 | Isenção |
| PIS | CST=07 | Operação isenta |
| COFINS | CST=07 | Operação isenta |
| NCM | 49011000 | Livros (provisório) |
| CFOP | 6107 | Venda interestadual a não-contribuinte (provisório) |

Esses campos ficam em `nfe_configuracao` e podem ser atualizados no banco sem alterar código.

**Atenção:** Para livros digitais no DF, a classificação correta (NF-e produto vs NFS-e serviço, NCM, CFOP, alíquotas DIFAL) precisa ser confirmada com o contador e com a SEFAZ-DF.

---

## Dados do Destinatário (B2C)

Para venda a consumidor final via PIX, a NF-e usa:

- **CPF/CNPJ**: extraído de `pagamento_pix.cpf_cnpj` (quando disponível; campo opcional para B2C)
- **Nome**: `pagamento_pix.nome_pagador` (produção) / string fixa em homologação (exigência SEFAZ: `cStat=598` se diferente)
- **Endereço**: endereço do emitente como fallback B2C (sem entrega física — produto digital)
- **indIEDest**: `9` = Não contribuinte

---

## Idempotência e Concorrência

Três camadas de proteção contra emissão dupla:

1. **`pagamento_pix.nfe_emitida_id`**: checado no início do service; se preenchido, retorna imediatamente
2. **`UNIQUE KEY uq_pagamento_pix (pagamento_pix_id)`** em `nfe_emitidas`: `IntegrityError` capturado no service
3. **`incrementar_numero_nfe` com `FOR UPDATE`**: o número nunca é gerado duas vezes para o mesmo PIX

---

## Tasks Celery

| Task | Fila | Retries | Descrição |
|---|---|---|---|
| `tasks.emitir_nfe` | normal | 3 (60s→120s→240s) | Emissão individual para um PIX |
| `tasks.reprocessar_nfe_pendentes` | baixa | 0 | Beat a cada 30min; recupera falhas das últimas 24h |

**Erros permanentes** (não retentam, notificam admin):
- `RuntimeError` — configuração ausente, senha não definida
- `ValueError` — XSD inválido, PIX não encontrado

**Erros transientes** (retentam com backoff):
- Timeout de rede, HTTP 5xx, SEFAZ indisponível

---

## Scripts de Teste

Execute a partir da raiz do projeto:

```bash
# 1. Testa carregamento do certificado .pfx
NF_CERT_SENHA="suasenha" python scripts/testar_certificado_nfe.py

# 2. Testa conectividade com SVRS (deve retornar cStat=107)
NF_CERT_SENHA="suasenha" python scripts/testar_status_svrs.py

# 3. Testa o fluxo completo de emissão sem banco de dados
NF_CERT_SENHA="suasenha" python scripts/testar_emissao_nfe.py

# 4. Ver o XML SOAP de resposta da SEFAZ
NF_CERT_SENHA="suasenha" DEBUG_SOAP=1 python scripts/testar_emissao_nfe.py
```

---

## Resultados dos Testes Confirmados

| Teste | Resultado |
|---|---|
| Carregamento do .pfx | ✅ |
| Consulta de status SVRS | ✅ cStat=107, HTTP 200, 224ms |
| Geração de chave 44 dígitos | ✅ cDV correto |
| Montagem de XML com nfelib | ✅ namespace correto |
| Assinatura RSA-SHA1 | ✅ 6.2 KB, verificada |
| Validação XSD nfe_v4.00.xsd | ✅ 0 erros |
| Envio SOAP SVRS | ✅ HTTP 200, 247ms |
| Lote processado (cStat=104) | ✅ |
| Autorização (cStat=100) | ⏳ aguarda IE do DF |

**Rejeições encontradas e corrigidas durante os testes:**

| cStat | Motivo | Correção |
|---|---|---|
| 598 | xNome dest diferente do obrigatório em homologação | `xNome` fixo em homologação |
| 434 | `indIntermed` ausente (NT 2020.006) | Adicionado `indIntermed=0` |
| 209 | IE do emitente inválida | Aguarda IE do DF; campo `config['ie']` já pronto |

---

## Checklist para Produção

- [ ] **Obter IE do DF** junto à SEFAZ-DF após abertura da PE
- [ ] **Confirmar com contador**: NCM, CFOP, CST corretos para livros digitais
- [ ] **Baixar CA bundle ICP-Brasil** (cadeia de certificação SEFAZ):
  ```bash
  # Salvar em infra/nginx/certs/cadeia-icp-brasil.pem
  ```
- [ ] **Rodar migration**:
  ```bash
  mysql -u appuser -p vendasdb < migrations/039_nfe.sql
  ```
- [ ] **Inserir configuração no banco**:
  ```sql
  INSERT INTO nfe_configuracao (
    tenant_slug, api_key, cnpj, ie, crt,
    razao_social, nome_fantasia,
    logradouro, numero, bairro, c_mun, x_mun, uf, cep,
    serie_padrao, certificado_path, certificado_senha_env,
    x_prod, ncm, cfop, cst_icms, cst_pis, cst_cofins,
    ambiente, ca_bundle_path
  ) VALUES (
    'lsn-livros',
    SHA2(UUID(), 256),
    '64980953000146',
    '<IE_DF>',             -- inserir quando obtida
    3,
    'LEONARDO SANTOS NEGREIROS',
    'LSN LIVROS',
    'SHA Conjunto 4 Chacara 19 Lote C', '5', 'Arniqueira',
    5300108, 'Brasilia', 'DF', '71994120',
    '001',
    '/app/certs/64.980.953 LEONARDO SANTOS NEGREIROS_64980953000146.pfx',
    'NF_CERT_SENHA',
    'Livro Digital',
    '49011000',            -- confirmar NCM com contador
    '6107',               -- confirmar CFOP com contador
    '40',                 -- confirmar CST ICMS com contador
    '07',                 -- confirmar CST PIS com contador
    '07',                 -- confirmar CST COFINS com contador
    2,                    -- 2=homologação; trocar para 1 quando pronto para produção
    NULL                  -- NULL=homologação sem verify; '/app/certs/cadeia-icp-brasil.pem' em produção
  );
  ```
- [ ] **Adicionar senha ao `.env`** no servidor:
  ```
  NF_CERT_SENHA=suasenha
  ```
- [ ] **Fazer rebuild do docker-compose** para o worker-normal pegar a nova variável:
  ```bash
  docker compose up -d --build worker-normal
  ```
- [ ] **Testar em homologação** com `ambiente=2` até obter `cStat=100`
- [ ] **Trocar para produção**: `UPDATE nfe_configuracao SET ambiente=1, ca_bundle_path='/app/certs/cadeia-icp-brasil.pem' WHERE id=1`

---

## Dependências Adicionadas

```
nfelib==2.5.2      # dataclasses NF-e 4.00 geradas dos XSD oficiais
lxml==6.1.1        # parsing/serialização XML + fix de namespace
signxml==5.0.0     # assinatura XML enveloped (SHA1 via subclasse)
```

`cryptography` já era dependência transitiva do projeto.

---

## Próximas Etapas

| Etapa | Descrição |
|---|---|
| Admin UI | Listar NF-e emitidas, detalhes, download XML, retentar |
| Eventos | Cancelamento (110111), CCe (110110), Inutilização |
| API REST | `/api/fiscal/` com Bearer token para uso multi-tenant |
| `consultar_retorno_nfe` | Task para o caso raro de `cStat=103` (assíncrono) |
