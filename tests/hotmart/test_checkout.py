"""O link do checkout da Hotmart e o preço que a prévia mostra."""
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from hotmart import checkout

OFERTA = {'codigo': 'sph9o75s', 'produto_hotmart': 9006872}


def test_link_com_oferta_xcod_e_email_codificados():
    link = checkout.link_pagamento(OFERTA, 'Ab_9-x', email='maría+teste@ejemplo.com')
    url = urlparse(link)
    assert (url.scheme, url.netloc, url.path) == ('https', 'pay.hotmart.com', '/9006872')
    assert parse_qs(url.query) == {'off': ['sph9o75s'], 'xcod': ['Ab_9-x'], 'email': ['maría+teste@ejemplo.com']}
    assert '+teste' not in link                             # o "+" vai codificado (%2B), senão vira espaço


def test_link_sem_email_nao_manda_o_parametro():
    assert checkout.link_pagamento(OFERTA, 'g1') == 'https://pay.hotmart.com/9006872?off=sph9o75s&xcod=g1'


def test_preco_da_previa():
    assert checkout.preco_texto(Decimal('149.00'), 'MXN') == 'MX$ 149'
    assert checkout.preco_texto(Decimal('49.90'), 'mxn') == 'MX$ 49.90'
    assert checkout.preco_texto(Decimal('10'), 'USD') == 'US$ 10'


def test_webhook_grava_o_email_da_hotmart_quando_o_pedido_nao_tem(cliente, repo):
    from tests.hotmart.conftest import aviso
    from tests.hotmart.test_webhook import _post
    _post(cliente, aviso())
    assert repo.pedidos[7]['email'] == 'cliente@exemplo.com' and repo.entregas == [7]


def test_webhook_nao_troca_o_email_que_o_pedido_ja_tem(cliente, repo):
    from tests.hotmart.conftest import aviso
    from tests.hotmart.test_webhook import _post
    repo.pedidos[7]['email'] = 'da-musica@exemplo.com'
    _post(cliente, aviso())
    assert repo.pedidos[7]['email'] == 'da-musica@exemplo.com'


def test_so_o_pedido_criado_e_reaproveitado():
    """1010 (OXXO gerado): o mesmo xcod em dois pagamentos; 1011 (cancelado): um aviso atrasado o cancelaria de novo."""
    assert checkout.ESTADOS_ABERTOS == (1001,)


def test_lembrete_nao_vai_para_quem_gerou_o_oxxo():
    import inspect
    from musica.adaptadores.repositorio_mysql import RepositorioMysql
    assert 'p.estado_id = 1010' in inspect.getsource(RepositorioMysql.candidatas_lembrete)


def test_preco_do_admin():
    from decimal import Decimal
    from admin.hotmart_views import _preco
    assert [_preco(x) for x in ('149', '149,00', '1.149', '1.149,90', '49.90')] == [
        Decimal('149.00'), Decimal('149.00'), Decimal('1149.00'), Decimal('1149.90'), Decimal('49.90')]
    assert [_preco(x) for x in ('nan', 'Infinity', '1e20', '0', '-5', '', 'abc', '99999999')] == [None] * 8


def test_segundo_pagamento_do_mesmo_pedido_vai_para_conferir(cliente, repo):
    from tests.hotmart.conftest import aviso
    from tests.hotmart.test_webhook import _post
    _post(cliente, aviso(id_='e1', transacao='HPOXXO', aprovado_ms=1763647200000))
    resposta = _post(cliente, aviso(id_='e2', transacao='HPCARTAO', aprovado_ms=1763650800000)).get_json()
    assert resposta['resultado'] == 'duplicado' and repo.entregas == [7]
    assert 'reembolsar a HPCARTAO' in repo.eventos['e2']['detalhe']
    # o COMPLETE da compra ORIGINAL depois do duplicado continua normal
    resposta = _post(cliente, aviso(id_='e3', transacao='HPOXXO', evento='PURCHASE_COMPLETE', status='COMPLETE',
                                    aprovado_ms=1763647200000)).get_json()
    assert resposta['resultado'] == 'ok'


def test_musica_paga_em_dois_pedidos_vai_para_conferir(cliente, repo):
    from tests.hotmart.conftest import aviso
    from tests.hotmart.test_webhook import _post
    repo.pedidos[8] = {'id': 8, 'guid': 'outro', 'produto_id': 50, 'plano_id': 501, 'estado_id': 1000,
                       'fluxo_inicial': 'web'}
    repo.musica_do_pedido.update({7: 99, 8: 99})                        # a mesma música nos dois pedidos
    resposta = _post(cliente, aviso()).get_json()
    assert resposta['resultado'] == 'duplicado' and repo.entregas == [7]
    assert 'pedido #8' in repo.eventos['evt-1']['detalhe']


def test_complete_sem_data_nao_faz_a_original_parecer_duplicada(cliente, repo):
    """O COMPLETE da compra original sem approved_date: vale a data gravada, não o "agora"."""
    from tests.hotmart.conftest import aviso
    from tests.hotmart.test_webhook import _post
    _post(cliente, aviso(id_='e1', transacao='HPA', aprovado_ms=1763647200000))
    _post(cliente, aviso(id_='e2', transacao='HPB', aprovado_ms=1763650800000))      # duplicada, marcada
    r = _post(cliente, aviso(id_='e3', transacao='HPA', evento='PURCHASE_COMPLETE', status='COMPLETE',
                             aprovado_ms=None)).get_json()
    assert r['resultado'] == 'ok' and repo.eventos['e2']['resultado'] == 'duplicado'
    assert str(repo.pagamentos['HPA']['aprovado_em']).startswith('2025-11-20')


def test_duplicado_nao_e_reprocessado(cliente, repo):
    import pytest
    from hotmart import servico
    from tests.hotmart.conftest import aviso
    from tests.hotmart.test_webhook import _post
    _post(cliente, aviso(id_='e1', transacao='HPA', aprovado_ms=1763647200000))
    _post(cliente, aviso(id_='e2', transacao='HPB', aprovado_ms=1763650800000))
    with pytest.raises(ValueError, match='não está para conferir'):
        servico.reprocessar(repo.eventos['e2']['id'])


def test_oferta_em_outra_moeda_nao_vai_para_link(monkeypatch):
    from decimal import Decimal
    linha = {'codigo': 'x', 'produto_id': 30, 'plano_id': 25, 'produto_hotmart': 1, 'preco': Decimal('10'),
             'moeda': 'USD', 'uso': 'botao'}
    monkeypatch.setattr(checkout, '_db', lambda: type('B', (), {'execute_query': lambda *a, **k: dict(linha)})())
    assert checkout.oferta_para_link('x', 30, 'MXN') is None and checkout.oferta_para_link('x', 30, 'USD') == linha
