"""Tela Admin → Hotmart: as quatro abas renderizam com dados, o salvar oferta grava e um POST de fora é recusado."""
import datetime
import sys
import types
from decimal import Decimal
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
AGORA = datetime.datetime(2026, 11, 26, 10, 0)

VENDA = {
    'transacao': 'HP0277856500', 'pedido_id': 7, 'guid': 'hmtteste', 'produto_id': 50, 'produto': 'Canción',
    'pedido_estado': 1000, 'aprovado_em': AGORA, 'criado_em': AGORA, 'pais': 'MX', 'tipo_pagamento': 'CREDIT_CARD',
    'valor': Decimal('50'), 'valor_cheio': Decimal('58'), 'moeda': 'MXN', 'api_total': Decimal('58'),
    'api_iva': Decimal('8'), 'api_moeda_iva': 'MXN', 'valor_brl': Decimal('14.98'), 'fonte_taxa': 'bce',
    'liquido': Decimal('2.01'), 'moeda_liquido': 'USD', 'liquido_brl': Decimal('11.69'),
    'api_taxa_percentual': Decimal('20'), 'api_taxa': Decimal('0.5'), 'api_moeda_taxa': None, 'taxa_hotmart': None,
    'moeda_taxa': None, 'api_status': 'APPROVED', 'status': 'APPROVED', 'modelo_fiscal': 'A',
    'previsao_repasse': datetime.date(2026, 12, 10), 'liberado_em': None, 'divergencia': 'status: API REFUNDED × webhook APPROVED',
    'conciliado_em': AGORA,
}


class BancoFalso:
    def __init__(self):
        self.ofertas_gravadas = []
        self.botao_limpo = []
        self.resolvidos = []

    def execute_query(self, sql, params=(), fetch_one=False, fetch_all=False, return_rowcount=False):
        sql = ' '.join(sql.split())
        if sql.startswith("UPDATE pagamento_hotmart_eventos SET resultado = 'resolvido'"):
            self.resolvidos.append(params[0])
            return 1
        if sql.startswith("UPDATE hotmart_ofertas SET uso = NULL"):
            self.botao_limpo.append(params)
            return 0
        if sql.startswith('INSERT INTO hotmart_ofertas'):
            self.ofertas_gravadas.append(params)
            return 1
        if 'AS n' in sql:
            return {'n': 3}
        if sql.startswith('SELECT id, produto_id FROM produto_planos'):
            return {'id': params[0], 'produto_id': 50} if params[0] == 501 else None
        if 'AS vendas, COALESCE(SUM(CASE' in sql:
            return {'vendas': 1, 'total_brl': Decimal('14.98'), 'liquido_brl': Decimal('11.69'),
                    'taxa_media': Decimal('20'), 'aguardando': 0, 'canceladas': 0, 'devolvidas': 0, 'divergentes': 1}
        if 'GROUP BY ph.moeda' in sql:
            return [{'moeda': 'MXN', 'total': Decimal('58'), 'vendas': 1}]
        if 'SELECT ph.*' in sql:
            return [dict(VENDA)]
        if 'FROM hotmart_conciliacoes' in sql:
            return [{'inicio': AGORA, 'fim': AGORA, 'origem': 'beat', 'vendas_api': 1, 'novas': 0, 'confirmadas': 0,
                     'divergentes': 1, 'erro': None}]
        if 'FROM pagamento_hotmart_eventos WHERE resultado IN' in sql:
            return [{'id': 9, 'evento_id': 'evt-9', 'transacao': 'HP1', 'evento': 'PURCHASE_APPROVED',
                     'resultado': 'oferta_divergente', 'detalhe': "oferta 'X' não cadastrada", 'recebido_em': AGORA,
                     'payload': '{"id": "evt-9"}'}]
        if "fonte_taxa = 'pendente'" in sql:
            return []
        if 'FROM hotmart_ofertas o' in sql:
            return [{'codigo': 'sph9o75s', 'produto_id': 50, 'plano_id': 501, 'descricao': 'Teste', 'ativo': 1,
                     'produto': 'Canción', 'plano': 'Música', 'slug': 'musica', 'produto_hotmart': 9006872,
                     'preco': Decimal('50'), 'moeda': 'MXN', 'uso': 'botao'}]
        if 'FROM produto_planos pl JOIN produtos' in sql:
            return [{'id': 501, 'nome': 'Música', 'slug': 'musica', 'produto_id': 50, 'produto': 'Canción'}]
        return [] if fetch_all else None


@pytest.fixture
def tela(monkeypatch):
    from flask import Flask
    from flask_login import LoginManager, UserMixin
    from admin import admin_bp
    from hotmart import api

    class Usuario(UserMixin):
        id, email, nome, primeiro_acesso = 1, 'admin@teste', 'Admin', False

        def is_admin(self):
            return True

    banco = BancoFalso()
    monkeypatch.setitem(sys.modules, 'database', types.SimpleNamespace(db=banco))
    monkeypatch.setattr(api, 'configurada', lambda: True)
    app = Flask(__name__, template_folder=str(RAIZ / 'app' / 'admin' / 'templates'))
    app.secret_key = 'teste'
    app.add_template_filter(lambda v: f'R$ {float(v or 0):.2f}', 'brl')
    LoginManager(app).request_loader(lambda request: Usuario())
    app.register_blueprint(admin_bp, url_prefix='/admin')
    return types.SimpleNamespace(cliente=app.test_client(), banco=banco)


