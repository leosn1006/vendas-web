"""
Testa o carregamento do certificado A1 (.pfx) para NF-e.
Uso: NF_CERT_SENHA="sua_senha" python scripts/testar_certificado_nfe.py

Em produção o path vem de nfe_configuracao.certificado_path no banco.
Aqui usamos o path fixo de desenvolvimento.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.fiscal.certificado import carregar_pfx
from cryptography import x509

CAMINHO_PFX = 'infra/nginx/certs/64.980.953 LEONARDO SANTOS NEGREIROS_64980953000146.pfx'
SENHA = os.getenv('NF_CERT_SENHA', '')

if not SENHA:
    print('ERRO: defina a variável NF_CERT_SENHA antes de rodar.')
    print('  export NF_CERT_SENHA="sua_senha"')
    sys.exit(1)

print(f'Carregando: {CAMINHO_PFX}')
try:
    cert_pem, key_pem, cert_der = carregar_pfx(CAMINHO_PFX, SENHA)
except Exception as e:
    print(f'ERRO ao carregar .pfx: {e}')
    sys.exit(1)

cert = x509.load_pem_x509_certificate(cert_pem)
print(f'OK — certificado carregado com sucesso')
print(f'  Subject : {cert.subject.rfc4514_string()}')
print(f'  Validade: {cert.not_valid_after_utc.strftime("%d/%m/%Y")}')
print(f'  cert_pem: {len(cert_pem)} bytes')
print(f'  key_pem : {len(key_pem)} bytes')
print(f'  cert_der: {len(cert_der)} bytes')
