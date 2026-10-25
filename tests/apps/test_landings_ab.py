"""Teste A/B das landings do Fatia: /fatia-e (quiz, página "fatia2-e") x /fatia1-e (site anterior, "fatia1-e")."""
from decimal import Decimal

from admin import views


def linha(pagina, etapa, visitas, pagos=0, receita='0', plano='Fatias que Vendem', padrao=1):
    return {'pagina': pagina, 'etapa': etapa, 'visitas': Decimal(visitas), 'pagos': Decimal(pagos),
            'receita': Decimal(receita), 'plano': plano, 'padrao': padrao}


def test_ab_soma_visitas_checkout_pagos_e_planos_por_pagina():
    linhas = [
        linha('fatia1-e', 0, 50),                                    # abriu e saiu
        linha('fatia1-e', 1, 20),                                    # viu a oferta
        linha('fatia1-e', 2, 6, pagos=3, receita='30.00'),           # foi ao checkout do Básico
        linha('fatia1-e', 5, 2, pagos=2, receita='30.00', plano='Completo', padrao=0),  # aceitou o popup
        linha('fatia1-e', 3, 4),                                     # viu o popup e saiu: não é checkout
        linha('fatia1-e', 6, 1),                                     # fechou o popup e foi ao checkout
        linha('fatia2-e', 16, 30),
        linha('fatia2-e', 17, 10, pagos=1, receita='10.00'),
    ]
    a, b = views._montar_ab_landings(linhas)
    assert a['pagina'] == 'fatia1-e' and b['pagina'] == 'fatia2-e'
    assert (a['visitas'], a['checkout'], a['pagos'], a['receita']) == (83, 9, 5, 60.0)
    assert a['conversao'] == round(100 * 5 / 83, 2) and a['ticket'] == 12.0
    assert a['planos'] == [('Fatias que Vendem', 3), ('Completo', 2)]   # o padrão primeiro
    assert (b['visitas'], b['checkout'], b['pagos']) == (40, 10, 1)


def test_ab_sem_dados():
    assert views._montar_ab_landings([]) == []


def test_funil_do_site_anterior_tem_nome_em_todas_as_etapas_e_as_de_compra_marcadas():
    quiz, = views._montar_etapas_quiz([{'pagina': 'fatia1-e', 'etapa': 2, 'pararam': 3, 'pagos': 1, 'etapa_nome': ''}])
    assert [e['etapa_nome'] for e in quiz['etapas']][:3] == ['Abriu a página', 'Viu a oferta', 'Clicou em comprar']
    assert len(quiz['etapas']) == 7
    assert {e['etapa'] for e in quiz['etapas'] if e['compra']} == {2, 4, 5, 6}   # 6 = depois do popup


def test_funil_da_musica_so_tem_as_etapas_que_existem():
    """A Música numera com saltos (quiz 1–9, letra 20, prévia 30, compra 40–43): nada de linhas vazias 10–19..."""
    quiz, = views._montar_etapas_quiz([
        {'pagina': 'musica-v2', 'etapa': 2, 'pararam': 5, 'pagos': 0, 'etapa_nome': 'pessoas'},
        {'pagina': 'musica-v2', 'etapa': 30, 'pararam': 4, 'pagos': 0, 'etapa_nome': 'previa'},
        {'pagina': 'musica-v2', 'etapa': 43, 'pararam': 1, 'pagos': 1, 'etapa_nome': 'ultima_aceitou'}])
    assert [e['etapa'] for e in quiz['etapas']] == [*range(1, 10), 20, 30, 40, 41, 42, 43, 44]
    nomes = {e['etapa']: e['etapa_nome'] for e in quiz['etapas']}
    assert nomes[2] == 'Quiz: nome' and nomes[3] == 'Quiz: ocasião' and nomes[30] == 'Ouviu a prévia'
    assert {e['etapa'] for e in quiz['etapas'] if e['compra']} == {40, 42, 43, 44}
    assert not quiz['abriu_pagina']
    assert quiz['etapas'][0]['chegaram'] == 10 and next(e for e in quiz['etapas'] if e['etapa'] == 30)['chegaram'] == 5


class Requisicao:
    def __init__(self, args, cookie='77'):
        self.args, self.cookies, self.headers, self.host = args, {'pedido_web_12': cookie}, {}, 'localhost'


def test_volta_por_outro_anuncio_vale_o_ultimo_clique(monkeypatch):
    """Mesmo cookie (/fatia-e e /fatia1-e), anúncio novo: o rascunho passa a ter o gclid do último clique."""
    import importlib
    import database
    checkout = importlib.import_module('web.checkout')
    atualizados = []
    monkeypatch.setattr(database, 'get_pedido_nao_finalizado', lambda pid, prod: {'id': pid, 'estado_id': 1004, 'gclid': 'A'})
    monkeypatch.setattr(database, 'avancar_pedido_web', lambda *a: None)
    monkeypatch.setattr(database, 'atualizar_campanha_rascunho', lambda pid, **k: atualizados.append((pid, k['gclid'])))
    assert checkout.rastrear_visita_funil(Requisicao({'gclid': 'B', 'gad_campaignid': '9'}), 12, 1004) == 77
    assert atualizados == [(77, 'B')]
    checkout.rastrear_visita_funil(Requisicao({'gclid': 'A'}), 12, 1003)   # mesmo clique: nada muda
    checkout.rastrear_visita_funil(Requisicao({}), 12, 1003)               # sem gclid (navegou): mantém
    assert atualizados == [(77, 'B')]


def test_nomes_das_telas_da_musica_seguem_a_ordem_do_quiz():
    """O quiz manda a posição fixa da pergunta (quiz.html): reordenar PERGUNTAS exige renomear _ETAPAS_MUSICA."""
    from musica.dominio.quiz import PERGUNTAS
    esperado = ['para_quem', 'pessoas', 'ocasiao', 'lembrancas', 'frase_obrigatoria', 'clima', 'estilo', 'voz', 'contato']
    assert [p['chave'] for p in PERGUNTAS] == esperado
    assert all(views._ETAPAS_MUSICA[n].startswith('Quiz:') for n in range(1, len(PERGUNTAS) + 1))
