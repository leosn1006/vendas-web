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


def test_tela_com_o_bcb_fora_do_ar_nao_chama_de_novo_por_10_minutos(monkeypatch):
    """Regressão (revisão de 26/11): com o BCB fora, a tela de ROI chamava o BCB (timeout de 10 s) a cada produto mesmo
    com o valor reserva guardado; a página passava do limite do Gunicorn (502). Como antes: reserva por 10 min, e depois
    disso tenta o BCB de novo."""
    relogio = [1000.0]
    feitas = []
    bcb_no_ar = [False]

    def get(url, params=None, timeout=None):
        feitas.append(url)
        if not bcb_no_ar[0]:
            raise TimeoutError('BCB fora')
        return _Resposta({'value': [{'cotacaoVenda': 5.8889, 'dataHoraCotacao': '2026-11-19 13:04:18'}]})
    monkeypatch.setattr(cotacao.requests, 'get', get)
    monkeypatch.setattr(cotacao.time, 'time', lambda: relogio[0])
    monkeypatch.setenv('COTACAO_USD_FALLBACK', '5.50')
    monkeypatch.setattr(cotacao, '_cache_moedas', {})
    monkeypatch.setattr(cotacao, '_cache_usd_tela', {})
    for _ in range(5):
        r = cotacao.obter_ptax_usd()
        assert r['fallback'] is True and r['valor'] == 5.50
    assert len(feitas) == 1                                    # uma tentativa só nos 10 min
    bcb_no_ar[0] = True
    relogio[0] += 9 * 60
    assert cotacao.obter_ptax_usd()['fallback'] is True and len(feitas) == 1
    relogio[0] += 2 * 60                                        # passou dos 10 min: tenta o BCB de novo
    r = cotacao.obter_ptax_usd()
    assert r['fallback'] is False and r['valor'] == 5.8889 and len(feitas) == 2


def test_tela_usa_a_ptax_de_verdade_que_chegou_depois_da_falha(monkeypatch):
    """Depois de uma falha, se a PTAX de verdade entrar no cache do processo (outro pedido de cotação em dólar),
    a tela usa ela no lugar da reserva."""
    bcb_no_ar = [False]

    def get(url, params=None, timeout=None):
        if not bcb_no_ar[0]:
            raise TimeoutError('BCB fora')
        return _Resposta({'value': [{'cotacaoVenda': 5.8889, 'dataHoraCotacao': '2026-11-19 13:04:18'}]})
    monkeypatch.setattr(cotacao.requests, 'get', get)
    monkeypatch.setenv('COTACAO_USD_FALLBACK', '5.50')
    monkeypatch.setattr(cotacao, '_cache_moedas', {})
    monkeypatch.setattr(cotacao, '_cache_usd_tela', {})
    assert cotacao.obter_ptax_usd()['fallback'] is True
    bcb_no_ar[0] = True
    assert cotacao.ptax_venda('USD')['valor'] == 5.8889       # outro caminho trouxe a PTAX
    r = cotacao.obter_ptax_usd()
    assert r['fallback'] is False and r['valor'] == 5.8889