@pytest.mark.parametrize('aba, espera', [
    ('vendas', ['Vendas pagas', '58.00 MXN', '20.0%', 'nota: modelo A', 'Estante']),
    ('conciliacao', ['Conciliar agora', 'status: API REFUNDED', 'automática']),
    ('conferir', ['oferta divergente', 'Reprocessar', 'evt-9']),
    ('ofertas', ['sph9o75s', 'Canción — Música', 'Nova oferta']),
])
def test_abas_renderizam(tela, aba, espera):
    resp = tela.cliente.get(f'/admin/hotmart?aba={aba}')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for trecho in espera:
        assert trecho in html, trecho
    assert 'Para conferir (3)' in html


def test_salvar_oferta_grava_com_o_produto_do_plano(tela):
    resp = tela.cliente.post('/admin/hotmart/ofertas', headers={'Origin': 'http://localhost'},
                             data={'codigo': ' tlaz6ojn ', 'plano_id': '501', 'descricao': 'Preço base', 'ativo': '1',
                                   'uso': 'botao', 'produto_hotmart': '9006872', 'preco': '149,00', 'moeda': 'mxn'})
    assert resp.status_code == 302
    assert tela.banco.ofertas_gravadas == [('tlaz6ojn', 50, 501, 'Preço base', 1, 9006872, Decimal('149.00'), 'MXN',
                                            'botao')]
    assert tela.banco.botao_limpo == [(501, 'tlaz6ojn')]          # a oferta anterior do botão do plano sai


def test_oferta_de_botao_sem_preco_nao_grava(tela):
    tela.cliente.post('/admin/hotmart/ofertas', headers={'Origin': 'http://localhost'},
                      data={'codigo': 'x', 'plano_id': '501', 'uso': 'botao', 'produto_hotmart': '9006872'})
    assert tela.banco.ofertas_gravadas == []


def test_post_de_outro_site_e_recusado(tela):
    tela.cliente.post('/admin/hotmart/ofertas', headers={'Origin': 'https://outro.site'},
                      data={'codigo': 'x', 'plano_id': '501'})
    assert tela.banco.ofertas_gravadas == []


def test_plano_inexistente_nao_grava(tela):
    tela.cliente.post('/admin/hotmart/ofertas', headers={'Origin': 'http://localhost'},
                      data={'codigo': 'x', 'plano_id': '999'})
    assert tela.banco.ofertas_gravadas == []


def test_conciliar_agora_agenda_no_worker(tela, monkeypatch):
    from hotmart import tarefas
    agendadas = []
    monkeypatch.setitem(sys.modules, 'celery_app', types.SimpleNamespace())
    monkeypatch.setattr(tarefas.conciliar, 'delay', lambda origem: agendadas.append(origem))
    resp = tela.cliente.post('/admin/hotmart/conciliar', headers={'Origin': 'http://localhost'})
    assert resp.status_code == 302 and agendadas == ['botao']


def test_conciliar_agora_sem_credencial_avisa_e_nao_agenda(tela, monkeypatch):
    from hotmart import api, tarefas
    agendadas = []
    monkeypatch.setattr(api, 'configurada', lambda: False)
    monkeypatch.setattr(tarefas.conciliar, 'delay', lambda origem: agendadas.append(origem))
    resp = tela.cliente.post('/admin/hotmart/conciliar', headers={'Origin': 'http://localhost'}, follow_redirects=True)
    assert agendadas == [] and 'não está configurada' in resp.get_data(as_text=True)


def test_oferta_desativada_nao_tira_o_botao_da_atual(tela):
    tela.cliente.post('/admin/hotmart/ofertas', headers={'Origin': 'http://localhost'},
                      data={'codigo': 'nova', 'plano_id': '501', 'uso': 'botao', 'produto_hotmart': '9006872',
                            'preco': '149', 'moeda': 'MXN', 'ativo': '0'})
    assert len(tela.banco.ofertas_gravadas) == 1 and tela.banco.botao_limpo == []


def test_moeda_desconhecida_nao_grava(tela):
    tela.cliente.post('/admin/hotmart/ofertas', headers={'Origin': 'http://localhost'},
                      data={'codigo': 'x', 'plano_id': '501', 'uso': 'botao', 'produto_hotmart': '9006872',
                            'preco': '149', 'moeda': 'MX'})
    assert tela.banco.ofertas_gravadas == []


def test_duplicado_tem_o_botao_resolvido_e_nao_o_reprocessar(tela, monkeypatch):
    original = tela.banco.execute_query

    def com_duplicado(sql, params=(), **kw):
        if ' '.join(sql.split()).startswith('SELECT id, evento_id'):
            return [{'id': 5, 'evento_id': 'e5', 'transacao': 'HPB', 'evento': 'PURCHASE_APPROVED',
                     'resultado': 'duplicado', 'detalhe': 'reembolsar a HPB', 'recebido_em': AGORA, 'payload': '{}'}]
        return original(sql, params, **kw)

    monkeypatch.setattr(tela.banco, 'execute_query', com_duplicado)
    html = tela.cliente.get('/admin/hotmart?aba=conferir').get_data(as_text=True)
    assert 'Resolvido' in html and 'eventos/5/reprocessar' not in html
    tela.cliente.post('/admin/hotmart/eventos/5/resolvido', headers={'Origin': 'http://localhost'})
    assert tela.banco.resolvidos == [5]
