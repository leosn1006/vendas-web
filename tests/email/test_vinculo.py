"""
Cascata que liga o e-mail da cliente ao pedido (fluxos/email_vinculo.py).

Por que importa: com o vínculo certo a resposta é só o link da Estante; com o errado, mandamos a
Estante de outra pessoa. A regra validada na medição de 27/09/2026 é "só vale se os pedidos pagos
encontrados forem de UMA pessoa" — nome comum vira lista de candidatos para o humano.
"""
from datetime import datetime

from tests.email.conftest import pedido
from fluxos.email_vinculo import extrair_identificadores, normalizar_nome, vincular


def _vincular(**kw):
    base = dict(remetente_email='cliente@gmail.com', remetente_nome='', assunto='', corpo='', thread_id='t1')
    base.update(kw)
    return vincular(**base)


# ─── extração e normalização ────────────────────────────────────────────────

def test_extrai_pedido_email_telefone_e_cpf_do_texto():
    ids = extrair_identificadores(
        'Meu pedido #287055, comprei com maria.silva@hotmail.com, zap (61) 99999-8888, CPF 123.456.789-09. '
        'Escrevi para pudim@lsnlivros.com.br', 'cliente@gmail.com')
    assert ids['pedidos'] == [287055]
    assert ids['emails'] == ['maria.silva@hotmail.com']  # domínio próprio fica de fora
    assert '61999998888' in ids['telefones']
    assert '12345678909' in ids['cpfs']


def test_onze_digitos_sem_mascara_vira_telefone_e_cpf():
    ids = extrair_identificadores('meu numero 61999998888', 'x@y.com')
    assert '61999998888' in ids['telefones'] and '61999998888' in ids['cpfs']


def test_normalizar_nome():
    assert normalizar_nome('Rode Sousa') == ('rode sousa', 'rode', 'sousa')
    assert normalizar_nome('Sônia da Cunha') == ('sonia da cunha', 'sonia', 'cunha')
    # Uma palavra só, e-mail no lugar do nome ou dígito: não serve para busca
    assert normalizar_nome('Dora') == ('', '', '')
    assert normalizar_nome('dalmo46@bol.com.br') == ('', '', '')
    assert normalizar_nome('G3neci Urbano') == ('', '', '')


# ─── cascata ─────────────────────────────────────────────────────────────────

def test_thread_do_email_de_entrega_resolve_direto(banco):
    banco['thread'] = pedido(10, 1000, 'cliente@gmail.com')
    v = _vincular()
    assert v.metodo == 'thread' and v.pedido['id'] == 10
    assert banco['chamadas'] == ['thread']


def test_email_prefere_o_pedido_pago_as_tentativas_abandonadas(banco):
    banco['email'] = [pedido(1, 1002, 'cliente@gmail.com', data=datetime(2026, 9, 5)),
                      pedido(2, 1000, 'cliente@gmail.com', data=datetime(2026, 9, 1)),
                      pedido(3, 1002, 'cliente@gmail.com', data=datetime(2026, 9, 6))]
    v = _vincular()
    assert v.metodo == 'email' and v.pedido['id'] == 2 and v.pago


def test_email_sem_pagamento_devolve_o_nao_pago_mais_recente(banco):
    banco['email'] = [pedido(1, 1002, 'cliente@gmail.com', data=datetime(2026, 9, 5)),
                      pedido(3, 1002, 'cliente@gmail.com', data=datetime(2026, 9, 6))]
    v = _vincular()
    assert v.pedido['id'] == 3 and not v.pago


def test_numero_do_pedido_so_vale_com_o_email_do_proprio_pedido(banco):
    banco['pedidos'][4321] = pedido(4321, 1000, 'outra@gmail.com')
    v = _vincular(corpo='meu pedido #4321')
    assert v.metodo != 'numero_pedido'
    banco['pedidos'][4321] = pedido(4321, 1000, 'cliente@gmail.com')
    assert _vincular(corpo='meu pedido #4321').metodo == 'numero_pedido'


def test_nome_com_uma_pessoa_paga_vincula(banco):
    banco['nome']['primeiro_ultimo'] = [pedido(7, 0, phone='5561999990000', nome='RODE DE SOUSA SILVA')]
    v = _vincular(remetente_nome='Rode Sousa')
    assert v.metodo == 'nome' and v.pedido['id'] == 7


def test_nome_com_varias_pessoas_vira_candidatos(banco):
    banco['nome']['completo'] = [pedido(7, 1000, 'a@x.com', nome='Vera Lucia'),
                                 pedido(8, 1000, 'b@x.com', nome='Vera Lucia Souza')]
    v = _vincular(remetente_nome='Vera Lucia')
    assert v.pedido is None
    assert {c['id'] for c in v.candidatos} == {7, 8}


def test_por_nome_pedido_nao_pago_nunca_vincula(banco):
    banco['nome']['completo'] = [pedido(7, 1002, 'a@x.com', nome='Zely Dedeski')]
    v = _vincular(remetente_nome='Zely Dedeski')
    assert v.pedido is None and v.candidatos == []


def test_comprovante_so_e_lido_quando_os_passos_baratos_falham(banco):
    lidos = []

    def ler():
        lidos.append(1)
        return [{'nome_pagador': 'Italia Amendola Ribeiro'}]

    banco['email'] = [pedido(1, 1000, 'cliente@gmail.com')]
    _vincular(ler_comprovantes=ler)
    assert lidos == []  # e-mail resolveu: não gastou a leitura do comprovante (gpt-4o)

    banco['email'] = []
    banco['nome']['completo'] = [pedido(9, 0, phone='5561988887777', pagador='ITALIA AMENDOLA RIBEIRO')]
    v = _vincular(ler_comprovantes=ler)
    assert lidos == [1] and v.metodo == 'comprovante' and v.pedido['id'] == 9


def test_prefere_o_produto_do_alias_da_chave_pix(banco):
    banco['email'] = [pedido(1, 1000, 'cliente@gmail.com', produto_id=12, data=datetime(2026, 9, 9)),
                      pedido(2, 1000, 'cliente@gmail.com', produto_id=8, data=datetime(2026, 9, 1))]
    assert _vincular(produto_id=8).pedido['id'] == 2
    assert _vincular().pedido['id'] == 1
