"""Resultado do A/B da contribuição (database.busca_teste_contribuicao): o pagamento do braço estante sai de uma
consulta à parte (vínculo + e-mail, em UNION). A regra continua: o 1º pago (menor id) por entrega, e cada pagamento
conta uma vez por braço."""
import database


def _clique(pedido_id, braco='estante', teste=0, **marcos):
    linha = {'pedido_id': pedido_id, 'braco': braco, 'teste': teste, 'cliques': 1, 'nome_em': None,
             'audio1_play_em': None, 'audio1_fim_em': None, 'email_em': None, 'estante_em': None,
             'audio2_play_em': None, 'checkout_em': None, 'data_pedido': None, 'data_envio_pedido': None,
             'pago_id': None}
    linha.update(marcos)
    return linha


def _banco(monkeypatch, cliques, pagos_estante, valores):
    chamadas = []

    def execute_query(sql, params=None, fetch_all=False, fetch_one=False):
        chamadas.append(sql)
        if 'UNION ALL' in sql:  # o SQL já devolve o menor pago por entrega (MIN ... GROUP BY origem)
            menores = {}
            for o, p in pagos_estante:
                menores[o] = min(menores.get(o, p), p)
            return [{'origem': o, 'pago_id': p} for o, p in menores.items()]
        if 'cp.pedido_id, cp.braco' in sql:
            return cliques
        if 'SELECT id, valor_pago FROM pedidos' in sql:
            return [{'id': i, 'valor_pago': valores[i]} for i in params]
        raise AssertionError(sql)

    monkeypatch.setattr(database.db, 'execute_query', execute_query)
    return chamadas


def test_estante_usa_o_menor_pago_entre_vinculo_e_email(monkeypatch):
    cliques = [_clique(10, email_em=1), _clique(20, email_em=1), _clique(30)]
    # 10: vínculo 105 e mesmo e-mail 103 → 103; 20: só e-mail 107; 30: nada.
    _banco(monkeypatch, cliques, [(10, 105), (10, 103), (20, 107)], {103: 10.0, 107: 17.0})
    estante = database.busca_teste_contribuicao(11, 'ini', 'fim')[0]
    assert estante['braco'] == 'estante'
    assert (estante['cliques'], estante['email'], estante['pagos'], estante['receita']) == (3, 2, 2, 27.0)


def test_mesmo_pagamento_em_duas_entregas_conta_uma_vez(monkeypatch):
    cliques = [_clique(10), _clique(20)]  # celular e computador, um pagamento só
    _banco(monkeypatch, cliques, [(10, 103), (20, 103)], {103: 10.0})
    estante = database.busca_teste_contribuicao(11, 'ini', 'fim')[0]
    assert (estante['pagos'], estante['receita']) == (1, 10.0)


def test_wpp_paga_pelo_proprio_lead_e_sem_estante_nao_busca_pagamento(monkeypatch):
    cliques = [_clique(1, braco='wpp', pago_id=1, data_pedido=1), _clique(2, braco='wpp')]
    chamadas = _banco(monkeypatch, cliques, [], {1: 10.0})
    wpp = database.busca_teste_contribuicao(11, 'ini', 'fim')[0]
    assert (wpp['braco'], wpp['cliques'], wpp['conversas'], wpp['pagos'], wpp['receita']) == ('wpp', 2, 1, 1, 10.0)
    assert not any('UNION ALL' in sql for sql in chamadas)


def test_piloto_fica_em_linha_separada_depois_do_teste(monkeypatch):
    cliques = [_clique(10, teste=1), _clique(20), _clique(1, braco='wpp')]
    _banco(monkeypatch, cliques, [(10, 103), (20, 104)], {103: 10.0, 104: 10.0})
    linhas = database.busca_teste_contribuicao(11, 'ini', 'fim')
    assert [(l['braco'], l['teste'], l['pagos']) for l in linhas] == [
        ('wpp', False, 0), ('estante', False, 1), ('estante', True, 1)]
