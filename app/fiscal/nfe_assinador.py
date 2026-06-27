"""
Assina digitalmente o XML da NF-e usando assinatura enveloped XML DSig.
Algoritmos conforme MOC NF-e 4.00:
  - SignatureMethod : RSA-SHA1
  - DigestMethod    : SHA-1
  - C14N            : Canonical XML 1.0
A assinatura referencia infNFe pelo atributo Id="NFe{chave}" e é
inserida como irmã de infNFe dentro de <NFe>.
"""
from lxml import etree
from signxml import XMLSigner, XMLVerifier, methods
from signxml.algorithms import SignatureMethod, DigestAlgorithm, CanonicalizationMethod
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509 import load_pem_x509_certificate


class _NFeSigner(XMLSigner):
    # signxml 5+ bloqueia SHA1 por padrão via check_deprecated_methods().
    # NF-e 4.00 MOC (NT/2020) exige RSA-SHA1 + SHA1 digest — sem alternativa legal.
    # check_deprecated_methods é um hook público do signxml, projetado para ser sobrescrito
    # em casos de compatibilidade fiscal/legado. Pinnar signxml em requirements.txt para
    # evitar quebra se o nome do método mudar em versões futuras.
    def check_deprecated_methods(self):
        pass


_SIGNER = _NFeSigner(
    method=methods.enveloped,
    signature_algorithm=SignatureMethod.RSA_SHA1,
    digest_algorithm=DigestAlgorithm.SHA1,
    c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
)


def assinar_nfe(xml_nfe: str, key_pem: bytes, cert_pem: bytes) -> bytes:
    """
    Assina o XML <NFe> e retorna os bytes do XML assinado.

    Args:
        xml_nfe:  XML string com <NFe xmlns="..."><infNFe Id="NFe...">...</infNFe></NFe>
        key_pem:  chave privada RSA em PEM (sem senha)
        cert_pem: certificado A1 em PEM

    Returns:
        Bytes do XML assinado — não reformatar após esta chamada.
    """
    root = etree.fromstring(xml_nfe.encode('utf-8'))

    chave_privada = load_pem_private_key(key_pem, password=None)
    certificado   = load_pem_x509_certificate(cert_pem)

    # Obtém o Id de infNFe para montar a referência URI
    inf_nfe = root.find('{http://www.portalfiscal.inf.br/nfe}infNFe')
    nfe_id  = inf_nfe.get('Id')          # ex: "NFe5326066498..."
    ref_uri = f'#{nfe_id}'               # ex: "#NFe5326066498..."

    signed_root = _SIGNER.sign(
        root,
        key=chave_privada,
        cert=[certificado],
        reference_uri=ref_uri,
        id_attribute='Id',
    )

    return etree.tostring(signed_root, encoding='utf-8', xml_declaration=False)


class _NFeVerifier(XMLVerifier):
    # Mesmo motivo do _NFeSigner: verifica assinaturas NF-e que usam RSA-SHA1 + SHA1.
    def check_signature_alg_expected(self, *args, **kwargs):
        pass

    def check_digest_alg_expected(self, *args, **kwargs):
        pass


def verificar_assinatura(xml_assinado: bytes, cert_pem: bytes) -> bool:
    """Verifica a assinatura do XML. Retorna True se válida."""
    certificado = load_pem_x509_certificate(cert_pem)
    _NFeVerifier().verify(xml_assinado, x509_cert=certificado)
    return True
