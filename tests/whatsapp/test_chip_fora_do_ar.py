"""
Chip do gateway caído: fluxos automáticos NÃO tentam enviar (adiam), em vez de rajada de 503.
Números da Meta seguem sem essa checagem (comportamento anterior).
"""
import pytest

import whatsapp
from fluxos import _executor_acao as executor
from fluxos import fluxo_responder
from whatsapp import ChipForaDoArWhatsApp, ErroTransienteWhatsApp

ACAO = {'acao': 'enviar_mensagem', 'mensagem': 'oi', 'delay_inicial': 0, 'delay_final': 0,
        'url': None, 'caption': None, 'nome_arquivo': None, 'produto_id': 1, 'fluxo': 'introducao',
        'condicao': 'sempre', 'ordem': 1}


@pytest.fixture
def enviados(monkeypatch):
    lista = []
    monkeypatch.setattr(executor, 'enviar_mensagem', lambda pedido, msg: lista.append(msg) or 'wamid.X')
    monkeypatch.setattr(executor, 'salvar_mensagem_pedido', lambda *a, **k: None)
    return lista


def test_chip_wpp_web_desconectado_levanta_e_nao_envia(monkeypatch, enviados):
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda _p: 'wpp_web')
    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional', lambda _p: False)
    monkeypatch.setattr(whatsapp, '_gateway_confirma_conectado', lambda _p: False)  # gateway também diz que caiu
    with pytest.raises(ChipForaDoArWhatsApp):
        executor.executar_acao(ACAO, {'id': 7, 'phone_number_id': 'web-1'}, None, 7, aplicar_delay=False)
    assert enviados == []


def test_chip_fora_do_ar_e_erro_transiente():
    # herda de ErroTransienteWhatsApp: código existente que já trata "tente de novo depois" continua valendo
    assert issubclass(ChipForaDoArWhatsApp, ErroTransienteWhatsApp)


def test_chip_wpp_web_conectado_envia(monkeypatch, enviados):
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda _p: 'wpp_web')
    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional', lambda _p: True)
    executor.executar_acao(ACAO, {'id': 7, 'phone_number_id': 'web-1'}, None, 7, aplicar_delay=False)
    assert enviados == ['oi']


def test_numero_meta_nao_e_checado(monkeypatch, enviados):
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda _p: 'meta')

    def nao_deveria_chamar(_p):
        raise AssertionError('numero_empresa_operacional não deve ser consultado para número Meta')

    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional', nao_deveria_chamar)
    executor.executar_acao(ACAO, {'id': 7, 'phone_number_id': '1012710858592627'}, None, 7, aplicar_delay=False)
    assert enviados == ['oi']


# ─── responder (IA) ──────────────────────────────────────────────────────────

@pytest.fixture
def resposta_enviada(monkeypatch):
    lista = []
    monkeypatch.setattr(fluxo_responder, 'enviar_mensagem', lambda pedido, msg: lista.append(msg) or 'wamid.X')
    monkeypatch.setattr(fluxo_responder, 'salvar_mensagem_pedido', lambda *a, **k: None)
    return lista


def test_responder_chip_fora_do_ar_levanta_transiente_e_nao_envia(monkeypatch, resposta_enviada):
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda _p: 'wpp_web')
    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional', lambda _p: False)
    monkeypatch.setattr(whatsapp, '_gateway_confirma_conectado', lambda _p: False)  # gateway também diz que caiu
    # transiente: tasks.enviar_resposta_cliente já reagenda ErroTransienteWhatsApp (60 s) com a mesma resposta
    with pytest.raises(ErroTransienteWhatsApp):
        fluxo_responder.enviar_resposta({'id': 7, 'phone_number_id': 'web-1'}, 'oi', 7)
    assert resposta_enviada == []


def test_responder_chip_conectado_envia(monkeypatch, resposta_enviada):
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda _p: 'wpp_web')
    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional', lambda _p: True)
    fluxo_responder.enviar_resposta({'id': 7, 'phone_number_id': 'web-1'}, 'oi', 7)
    assert resposta_enviada == ['oi']


def test_responder_numero_meta_nao_consulta_status(monkeypatch, resposta_enviada):
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda _p: 'meta')
    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional',
                        lambda _p: (_ for _ in ()).throw(AssertionError('não deve consultar status de número Meta')))
    fluxo_responder.enviar_resposta({'id': 7, 'phone_number_id': '1012710858592627'}, 'oi', 7)
    assert resposta_enviada == ['oi']
