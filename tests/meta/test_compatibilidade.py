"""Cenários 41 e 42, migration, configuração e admin."""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parents[2]


# ─── Música ───────────────────────────────────────────────────────────────────

@pytest.fixture
def musica(banco):
    from musica.adaptadores.repositorio_mysql import RepositorioMysql

    def vincular(origem: dict, novo: dict) -> dict:
        origem_id = banco.pedido(produto_id=1, estado_id=1004, **origem)
        novo_id = banco.pedido(produto_id=1, estado_id=1001, **novo)
        banco.conexao.execute('INSERT INTO musicas (id, pedido_origem_id) VALUES (1, ?)', (origem_id,))
        RepositorioMysql().vincular_pedido(1, novo_id)
        return banco.ler_pedido(novo_id)
    return vincular


def test_41_pedido_novo_herda_fbc_e_campanha(musica):
    p = musica({'gclid': '', 'fbc': 'fb.1.1.AbC', 'campaignid': '123', 'adgroupid': '9'}, {'gclid': '', 'campaignid': ''})
    assert p['fbc'] == 'fb.1.1.AbC' and p['campaignid'] == '123' and p['adgroupid'] == '9'


def test_41_pedido_novo_herda_gclid_como_antes(musica):
    p = musica({'gclid': 'G1', 'campaignid': '123'}, {'gclid': '', 'campaignid': ''})
    assert p['gclid'] == 'G1' and p['campaignid'] == '123' and not p['fbc']


@pytest.mark.parametrize('clique', [{'gclid': 'G2', 'campaignid': '777'}, {'fbc': 'fb.1.1.Meu', 'campaignid': '777', 'gclid': ''}],
                         ids=['com_gclid', 'com_fbc'])
def test_41_pedido_que_ja_tem_clique_nao_muda(musica, clique):
    p = musica({'gclid': '', 'fbc': 'fb.1.1.AbC', 'campaignid': '123'}, clique)
    assert p['campaignid'] == '777' and p['fbc'] == clique.get('fbc') and p['gclid'] == clique['gclid']


def test_41_origem_sem_clique_nao_muda_nada(musica):
    p = musica({'gclid': '', 'fbc': None, 'campaignid': '123'}, {'gclid': '', 'campaignid': '777'})
    assert p['campaignid'] == '777' and not p['fbc'] and p['gclid'] == ''


# ─── Exportação do Google ─────────────────────────────────────────────────────

class _Aba:
    def __init__(self):
        self.linhas = []

    def row_values(self, _):
        return ['cabeçalho']

    def append_rows(self, linhas, value_input_option=None):
        self.linhas.extend(linhas)


@pytest.fixture
def exportar(monkeypatch, banco):
    from fluxos import fluxo_upload_google_ads as fluxo
    aba = _Aba()
    planilha = SimpleNamespace(worksheet=lambda nome: aba)
    monkeypatch.setenv('GOOGLE_SA_TESTE', '{}')
    monkeypatch.setattr(fluxo.Credentials, 'from_service_account_info', lambda *a, **k: None)
    monkeypatch.setattr(fluxo.gspread, 'authorize', lambda c: SimpleNamespace(open_by_key=lambda i: planilha))
    banco.conexao.execute(
        """INSERT INTO google_ads_planilha_dns (produto_id, dns, google_sheets_spreadsheet_id, google_sheets_sheet_name,
                                                google_ads_conversion_name, google_sa_env_var)
           VALUES (1, 'site.com', 'PLAN', 'Aba', 'compra', 'GOOGLE_SA_TESTE')""")

    def rodar():
        fluxo.exportar_para_google_sheets()
        return aba.linhas
    return rodar


def test_42_pedido_com_gclid_sai_igual(banco, exportar):
    banco.campanha('123', plataforma='google')
    pid = banco.pedido(produto_id=1, estado_id=1000, valor_pago=47.9, gclid='G1', campaignid='123', dns_origem='site.com',
                       data_pagamento='2026-10-30 12:00:00')
    assert exportar() == [['G1', 'compra', '2026-10-30 12:00:00 America/Sao_Paulo', '47.90', 'BRL', '', '']]
    assert banco.ler_pedido(pid)['data_envio_google_ads'] is not None


def test_42_pedido_da_meta_sem_gclid_nao_sai(banco, exportar):
    banco.campanha('123', plataforma='meta')
    pid = banco.pedido(produto_id=1, estado_id=1000, valor_pago=47.9, gclid='', fbc='fb.1.1.AbC', campaignid='123',
                       dns_origem='site.com', data_pagamento='2026-10-30 12:00:00')
    assert exportar() == []
    assert banco.ler_pedido(pid)['data_envio_google_ads'] is None


# ─── Migration e configuração ─────────────────────────────────────────────────

def test_migration_cobre_o_esquema_e_e_idempotente():
    sql = (RAIZ / 'migrations' / '099_conversoes_meta.sql').read_text(encoding='utf-8')
    for coluna in ('fbc', 'client_ip', 'client_user_agent', 'data_envio_meta', 'plataforma'):
        assert f'ADD COLUMN {coluna} ' in sql
    assert "DEFAULT ''google''" in sql
    assert 'CREATE TABLE IF NOT EXISTS meta_dataset_dns' in sql and 'UNIQUE KEY uk_produto_dns (produto_id, dns)' in sql
    assert sql.count('information_schema') == 3 and sql.count('ALTER TABLE') == 3


