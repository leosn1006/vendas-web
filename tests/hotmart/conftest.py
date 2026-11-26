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
        self.conciliacoes = []
        self.musica_do_pedido = {}           # pedido_id -> musica_id (musica_pedidos)

    # avisos
    def registrar_evento(self, evento_id, transacao, evento, payload):
        if evento_id not in self.eventos:
            self.eventos[evento_id] = {'id': len(self.eventos) + 1, 'evento_id': evento_id, 'transacao': transacao,
                                       'evento': evento, 'resultado': 'processando', 'detalhe': None,
                                       'payload': copy.deepcopy(payload)}
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

    def aprovado_gravado(self, transacao):
        return self.pagamentos.get(transacao, {}).get('aprovado_em')

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

    # conciliação
    def pagamento_com_pedido(self, transacao):
        if transacao not in self.pagamentos:
            return None
        linha = dict(self.pagamentos[transacao])
        pedido = self.pedidos.get(linha.get('pedido_id')) or {}
        return {**linha, 'pedido_guid': pedido.get('guid'), 'pedido_estado': pedido.get('estado_id'),
                'pedido_metodo': pedido.get('metodo_pagamento'), 'pedido_email': pedido.get('email'),
                'pedido_entregue_em': pedido.get('data_envio_ebook'), 'pedido_pago_em': pedido.get('data_pagamento')}

    def salvar_conciliacao(self, transacao, campos, divergencia):
        from hotmart.repositorio import _CAMPOS_API
        self.pagamentos[transacao].update({c: campos.get(c) for c in _CAMPOS_API}, divergencia=divergencia,
                                          conciliado_em='agora')

    def iniciar_conciliacao(self, origem, de, ate):
        self.conciliacoes.append({'origem': origem, 'fim': None})
        return len(self.conciliacoes)

    def finalizar_conciliacao(self, execucao_id, vendas_api, novas, confirmadas, divergentes, reentregas, erro):
        self.conciliacoes[execucao_id - 1].update(fim='agora', vendas_api=vendas_api, novas=novas,
                                                  confirmadas=confirmadas, divergentes=divergentes,
                                                  reentregas=reentregas, erro=erro)

    def tem_aviso_a_conferir(self, transacao):
        return any(e['transacao'] == transacao and e['resultado'] in ('sem_pedido', 'oferta_divergente', 'duplicado', 'erro')
                   for e in self.eventos.values())

    def evento_por_id(self, evento_db_id):
        return next((dict(e) for e in self.eventos.values() if e['id'] == evento_db_id), None)

    def liberar_para_reprocessar(self, evento_id):
        if self.eventos[evento_id]['resultado'] not in ('sem_pedido', 'oferta_divergente', 'erro'):
            return False
        self.eventos[evento_id]['resultado'] = None
        return True

    def outra_compra_paga(self, pedido_id, transacao, aprovado_em):
        return next((t for t, pg in self.pagamentos.items() if pg.get('pedido_id') == pedido_id and t != transacao
                     and pg.get('status') in ('APPROVED', 'COMPLETE') and not pg.get('order_bump')
                     and (not pg.get('aprovado_em') or not aprovado_em or pg['aprovado_em'] <= aprovado_em)), None)

    def outro_pedido_pago_da_musica(self, pedido_id):
        musica = self.musica_do_pedido.get(pedido_id)
        return next((p for p, m in self.musica_do_pedido.items() if m == musica and p != pedido_id
                     and self.pedidos.get(p, {}).get('estado_id') == 1000), None) if musica else None

    def preencher_email_se_vazio(self, pedido_id, email):
        if email and not self.pedidos[pedido_id].get('email'):
            self.pedidos[pedido_id]['email'] = email

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
                 'fonte_taxa_gravada', 'corrigir_valor_pendente', 'pagamento_com_pedido', 'salvar_conciliacao',
                 'iniciar_conciliacao', 'finalizar_conciliacao', 'evento_por_id', 'liberar_para_reprocessar',
                 'tem_aviso_a_conferir', 'preencher_email_se_vazio', 'outra_compra_paga',
                 'outro_pedido_pago_da_musica', 'aprovado_gravado'):
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
