"""
Valida o XML da NF-e contra o XSD oficial (bundled com nfelib).
A validação ocorre antes do envio à SEFAZ para rejeitar antecipadamente
erros de schema — evitando gastar número de NF-e com uma nota inválida.
"""
import os
import logging
import threading
from lxml import etree

logger = logging.getLogger(__name__)

def _schema_path(nome: str) -> str:
    import nfelib
    return os.path.join(os.path.dirname(nfelib.__file__), 'nfe', 'schemas', 'v4_0', nome)


_schema: etree.XMLSchema | None = None
_schema_lock = threading.Lock()


def _carregar_schema_nfe() -> etree.XMLSchema:
    """Carrega e cacheia o XMLSchema do nfe_v4.00.xsd (thread-safe)."""
    global _schema
    if _schema is None:
        xsd_path = _schema_path('nfe_v4.00.xsd')
        with open(xsd_path, 'rb') as f:
            doc = etree.parse(f, parser=etree.XMLParser(load_dtd=False))
        _schema = etree.XMLSchema(doc)
    return _schema


def validar_nfe(xml: str | bytes) -> list[str]:
    """
    Valida o XML <NFe> contra o XSD NF-e 4.00.

    Args:
        xml: XML da NF-e (assinado ou não).

    Returns:
        Lista de erros. Vazia = XML válido.
    """
    if isinstance(xml, str):
        xml = xml.encode('utf-8')

    schema = _carregar_schema_nfe()
    try:
        doc = etree.fromstring(xml)
        # Lock necessário: XMLSchema.validate() modifica schema.error_log in-place.
        # Sem o lock, duas tasks concorrentes leriam o error_log uma da outra.
        with _schema_lock:
            schema.validate(doc)
            erros = [str(e) for e in schema.error_log]
    except etree.XMLSyntaxError as e:
        erros = [f'XML malformado: {e}']

    if erros:
        for e in erros:
            logger.warning(f'[NF-e XSD] {e}')
    return erros
