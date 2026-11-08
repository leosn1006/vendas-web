"""WhatsApp do formulário do checkout: mesmo formato no Pix e no cartão (antes o cartão gravava vazio)."""
import pytest

from web.checkout import _whatsapp_do_checkout


@pytest.mark.parametrize('body, esperado', [
    ({'whatsapp': '(61) 98116-3324'}, '556181163324'),           # celular BR: tira o 9º dígito
    ({'whatsapp': '61 8116-3324'}, '556181163324'),              # já sem o 9
    ({'whatsapp': '5561981163324'}, '556181163324'),             # já com DDI
    ({'whatsapp': '(55) 99123-4567'}, '555591234567'),           # DDD 55 (RS) sem DDI
    ({'whatsapp': '(55) 9123-4567'}, '555591234567'),
    ({'whatsapp': '555591234567'}, '555591234567'),              # DDD 55 já com DDI
    ({'whatsapp': '351912345678', 'ddi': '351'}, '351912345678'),  # outro país: não mexe
    ({'whatsapp': '91234567890', 'ddi': '86'}, '8691234567890'),   # 13 dígitos fora do BR: não tira dígito
    ({'whatsapp': ''}, ''),                                      # opcional, não preenchido
    ({}, ''),
    ({'whatsapp': None, 'ddi': None}, ''),
])
def test_whatsapp_do_checkout(body, esperado):
    assert _whatsapp_do_checkout(body) == esperado
