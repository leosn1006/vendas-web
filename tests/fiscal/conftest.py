"""
Fixtures compartilhadas pelos testes fiscais.
Gera certificado auto-assinado efêmero para testes locais — sem depender
do certificado A1 real (que nunca deve entrar no repositório).

Opção CLI extra:
    --tenant SLUG   seleciona tenant na nfe_configuracao (default: primeiro ativo)
"""
import datetime
import pytest


def pytest_addoption(parser):
    parser.addoption(
        '--tenant',
        default=None,
        help='tenant_slug da nfe_configuracao a usar nos testes de integração (ex: lbe-livros)',
    )


@pytest.fixture(scope='session')
def tenant_slug(request):
    return request.config.getoption('--tenant')

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope='session')
def test_cert_pem_key_pem():
    """Retorna (cert_pem: bytes, key_pem: bytes) de um certificado auto-assinado."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, 'Teste NF-e'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Testes Unitarios'),
    ])
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return cert_pem, key_pem
