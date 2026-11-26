"""Cliente da API de vendas da Hotmart: token guardado, renovação no 401, paginação, sem credencial."""
import pytest

from hotmart import api, config


class _Resp:
    def __init__(self, status, corpo):
        self.status_code, self._corpo, self.text = status, corpo, str(corpo)

    def json(self):
        return self._corpo


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setattr(config, 'CLIENT_ID', 'id')
    monkeypatch.setattr(config, 'CLIENT_SECRET', 'segredo')
    monkeypatch.setattr(config, 'CLIENT_TOKEN', 'abc')
    monkeypatch.setattr(api, '_token', {})
    registro = {'tokens': 0, 'gets': [], 'respostas': []}

    def post(url, params=None, headers=None, timeout=None):
        registro['tokens'] += 1
        assert headers['Authorization'] == 'Basic abc'           # o prefixo é posto quando falta
        return _Resp(200, {'access_token': f"tok{registro['tokens']}", 'expires_in': 172799})

    def get(url, params=None, headers=None, timeout=None):
        registro['gets'].append((url, dict(params), headers['Authorization']))
        return registro['respostas'].pop(0)

    monkeypatch.setattr(api.requests, 'post', post)
    monkeypatch.setattr(api.requests, 'get', get)
    return registro


def test_pagina_ate_o_fim_e_guarda_o_token(http):
    http['respostas'] += [_Resp(200, {'items': [1, 2], 'page_info': {'next_page_token': 'p2'}}),
                          _Resp(200, {'items': [3], 'page_info': {}})]
    assert api.listar('sales/history', transaction_status='APPROVED', start_date=None) == [1, 2, 3]
    assert http['tokens'] == 1
    assert http['gets'][1][1]['page_token'] == 'p2' and 'start_date' not in http['gets'][0][1]
    assert http['gets'][0][0] == 'https://developers.hotmart.com/payments/api/v1/sales/history'


def test_401_renova_o_token_uma_vez(http):
    http['respostas'] += [_Resp(401, {}), _Resp(200, {'items': [], 'page_info': {}})]
    assert api.listar('sales/history') == []
    assert http['tokens'] == 2 and http['gets'][1][2] == 'Bearer tok2'


def test_403_vira_erro_com_a_mensagem_da_hotmart(http):
    http['respostas'] += [_Resp(403, {'error_description': "You don't have permission to take this action."})]
    with pytest.raises(api.ErroApi, match='HTTP 403 You'):
        api.listar('sales/history')


def test_sem_credencial_desligada(monkeypatch):
    monkeypatch.setattr(config, 'CLIENT_ID', '')
    monkeypatch.setattr(api, '_token', {})
    assert not api.configurada()
    with pytest.raises(api.ApiDesligada):
        api.listar('sales/history')
