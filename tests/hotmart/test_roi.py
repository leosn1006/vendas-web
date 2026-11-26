"""ROI separado: a Hotmart sai do PIX-web e aparece em coluna própria ("Recebido (Hotmart)"), somando no total."""
import sys
import types
from decimal import Decimal

import pytest

from tests.hotmart.test_admin import RAIZ


def test_consultas_do_roi_separam_a_hotmart_do_pix_web():
    from admin import views
    for sql in (views._SQL_ROI_REAL_WEB, views._SQL_ROI_TODOS_PRODUTOS):
        assert "WHEN metodo_pagamento IN ('cartao', 'hotmart') THEN 0 ELSE valor_pago END) AS total_web" in sql
        assert "WHEN metodo_pagamento = 'hotmart' THEN valor_pago ELSE 0 END) AS total_hotmart" in sql


@pytest.fixture
def cliente_roi(monkeypatch):
    from flask import Flask
    from flask_login import LoginManager, UserMixin
    from admin import admin_bp, views

    class Usuario(UserMixin):
        id, email, nome, primeiro_acesso = 1, 'admin@teste', 'Admin', False

        def is_admin(self):
            return True

    linha = {'id': 22, 'nome': 'Canción de Regalo', 'total_investido': Decimal('10'), 'total_pix': Decimal('0'),
             'total_web': Decimal('5'), 'total_cartao': Decimal('0'), 'total_hotmart': Decimal('14.98')}
    banco = types.SimpleNamespace(execute_query=lambda *a, **k: [dict(linha)] if k.get('fetch_all') else None)
    monkeypatch.setattr(views, 'db', banco)
    monkeypatch.setitem(sys.modules, 'database', types.SimpleNamespace(db=banco))
    monkeypatch.setattr(views, '_custo_wpp_periodo', lambda *a, **k: {})
    app = Flask(__name__, template_folder=str(RAIZ / 'app' / 'admin' / 'templates'))
    app.secret_key = 'teste'
    app.add_template_filter(lambda v: f'R$ {float(v or 0):.2f}', 'brl')
    LoginManager(app).request_loader(lambda request: Usuario())
    app.register_blueprint(admin_bp, url_prefix='/admin')
    return app.test_client()


def test_roi_de_todos_os_produtos_tem_a_coluna_hotmart_e_soma_no_total(cliente_roi):
    html = cliente_roi.get('/admin/roi-produtos?imposto=0').get_data(as_text=True)
    assert 'Recebido (Hotmart)' in html and 'R$ 14.98' in html
    # lucro = 5 (web) + 14,98 (Hotmart) − 10 investidos = 9,98
    assert '9.98' in html
