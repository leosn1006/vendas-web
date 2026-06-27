"""
Testa o fluxo completo de emissão NF-e em homologação SVRS, sem banco de dados.

O script executa todas as etapas:
  gerar_chave → montar_nfe → assinar_nfe → validar_nfe (XSD) → enviar_autorizacao

Resultado esperado: cStat=100 (Autorizado) ou cStat=2xx/5xx (rejeição fiscal —
não é bug do código, mas dado de entrada a corrigir com o contador).

Uso:
  NF_CERT_SENHA="sua_senha" python scripts/testar_emissao_nfe.py
"""
import os
import sys
import pprint
from datetime import datetime
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.fiscal.certificado import carregar_pfx, certificado_temp
from app.fiscal.nfe_chave import gerar_chave
from app.fiscal.nfe_xml_builder import montar_nfe
from app.fiscal.nfe_assinador import assinar_nfe, verificar_assinatura
from app.fiscal.nfe_validador import validar_nfe
from app.fiscal.nfe_soap import enviar_autorizacao

# ─── Configuração ────────────────────────────────────────────────────────────

CAMINHO_PFX = 'infra/nginx/certs/64.980.953 LEONARDO SANTOS NEGREIROS_64980953000146.pfx'
SENHA = os.getenv('NF_CERT_SENHA', '')

if not SENHA:
    print('ERRO: defina NF_CERT_SENHA antes de rodar.')
    sys.exit(1)

# Espelha os campos relevantes de nfe_configuracao
CONFIG = {
    'serie_padrao': '001',
    'ambiente': 2,           # 2 = homologação
    'x_prod': 'LIVRO DIGITAL - NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL',
    'ncm': '49011000',       # livros — a confirmar com contador
    'cfop': '6107',          # venda interestadual a não-contribuinte — a confirmar
}

# Espelha os campos de pagamento_pix usados pelo builder
PIX = {
    'cpf_cnpj': '12345678909',   # CPF fictício com dígitos verificadores válidos
    'nome_pagador': 'COMPRADOR HOMOLOGACAO',
    'valor': '97.00',
}

# ─── Pipeline ────────────────────────────────────────────────────────────────

print('=' * 60)
print('TESTE DE EMISSÃO NF-e HOMOLOGAÇÃO SVRS')
print('=' * 60)

# 1. Certificado
print('\n[1/6] Carregando certificado...')
try:
    cert_pem, key_pem, _ = carregar_pfx(CAMINHO_PFX, SENHA)
    print('      OK — certificado carregado')
except Exception as e:
    print(f'      ERRO: {e}')
    sys.exit(1)

# 2. Chave de acesso
print('\n[2/6] Gerando chave de acesso...')
data_emissao = datetime.now()
n_nf = 1   # número de teste
chave44, c_nf = gerar_chave('53', data_emissao, '64980953000146', '55', '001', n_nf)
print(f'      Número   : {n_nf}')
print(f'      Chave 44 : {chave44}')
print(f'      cDV      : {chave44[-1]}')

# 3. Monta XML
print('\n[3/6] Montando XML infNFe...')
try:
    xml = montar_nfe(CONFIG, PIX, n_nf, chave44, c_nf, data_emissao)
    print(f'      OK — {len(xml)} chars')
except Exception as e:
    print(f'      ERRO: {e}')
    sys.exit(1)

# 4. Assina
print('\n[4/6] Assinando XML (RSA-SHA1 + C14N 1.0)...')
try:
    xml_assinado = assinar_nfe(xml, key_pem, cert_pem)
    print(f'      OK — {len(xml_assinado)} bytes')
    ok_assinatura = verificar_assinatura(xml_assinado, cert_pem)
    print(f'      Assinatura verificada: {ok_assinatura}')
except Exception as e:
    print(f'      ERRO: {e}')
    sys.exit(1)

# XML completo (antes da validação)
print('\n' + '─' * 60)
print('XML NF-e ASSINADO')
print('─' * 60)
doc = etree.fromstring(xml_assinado)
print(etree.tostring(doc, pretty_print=True, encoding='unicode'))
print('─' * 60)

# 5. Valida XSD
print('\n[5/6] Validando contra XSD NF-e 4.00...')
erros = validar_nfe(xml_assinado)
if erros:
    print(f'      FALHA — {len(erros)} erro(s):')
    for e in erros:
        print(f'        {e}')
    sys.exit(1)
print('      OK — XML válido')

# 6. Envia para SEFAZ
print('\n[6/6] Enviando para SVRS (homologação)...')
try:
    with certificado_temp(CAMINHO_PFX, SENHA) as (cert_path, key_path, _):
        resultado = enviar_autorizacao(
            xml_nfe_assinado=xml_assinado,
            cert_path=cert_path,
            key_path=key_path,
            ambiente=2,
            verify=False,
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
    print(f'  dhRecbto     : {resultado["dh_recbto"]}')

if resultado['c_stat'] == '104' and resultado['prot_c_stat'] == '100':
    print()
    print('✅  NF-e AUTORIZADA em homologação!')
    print(f'    Protocolo : {resultado["n_prot"]}')
    print(f'    Chave     : {chave44}')
    print('\n' + '─' * 60)
    print('XML DE RETORNO (nfeProc)')
    print('─' * 60)
    try:
        doc_ret = etree.fromstring(resultado['soap_response'].encode('utf-8'))
        ret_envi = doc_ret.find('.//{http://www.portalfiscal.inf.br/nfe}retEnviNFe')
        if ret_envi is not None:
            print(etree.tostring(ret_envi, pretty_print=True, encoding='unicode'))
        else:
            print(resultado['soap_response'])
    except Exception:
        print(resultado['soap_response'])
    print('─' * 60)
elif resultado['c_stat'] or resultado['prot_c_stat']:
    print()
    print('⚠️  Rejeição SEFAZ (esperado em testes — verificar NCM/CFOP/dados com contador)')

if os.getenv('DEBUG_SOAP'):
    print('\n--- SOAP Response (DEBUG_SOAP=1) ---')
    print(resultado['soap_response'][:3000])