def test_variaveis_so_no_worker_baixa():
    compose = (RAIZ / 'docker-compose.yml').read_text(encoding='utf-8')
    servico = re.search(r'\n  worker-baixa:\n(.*?)\n  [\w-]+:\n', compose, re.S).group(1)
    assert 'META_TOKEN_LSN=${META_TOKEN_LSN:-}' in servico and 'META_TEST_EVENT_CODE=${META_TEST_EVENT_CODE:-}' in servico
    assert compose.count('META_TOKEN_LSN=') == 1
    exemplo = (RAIZ / '.env.example').read_text(encoding='utf-8')
    assert 'META_TOKEN_LSN=' in exemplo and 'META_TEST_EVENT_CODE=' in exemplo


# ─── Admin ────────────────────────────────────────────────────────────────────

@pytest.fixture
def admin(monkeypatch, banco):
    """As views do admin no blueprint de verdade, com o usuário simulado (os decoradores têm os próprios testes)."""
    from flask import Flask
    from flask_login import LoginManager, UserMixin
    from admin import admin_bp, views

    class Usuario(UserMixin):
        id, email, nome = 1, 'admin@teste', 'Admin'

        def __init__(self, eh_admin=True):
            self.eh_admin = eh_admin

        def is_admin(self):
            return self.eh_admin

    app = Flask(__name__, template_folder=str(RAIZ / 'app' / 'admin' / 'templates'))
    app.secret_key = 'teste'
    usuario = Usuario()
    LoginManager(app).request_loader(lambda request: usuario)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    monkeypatch.setattr(views, 'db', banco)
    return SimpleNamespace(app=app, views=views, usuario=usuario)


@pytest.mark.parametrize('form', [
    {'dns': 'site.com', 'dataset_id': '12a', 'token_env_var': 'META_TOKEN_LSN'},
    {'dns': 'site.com', 'dataset_id': '123', 'token_env_var': 'SECRET_KEY'},
    {'dns': '', 'dataset_id': '123', 'token_env_var': 'META_TOKEN_LSN'},
], ids=['dataset_com_letra', 'outra_variavel', 'sem_dns'])
def test_admin_recusa_dataset_invalido(banco, admin, form):
    with admin.app.test_request_context('/', method='POST', data=form):
        admin.views.adicionar_conversao_meta.__wrapped__(1)
    assert banco.contar('meta_dataset_dns') == 0


def test_admin_adiciona_alterna_e_remove_dataset(banco, admin):
    form = {'dns': ' Site.com ', 'dataset_id': '123', 'token_env_var': 'META_TOKEN_LSN'}
    with admin.app.test_request_context('/', method='POST', data=form):
        admin.views.adicionar_conversao_meta.__wrapped__(1)
    linha = banco.execute_query('SELECT * FROM meta_dataset_dns', fetch_one=True)
    assert linha['dns'] == 'site.com' and linha['ativo'] == 1

    with admin.app.test_request_context('/', method='POST'):
        admin.views.alternar_conversao_meta.__wrapped__(2, linha['id'])  # de outro produto: nada muda
        assert banco.execute_query('SELECT ativo FROM meta_dataset_dns', fetch_one=True)['ativo'] == 1
        admin.views.alternar_conversao_meta.__wrapped__(1, linha['id'])
        assert banco.execute_query('SELECT ativo FROM meta_dataset_dns', fetch_one=True)['ativo'] == 0
        admin.views.remover_conversao_meta.__wrapped__(1, linha['id'])
    assert banco.contar('meta_dataset_dns') == 0


def test_admin_altera_a_plataforma_da_campanha(banco, admin):
    banco.campanha('123', nome='Nome', plataforma='google')
    form = {'campaignid': '123', 'nome': 'Nome', 'plataforma': 'meta'}
    with admin.app.test_request_context('/', method='POST', data=form):
        admin.views.salvar_campanha.__wrapped__(1)
    assert banco.ler_campanha('123')['plataforma'] == 'meta'


def test_admin_recusa_plataforma_desconhecida(banco, admin):
    banco.campanha('123', nome='Nome', plataforma='google')
    form = {'campaignid': '123', 'nome': 'Outro', 'plataforma': 'tiktok'}
    with admin.app.test_request_context('/', method='POST', data=form):
        admin.views.salvar_campanha.__wrapped__(1)
    assert banco.ler_campanha('123')['nome'] == 'Nome'


def test_acoes_de_dataset_so_para_admin():
    fonte = (RAIZ / 'app' / 'admin' / 'views.py').read_text(encoding='utf-8')
    for funcao in ('adicionar_conversao_meta', 'alternar_conversao_meta', 'remover_conversao_meta'):
        assert re.search(rf"@requer_admin\ndef {funcao}\(", fonte)


@pytest.mark.parametrize('eh_admin, tem_formulario', [(True, True), (False, False)])
def test_tela_de_conversoes_meta_renderiza(banco, admin, monkeypatch, eh_admin, tem_formulario):
    banco.dataset(dns='site.com', dataset_id='555')
    monkeypatch.setattr(admin.views, '_get_produto_or_redirect', lambda pid: {'id': pid, 'nome': 'Produto'})
    admin.usuario.eh_admin = eh_admin
    with admin.app.test_request_context('/admin/produto/1/conversoes-meta'):
        html = admin.views.conversoes_meta_produto.__wrapped__(1)
    assert 'site.com' in html and '555' in html and 'META_TOKEN_LSN' in html
    assert ('Adicionar dataset' in html) is tem_formulario and ('Remover' in html) is tem_formulario


def test_tela_de_campanhas_tem_o_seletor_de_plataforma(banco, admin, monkeypatch):
    banco.campanha('123', plataforma='meta')
    banco.pedido(produto_id=1, estado_id=1, campaignid='123')
    monkeypatch.setattr(admin.views, '_get_produto_or_redirect', lambda pid: {'id': pid, 'nome': 'Produto'})
    with admin.app.test_request_context('/admin/produto/1/campanhas'):
        html = admin.views.campanhas_produto.__wrapped__(1)
    assert 'name="plataforma"' in html and '<option value="meta" selected>' in html
