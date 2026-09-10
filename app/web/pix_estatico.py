"""
Gerador de QR Code PIX estático (BR Code EMV) — sem chamada de API.

Spec: Manual de Padrões para Iniciação do PIX (BACEN) versão 2.3
Campos EMV usados:
  00  Payload Format Indicator   "01"
  26  Merchant Account Info PIX  gui + chave_pix
  52  Merchant Category Code     "0000"
  53  Transaction Currency       "986" (BRL)
  54  Transaction Amount         valor formatado "10.00"
  58  Country Code               "BR"
  59  Merchant Name              max 25 chars, só ASCII imprimível
  60  Merchant City              max 15 chars, só ASCII imprimível
  62  Additional Data            subcampo 05 = txid (Reference Label), max 25 chars
  63  CRC16-CCITT                checksum obrigatório
"""
import io
import base64
import unicodedata
import qrcode
from qrcode.image.pil import PilImage


_PIX_GUI = 'BR.GOV.BCB.PIX'


def _ascii(text: str, max_len: int) -> str:
    """Remove acentos e caracteres não-ASCII, trunca ao tamanho máximo."""
    normalized = unicodedata.normalize('NFKD', text)
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    # Manter só printable ASCII permitido pelo spec
    cleaned = ''.join(c for c in ascii_only if 32 <= ord(c) <= 126)
    return cleaned[:max_len]


def _campo(id_: str, value: str) -> str:
    """Formata um campo EMV: ID (2 chars) + tamanho (2 chars) + valor."""
    return f'{id_}{len(value):02d}{value}'


def _crc16(payload: str) -> str:
    """CRC16-CCITT (polinômio 0x1021, seed 0xFFFF)."""
    crc = 0xFFFF
    for char in payload.encode('utf-8'):
        crc ^= char << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f'{crc:04X}'


def gerar_payload_pix(
    chave_pix: str,
    valor: float,
    nome_recebedor: str,
    cidade: str,
    txid: str,
) -> str:
    """
    Monta o payload EMV do QR Code PIX estático.

    Args:
        chave_pix:      e-mail, CPF, CNPJ ou chave aleatória
        valor:          valor em reais (ex: 10.50)
        nome_recebedor: nome do recebedor (normalizado para ASCII, max 25)
        cidade:         cidade do recebedor (normalizado para ASCII, max 15)
        txid:           identificador do pedido — apenas [A-Za-z0-9], max 25

    Returns:
        String payload EMV pronta para gerar o QR Code.
    """
    nome  = _ascii(nome_recebedor, 25)
    cid   = _ascii(cidade, 15)
    ref   = ''.join(c for c in str(txid) if c.isalnum())[:25]
    valor_str = f'{float(valor):.2f}'

    # BACEN limita chaves PIX (email ≤ 77 chars), mas validamos aqui para garantir que
    # merchant_account ≤ 99 chars (campo 26 usa prefixo de 2 dígitos: máx "26" + "99" + valor).
    # GUI subfield = 18 chars fixos → chave pode ter no máximo 77 chars.
    if len(chave_pix) > 77:
        raise ValueError(f'Chave PIX excede 77 caracteres (len={len(chave_pix)}): payload EMV seria inválido')

    merchant_account = (
        _campo('00', _PIX_GUI)
        + _campo('01', chave_pix)
    )
    additional = _campo('05', ref)

    payload = (
        _campo('00', '01')
        + _campo('26', merchant_account)
        + _campo('52', '0000')
        + _campo('53', '986')
        + _campo('54', valor_str)
        + _campo('58', 'BR')
        + _campo('59', nome)
        + _campo('60', cid)
        + _campo('62', additional)
        + '6304'            # campo 63 com tamanho 04, valor calculado a seguir
    )
    return payload + _crc16(payload)


def gerar_qrcode_base64(payload: str, box_size: int = 6, border: int = 2) -> str:
    """Gera imagem PNG do QR Code e retorna como base64."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img: PilImage = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('ascii')
