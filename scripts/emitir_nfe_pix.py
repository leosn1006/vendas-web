"""
Emite NF-e em homologação para um pagamento_pix real, sem gravar no banco.

Gera 3 arquivos em testes-nfe/pix-<ID>/:
  nfe_assinada.xml  — XML de envio (assinado)
  nfe_proc.xml      — nfeProc com protocolo SEFAZ
  danfe.pdf         — DANFE para o contador

Uso:
  source .venv/bin/activate
  python scripts/emitir_nfe_pix.py [PIX_ID]   # default: 510855
"""
import os
import sys
import pathlib
from datetime import datetime

from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import buscar_pagamento_pix_por_id, buscar_nfe_configuracao_por_slug, db
from app.fiscal.certificado import carregar_pfx, certificado_temp
from app.fiscal.nfe_chave import gerar_chave
from app.fiscal.nfe_xml_builder import montar_nfe
from app.fiscal.nfe_assinador import assinar_nfe, verificar_assinatura
from app.fiscal.nfe_validador import validar_nfe
from app.fiscal.nfe_soap import enviar_autorizacao
from app.fiscal.nfe_service import _montar_nfe_proc

# ─── Parâmetros ──────────────────────────────────────────────────────────────

PIX_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 510855
SLUG   = 'lbe-livros'

# ─── Pipeline ────────────────────────────────────────────────────────────────

print('=' * 60)
print(f'EMISSÃO NF-e HOMOLOGAÇÃO — pagamento_pix id={PIX_ID}')
print('=' * 60)

# 1. Dados do PIX
print(f'\n[1/7] Lendo pagamento_pix id={PIX_ID}...')
pix = buscar_pagamento_pix_por_id(PIX_ID)
if not pix:
    print(f'      ERRO: pagamento_pix {PIX_ID} não encontrado.')
    sys.exit(1)
print(f'      Produto : {pix.get("x_prod")}')
print(f'      ISBN    : {pix.get("isbn") or "—"}')
print(f'      Valor   : R$ {pix.get("valor")}')
print(f'      CPF/CNPJ: {pix.get("cpf_cnpj")}')
print(f'      Pagador : {pix.get("nome_pagador")}')

# 2. Config da empresa emissora
print(f'\n[2/7] Lendo nfe_configuracao slug={SLUG}...')
config = buscar_nfe_configuracao_por_slug(SLUG)
if not config:
    print(f'      ERRO: configuração "{SLUG}" não encontrada.')
    sys.exit(1)
config['ambiente'] = 2   # forçar homologação independente do banco
print(f'      Emitente: {config.get("razao_social")} — CNPJ {config.get("cnpj")}')
print(f'      Ambiente: {config["ambiente"]} (homologação)')

# 3. Número da NF-e (somente leitura — sem incrementar)
print('\n[3/7] Lendo próximo número NF-e (sem incrementar)...')
row = db.execute_query(
    "SELECT ultimo_numero_nfe FROM nfe_configuracao WHERE id = %s",
    (config['id'],), fetch_one=True,
)
n_nf = (row['ultimo_numero_nfe'] if row else 0) + 1
print(f'      nNF (simulado): {n_nf}')

# 4. Certificado
print('\n[4/7] Carregando certificado...')
senha_env = config.get('certificado_senha_env', '')
senha = os.environ.get(senha_env, '')
if not senha:
    print(f'      ERRO: variável de ambiente {senha_env!r} não definida ou vazia.')
    sys.exit(1)
cert_path_pfx = config.get('certificado_path', '')
try:
    cert_pem, key_pem, _ = carregar_pfx(cert_path_pfx, senha)
    print('      OK — certificado carregado')
except Exception as e:
    print(f'      ERRO: {e}')
    sys.exit(1)

# 5. Chave de acesso
print('\n[5/7] Gerando chave de acesso...')
cnpj_digits = ''.join(filter(str.isdigit, config.get('cnpj', '')))
data_emissao = pix['horario'] if pix.get('horario') else datetime.now()
chave44, c_nf = gerar_chave('53', data_emissao, cnpj_digits, '55', '001', n_nf)
print(f'      nNF    : {n_nf}')
print(f'      Chave  : {chave44}')

# 6. Monta, assina e valida
print('\n[6/7] Montando → assinando → validando XSD...')
try:
    xml = montar_nfe(config, pix, n_nf, chave44, c_nf, data_emissao)
