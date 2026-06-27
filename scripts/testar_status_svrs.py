"""
Testa a conectividade com a SVRS consultando o status do serviço NF-e.
Resultado esperado: cStat=107 (Serviço em Operação).
Uso: NF_CERT_SENHA="sua_senha" python scripts/testar_status_svrs.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.fiscal.nfe_soap import consultar_status_servico

CAMINHO_PFX = 'infra/nginx/certs/64.980.953 LEONARDO SANTOS NEGREIROS_64980953000146.pfx'
SENHA = os.getenv('NF_CERT_SENHA', '')

if not SENHA:
    print('ERRO: defina NF_CERT_SENHA antes de rodar.')
    sys.exit(1)

print('Consultando status do serviço SVRS (homologação)...')
try:
    # verify=False ignora verificação do certificado do servidor (CA ICP-Brasil não está no bundle padrão)
    # Em produção: substituir por verify='/caminho/para/cadeia-icp-brasil.pem'
    resultado = consultar_status_servico(CAMINHO_PFX, SENHA, ambiente=2, verify=False)
except Exception as e:
    print(f'ERRO na comunicação SOAP: {e}')
    sys.exit(1)

print(f'  cStat    : {resultado["cStat"]}')
print(f'  xMotivo  : {resultado["xMotivo"]}')
print(f'  dhRecbto : {resultado["dhRecbto"]}')
print(f'  HTTP     : {resultado["status_http"]}')
print(f'  Duração  : {resultado["duracao_ms"]:.0f}ms')

if resultado['cStat'] == '107':
    print('\nOK — SVRS em operação. Conectividade e certificado validados.')
else:
    print(f'\nATENÇÃO — cStat inesperado: {resultado["cStat"]}')
