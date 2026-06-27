import os
import tempfile
import logging
from contextlib import contextmanager
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption
)

logger = logging.getLogger(__name__)


def carregar_pfx(caminho_pfx: str, senha: str) -> tuple[bytes, bytes, bytes]:
    """
    Carrega um certificado A1 (.pfx) e extrai seus componentes.

    Retorna (cert_pem, key_pem, cert_der):
      - cert_pem: certificado em PEM (para mTLS e signxml)
      - key_pem:  chave privada em PEM sem senha (para mTLS e signxml)
      - cert_der: certificado em DER/base64 (para KeyInfo no XML assinado)
    """
    with open(caminho_pfx, 'rb') as f:
        dados_pfx = f.read()

    senha_bytes = senha.encode('utf-8') if isinstance(senha, str) else senha
    chave, certificado, _ = load_key_and_certificates(dados_pfx, senha_bytes)

    cert_pem = certificado.public_bytes(Encoding.PEM)
    key_pem = chave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    cert_der = certificado.public_bytes(Encoding.DER)

    return cert_pem, key_pem, cert_der


@contextmanager
def certificado_temp(caminho_pfx: str, senha: str):
    """
    Context manager: extrai o .pfx e disponibiliza arquivos temporários PEM
    prontos para uso em requests (mTLS).

    Uso:
        with certificado_temp(path, senha) as (cert_path, key_path, cert_der):
            requests.post(url, cert=(cert_path, key_path), ...)
    """
    cert_pem, key_pem, cert_der = carregar_pfx(caminho_pfx, senha)

    cert_tmp = tempfile.NamedTemporaryFile(suffix='.pem', delete=False)
    key_tmp  = tempfile.NamedTemporaryFile(suffix='.pem', delete=False)
    try:
        cert_tmp.write(cert_pem)
        cert_tmp.flush()
        key_tmp.write(key_pem)
        key_tmp.flush()
        cert_tmp.close()
        key_tmp.close()
        yield cert_tmp.name, key_tmp.name, cert_der
    finally:
        os.unlink(cert_tmp.name)
        os.unlink(key_tmp.name)