except Exception as e:
    print(f'      ERRO ao montar: {e}')
    sys.exit(1)

try:
    xml_assinado = assinar_nfe(xml, key_pem, cert_pem)
    ok = verificar_assinatura(xml_assinado, cert_pem)
    print(f'      Assinatura: {"OK" if ok else "FALHOU"}')
    if not ok:
        sys.exit(1)
except Exception as e:
    print(f'      ERRO ao assinar: {e}')
    sys.exit(1)

erros = validar_nfe(xml_assinado)
if erros:
    print(f'      XSD FALHOU — {len(erros)} erro(s):')
    for err in erros:
        print(f'        {err}')
    sys.exit(1)
print('      XSD: OK')

# 7. Envia para SEFAZ (homologação)
print('\n[7/7] Enviando para SVRS (homologação)...')
ca_bundle = config.get('ca_bundle_path') or False
try:
    with certificado_temp(cert_path_pfx, senha) as (cp, kp, _):
        resultado = enviar_autorizacao(
            xml_nfe_assinado=xml_assinado,
            cert_path=cp,
            key_path=kp,
            ambiente=2,
            verify=ca_bundle,
        )
except Exception as e:
    print(f'      ERRO na comunicação SOAP: {e}')
    sys.exit(1)

# ─── Resultado ───────────────────────────────────────────────────────────────

print('\n' + '=' * 60)
print('RETORNO SVRS')
print('=' * 60)
print(f'  HTTP         : {resultado["status_http"]}')
print(f'  Duração      : {resultado["duracao_ms"]:.0f}ms')
print(f'  cStat (lote) : {resultado["c_stat"]}  {resultado["x_motivo"]}')
if resultado['prot_c_stat']:
    print(f'  cStat (NF-e) : {resultado["prot_c_stat"]}  {resultado["prot_x_motivo"]}')
    print(f'  nProt        : {resultado["n_prot"]}')

autorizada = resultado['c_stat'] == '104' and resultado['prot_c_stat'] == '100'
duplicada  = resultado['prot_c_stat'] == '539'

if not autorizada and not duplicada:
    print('\n⚠️  NF-e não autorizada — verifique os dados acima.')
    if os.getenv('DEBUG_SOAP'):
        print(resultado.get('soap_response', '')[:4000])
    sys.exit(1)

# ─── Extrai protNFe e monta nfeProc ──────────────────────────────────────────

NS = 'http://www.portalfiscal.inf.br/nfe'
try:
    doc_soap = etree.fromstring(resultado['soap_response'].encode('utf-8'))
    prot_el  = doc_soap.find(f'.//{{{NS}}}protNFe')
    if prot_el is None:
        print('ERRO: protNFe não encontrado no retorno SOAP.')
        sys.exit(1)
    prot_nfe_xml = etree.tostring(prot_el, encoding='unicode')
except Exception as e:
    print(f'ERRO ao extrair protNFe: {e}')
    sys.exit(1)

nfe_proc_xml = _montar_nfe_proc(xml_assinado, prot_nfe_xml)

# ─── Salva arquivos ──────────────────────────────────────────────────────────

pasta = pathlib.Path(f'testes-nfe/pix-{PIX_ID}')
pasta.mkdir(parents=True, exist_ok=True)

(pasta / 'nfe_assinada.xml').write_bytes(xml_assinado)
(pasta / 'nfe_proc.xml').write_text(nfe_proc_xml, encoding='utf-8')

try:
    from brazilfiscalreport.danfe import Danfe
    pdf = Danfe(xml=nfe_proc_xml.encode('utf-8')).output()
    (pasta / 'danfe.pdf').write_bytes(pdf)
    print(f'\n  danfe.pdf    : {pasta / "danfe.pdf"}')
except ImportError:
    print('\n  danfe.pdf    : PULADO (brazilfiscalreport não instalado neste ambiente)')
except Exception as e:
    print(f'\n  danfe.pdf    : ERRO — {e}')

print(f'  nfe_assinada : {pasta / "nfe_assinada.xml"}')
print(f'  nfe_proc     : {pasta / "nfe_proc.xml"}')

status = '✅ AUTORIZADA' if autorizada else '⚠️  DUPLICADA (cStat=539 — esperado em reenvio homologação)'
print(f'\n{status}')
print(f'  Protocolo   : {resultado["n_prot"]}')
print(f'  Chave       : {chave44}')
