"""Payload de webhook emitido pelo api-wpp-web lido pelo orquestrador existente + dedupe + cliente admin."""
import pytest

import whatsapp_orquestrador as orq


def _payload(**msg):
    mensagem = {'id': 'wamid.HBg', 'timestamp': '1790000000', 'type': 'text', 'from': '556181163324',
                'text': {'body': 'quero o produto'}}
    mensagem.update(msg)
    return {'object': 'whatsapp_business_account', 'entry': [{'id': 'web-5561982402450', 'changes': [{
        'field': 'messages', 'value': {
            'messaging_product': 'whatsapp',
            'metadata': {'display_phone_number': '5561982402450', 'phone_number_id': 'web-5561982402450'},
            'contacts': [{'profile': {'name': 'Cliente'}, 'wa_id': '556181163324'}],
            'messages': [mensagem]}}]}]}


@pytest.fixture(autouse=True)
def _sem_banco(monkeypatch):
    monkeypatch.setattr(orq, 'get_produto_by_phone_number_id', lambda _p: {'id': 10})


def test_texto_do_gateway_e_extraido():
    dados = orq.extrair_dados_mensagem(_payload())
    assert dados['phone_number_id'] == 'web-5561982402450'
    assert dados['produto'] == 10
    assert dados['contact_to'] == '556181163324'
    assert dados['texto'] == 'quero o produto'


def test_remetente_lid_sem_telefone_responde_para_o_lid():
    payload = _payload()
    valor = payload['entry'][0]['changes'][0]['value']
    del valor['messages'][0]['from']
    valor['contacts'][0] = {'profile': {'name': 'Cliente'}, 'user_id': '123456789012345@lid'}
    dados = orq.extrair_dados_mensagem(payload)
    assert dados['numero_remetente'] == ''
    assert dados['contact_to'] == '123456789012345@lid'


def test_audio_do_gateway_e_aceito():
    dados = orq.extrair_dados_mensagem(_payload(type='audio', audio={'id': 'x', 'voice': True, 'mime_type': 'audio/ogg'},
                                                text=None))
    assert dados is not None


def test_dedupe_do_webhook_cobre_a_janela_da_outbox_do_gateway():
    import tasks
    # o gateway reentrega por até 24 h (OUTBOX_MAX_AGE_HOURS); com 300 s o wamid repetido virava pedido/resposta em dobro
    assert tasks._WEBHOOK_DEDUPE_TTL_S >= 24 * 3600


def test_qr_vira_svg():
    import wpp_web_gateway
    svg = wpp_web_gateway.qr_para_svg('2@abc,def,ghi==')
    assert svg.lstrip().startswith(('<?xml', '<svg'))
    assert '<svg' in svg


def test_base_admin_deriva_do_url_do_graph(monkeypatch):
    import wpp_web_gateway
    monkeypatch.setattr(wpp_web_gateway, 'WPP_WEB_API_URL', 'http://api-wpp-web:3100/v24.0/')
    assert wpp_web_gateway._base_admin() == 'http://api-wpp-web:3100'
