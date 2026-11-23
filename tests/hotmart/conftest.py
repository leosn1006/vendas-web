"""Hotmart: imports como no container (app/ na raiz) e um repositório em memória no lugar do SQL."""
import copy
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'app'))

import pytest  # noqa: E402

HOTTOK = 'segredo-de-teste'


class RepositorioFalso:
    """As funções de hotmart.repositorio, em memória."""

    ESTADO_AGUARDANDO = 1010
    ESTADO_CANCELADO = 1011

    def __init__(self):
        self.eventos, self.pagamentos, self.ofertas, self.pedidos = {}, {}, {}, {}
        self.taxas = {}

    # avisos
    def registrar_evento(self, evento_id, transacao, evento, payload):
        if evento_id not in self.eventos:
            self.eventos[evento_id] = {'transacao': transacao, 'evento': evento, 'resultado': 'processando',
                                       'detalhe': None}
            return True
        evento_gravado = self.eventos[evento_id]
        if evento_gravado['resultado'] in (None, 'erro'):   # 'processando' antigo: o relógio dos testes não anda
            evento_gravado['resultado'] = 'processando'
            return True
        return False

    def marcar_resultado_evento(self, evento_id, resultado, detalhe=''):
        self.eventos[evento_id].update(resultado=resultado, detalhe=detalhe)

    # compra (mesma regra do ON DUPLICATE KEY: o que já foi gravado vence um campo nulo)
    def salvar_pagamento(self, dados):
        from hotmart.repositorio import _CAMPOS, _MANTER_SE_NULO
        atual = self.pagamentos.setdefault(dados['transacao'], {})
        for c in _CAMPOS:
            novo = dados.get(c)
            if c in _MANTER_SE_NULO and novo is None and c in atual:
                continue
            atual[c] = novo

    def marcar_liberado(self, transacao):
        self.pagamentos[transacao].setdefault('liberado_em', 'agora')

    def fonte_taxa_gravada(self, transacao):
        return self.pagamentos.get(transacao, {}).get('fonte_taxa')

    def corrigir_valor_pendente(self, pedido_id, valor_brl, liquido_brl):
        p = self.pedidos[pedido_id]
        if valor_brl is None or p['estado_id'] != 1000 or p.get('metodo_pagamento') != 'hotmart':
            return False
        p['valor_pago'] = valor_brl
        if liquido_brl is not None:
            p['valor_liquido_pagamento'] = liquido_brl
        return True

    def ultima_taxa(self, moeda):
        return self.taxas.get(moeda)

    def oferta(self, codigo):
        return self.ofertas.get(codigo)

    # pedido
    def pedido_por_guid(self, guid):
        return next((copy.deepcopy(p) for p in self.pedidos.values() if p['guid'] == guid), None)

    def confirmar_pedido(self, pedido_id, valor, nome, valor_liquido, data_repasse):
        p = self.pedidos[pedido_id]
        if p['estado_id'] == 1000:
            return False
        p.update(estado_id=1000, valor_pago=valor, nome_pagador=nome, valor_liquido_pagamento=valor_liquido,
                 data_repasse=data_repasse, metodo_pagamento='hotmart')
        return True

    def mudar_estado_se_nao_pago(self, pedido_id, estado):
        from hotmart.repositorio import ESTADOS_ANTES_DO_PAGAMENTO
        p = self.pedidos[pedido_id]
        if p.get('fluxo_inicial') != 'web' or p['estado_id'] not in ESTADOS_ANTES_DO_PAGAMENTO:
            return False
        p['estado_id'] = estado
        return True


@pytest.fixture
def repo(monkeypatch):
    from hotmart import repositorio, servico
    falso = RepositorioFalso()
    for nome in ('registrar_evento', 'marcar_resultado_evento', 'salvar_pagamento', 'marcar_liberado',
                 'ultima_taxa', 'oferta', 'pedido_por_guid', 'confirmar_pedido', 'mudar_estado_se_nao_pago',
                 'fonte_taxa_gravada', 'corrigir_valor_pendente'):
        monkeypatch.setattr(repositorio, nome, getattr(falso, nome))
    falso.pedidos[7] = {'id': 7, 'guid': 'abc123', 'produto_id': 50, 'plano_id': 501, 'estado_id': 1001,
                        'valor_pago': None, 'fluxo_inicial': 'web'}
    falso.ofertas['OFMUSICA'] = {'codigo': 'OFMUSICA', 'produto_id': 50, 'plano_id': 501, 'ativo': 1}
    falso.ofertas['OFVIDEO'] = {'codigo': 'OFVIDEO', 'produto_id': 50, 'plano_id': 502, 'ativo': 1}
    falso.entregas = []
    monkeypatch.setattr(servico, 'enfileirar_entrega', falso.entregas.append)
    falso.cotacoes = {'MXN': {'valor': 0.30}}
    monkeypatch.setattr(servico, '_ptax', lambda moeda: falso.cotacoes.get(moeda))
    return falso


@pytest.fixture
def cliente(repo, monkeypatch):
    from flask import Flask
    from hotmart import config
    from hotmart.rotas import bp
    monkeypatch.setattr(config, 'HOTTOK', HOTTOK)
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app.test_client()


def aviso(evento='PURCHASE_APPROVED', id_='evt-1', transacao='HP111', xcod='abc123', oferta='OFMUSICA',
          valor=599.0, moeda='MXN', liquido=520.0, moeda_liquido='MXN', conversao=None, status='APPROVED',
          tipo='CREDIT_CARD', order_bump=False, aprovado_ms=1763647200000):
    produtor = {'value': liquido, 'currency_value': moeda_liquido, 'source': 'PRODUCER'}
    if conversao:
        produtor['currency_conversion'] = conversao
    compra = {
        'transaction': transacao, 'status': status, 'offer': {'code': oferta},
        'price': {'value': valor, 'currency_value': moeda}, 'full_price': {'value': valor, 'currency_value': moeda},
        'payment': {'type': tipo}, 'checkout_country': {'iso': 'MX', 'name': 'Mexico'},
        'order_bump': {'is_order_bump': order_bump, 'parent_purchase_transaction': 'HP000' if order_bump else None},
    }
    if xcod is not None:
        compra['origin'] = {'xcod': xcod}
    if aprovado_ms:
        compra['approved_date'] = aprovado_ms
    return {
        'id': id_, 'creation_date': 1763647200000, 'event': evento, 'version': '2.0.0',
        'data': {
            'product': {'id': 999, 'name': 'Canción de Regalo'},
            'buyer': {'email': 'cliente@exemplo.com', 'name': 'María López'},
            'purchase': compra,
            'commissions': [{'value': 79.0, 'currency_value': moeda, 'source': 'MARKETPLACE'}, produtor],
        },
    }


D = Decimal
