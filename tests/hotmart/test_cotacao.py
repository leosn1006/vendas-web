"""Cotação em reais: PTAX do BCB para as 10 moedas dele, referência do BCE para as outras (MXN, INR), None sem nenhuma."""
import pytest

import cotacao


class _Resposta:
    def __init__(self, corpo, status=200):
        self.corpo, self.status_code = corpo, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self.corpo


@pytest.fixture
def chamadas(monkeypatch):
    feitas = []

    def get(url, params=None, timeout=None):
        feitas.append(url)
        if 'frankfurter' in url:
            if params['base'] == 'NGN':
                return _Resposta({'message': 'not found'}, 404)
            return _Resposta({'date': '2026-11-20', 'rates': {'BRL': 0.31142}})
        return _Resposta({'value': [{'cotacaoVenda': 5.8889, 'dataHoraCotacao': '2026-11-19 13:04:18'}]})

    monkeypatch.setattr(cotacao.requests, 'get', get)
    monkeypatch.setattr(cotacao, '_cache_moedas', {})
    return feitas


def test_dolar_pela_ptax(chamadas):
    cot = cotacao.cotacao_em_reais('usd')
    assert cot['fonte'] == 'ptax' and cot['valor'] == 5.8889
    assert 'olinda' in chamadas[0]


def test_peso_mexicano_pelo_bce_sem_tentar_a_ptax(chamadas):
    cot = cotacao.cotacao_em_reais('MXN')
    assert cot['fonte'] == 'bce' and cot['valor'] == 0.31142
    assert all('frankfurter' in url for url in chamadas)


def test_naira_sem_cotacao(chamadas):
    assert cotacao.cotacao_em_reais('NGN') is None


def test_cache_por_moeda(chamadas):
    cotacao.cotacao_em_reais('MXN')
    cotacao.cotacao_em_reais('MXN')
    assert len(chamadas) == 1


def test_ptax_usa_o_boletim_de_fechamento(monkeypatch):
    boletins = [{'cotacaoVenda': 5.80, 'dataHoraCotacao': '2026-11-19 13:04:18', 'tipoBoletim': 'Fechamento'},
                {'cotacaoVenda': 5.95, 'dataHoraCotacao': '2026-11-20 10:10:00', 'tipoBoletim': 'Abertura'}]
    monkeypatch.setattr(cotacao.requests, 'get', lambda *a, **k: _Resposta({'value': boletins}))
    monkeypatch.setattr(cotacao, '_cache_moedas', {})
    assert cotacao.ptax_venda('USD')['valor'] == 5.80


def test_tela_do_roi_cai_no_fallback_fixo_sem_o_bcb(monkeypatch):
    monkeypatch.setattr(cotacao.requests, 'get', lambda *a, **k: _Resposta({}, 503))
    monkeypatch.setattr(cotacao, '_cache_moedas', {})
    monkeypatch.setattr(cotacao, '_cache_usd_tela', {})
    monkeypatch.setenv('COTACAO_USD_FALLBACK', '5.40')
    assert cotacao.obter_ptax_usd() == {'valor': 5.40, 'data': None, 'fallback': True}
