"""Cenários 35 a 40: investimento lido da Meta e gravado na tabela do Google."""
import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from fluxos import fluxo_orcamento_meta as fluxo
from fluxos.fluxo_orcamento_meta import processar_orcamento_meta


class Resposta:
    def __init__(self, corpo, status=200):
        self.corpo, self.status_code = corpo, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code}')

    def json(self):
        return self.corpo


def linha(campanha='123', data='2026-10-30', moeda='BRL', spend='12.34', nome='Campanha Bonita', **extras):
    return {'campaign_id': campanha, 'campaign_name': nome, 'spend': spend, 'inline_link_clicks': '5',
            'impressions': '100', 'account_currency': moeda, 'date_start': data, **extras}


@pytest.fixture
def meta(monkeypatch):
    """API simulada: `contas[token]` lista as contas; `insights[conta]` é a lista de páginas de cada conta."""
    class Estado:
        contas, insights, chamadas = {}, {}, []

    estado = Estado()
    estado.contas, estado.insights, estado.chamadas = {}, {}, []

    def get(url, headers=None, params=None, timeout=None):
        token = headers['Authorization'].removeprefix('Bearer ')
        estado.chamadas.append({'url': url, 'token': token, 'params': dict(params)})
        caminho = url.removeprefix('https://meta.teste/v24.0/')
        if caminho == 'me/adaccounts':
            contas = estado.contas[token]
            if isinstance(contas, Exception):
                raise contas
            return Resposta({'data': [{'id': c} for c in contas]})
        conta = caminho.removesuffix('/insights')
        paginas = estado.insights[conta]
        if isinstance(paginas, Exception):
            raise paginas
        indice = int(params.get('after', 0))
        corpo = {'data': paginas[indice]}
        if indice + 1 < len(paginas):
            corpo['paging'] = {'cursors': {'after': str(indice + 1)}, 'next': f'https://meta.teste/next?access_token={token}'}
        return Resposta(corpo)

    monkeypatch.setattr(fluxo.requests, 'get', get)
    monkeypatch.setattr(fluxo.config, 'WHATSAPP_API_URL', 'https://meta.teste/v24.0/')
    for nome in [n for n in fluxo.os.environ if n.startswith('META_TOKEN_')]:
        monkeypatch.delenv(nome)
    monkeypatch.setenv('META_TOKEN_A', 'ta')
    estado.contas['ta'] = ['act_1']
    return estado


def _orcamento(banco):
    return [dict(l) for l in banco.conexao.execute('SELECT * FROM orcamento_campanha ORDER BY data, campaignid')]


def test_35_grava_cada_dia_na_sua_data_e_atualiza_o_nome(banco, meta):
    banco.campanha('123', produto_id=4, plataforma='meta')
    meta.insights['act_1'] = [[linha(data='2026-10-29'), linha(data='2026-10-30', spend='20')]]
    resumo = processar_orcamento_meta()
    assert _orcamento(banco) == [
        {'produto_id': 4, 'campaignid': '123', 'data': '2026-10-29', 'valor_investido': 12.34, 'cliques': 5, 'impressoes': 100},
        {'produto_id': 4, 'campaignid': '123', 'data': '2026-10-30', 'valor_investido': 20.0, 'cliques': 5, 'impressoes': 100},
    ]
    assert banco.ler_campanha('123', produto_id=4)['nome'] == 'Campanha Bonita'
    assert resumo['upserts'] == 2


def test_35_nome_dado_no_admin_fica(banco, meta):
    banco.campanha('123', nome='Dado no admin', plataforma='meta')
    meta.insights['act_1'] = [[linha()]]
    processar_orcamento_meta()
    assert banco.ler_campanha('123')['nome'] == 'Dado no admin'


def test_35_rodar_de_novo_nao_duplica_e_atualiza_o_gasto(banco, meta):
    banco.campanha('123', plataforma='meta')
    meta.insights['act_1'] = [[linha(spend='10')]]
    processar_orcamento_meta()
    meta.insights['act_1'] = [[linha(spend='15')]]
    processar_orcamento_meta()
    linhas = _orcamento(banco)
    assert len(linhas) == 1 and linhas[0]['valor_investido'] == 15.0


def test_35_meta_omite_cliques_zerados(banco, meta):
    banco.campanha('123', plataforma='meta')
    item = linha()
    del item['inline_link_clicks']
    meta.insights['act_1'] = [[item]]
    processar_orcamento_meta()
    assert _orcamento(banco)[0]['cliques'] == 0


def test_36_descobre_contas_pelo_token_e_le_todas_as_paginas(banco, meta):
    banco.campanha('123', plataforma='meta')
    meta.insights['act_1'] = [[linha(data='2026-10-28')], [linha(data='2026-10-29')], [linha(data='2026-10-30')]]
    processar_orcamento_meta()
    assert len(_orcamento(banco)) == 3
    primeira = meta.chamadas[0]
    assert primeira['url'].endswith('/me/adaccounts') and primeira['token'] == 'ta'
    insights = [c for c in meta.chamadas if c['url'].endswith('act_1/insights')]
    assert [c['params'].get('after') for c in insights] == [None, '1', '2']
    assert insights[0]['params']['level'] == 'campaign' and insights[0]['params']['time_increment'] == 1
    assert insights[0]['params']['fields'] == ('campaign_id,campaign_name,spend,inline_link_clicks,impressions,'
                                               'account_currency,date_start')


def test_36_token_nunca_na_url_nem_nos_parametros(banco, meta):
    banco.campanha('123', plataforma='meta')
    meta.insights['act_1'] = [[linha()], [linha(data='2026-10-31')]]
    processar_orcamento_meta()
    for chamada in meta.chamadas:
        assert 'ta' != chamada['params'].get('access_token') and 'access_token' not in chamada['url']


def _time_range(meta):
    chamada = next(c for c in meta.chamadas if c['url'].endswith('/insights'))
    return json.loads(chamada['params']['time_range'])


def test_37_sem_data_le_os_ultimos_7_dias(banco, meta):
    meta.insights['act_1'] = [[]]
    processar_orcamento_meta()
    hoje = datetime.now(timezone(timedelta(hours=-3))).date()
    assert _time_range(meta) == {'since': (hoje - timedelta(days=6)).isoformat(), 'until': hoje.isoformat()}


def test_37_com_data_le_um_dia(banco, meta):
    meta.insights['act_1'] = [[]]
    processar_orcamento_meta('2026-10-15')
    assert _time_range(meta) == {'since': '2026-10-15', 'until': '2026-10-15'}


def test_38_campanha_sem_linha_nao_grava(banco, meta):
    meta.insights['act_1'] = [[linha(campanha='404')]]
    resumo = processar_orcamento_meta()
    assert _orcamento(banco) == [] and resumo['ignoradas'] == 1


def test_38_outra_moeda_nao_grava_e_registra_erro(banco, meta, caplog):
    banco.campanha('123', plataforma='meta')
    meta.insights['act_1'] = [[linha(moeda='USD')]]
    processar_orcamento_meta()
    assert _orcamento(banco) == []
    assert 'só gravamos BRL' in caplog.text
    assert banco.ler_campanha('123')['nome'] == '123'


def test_39_bm_bloqueada_nao_atrapalha_as_outras(banco, meta, monkeypatch):
    monkeypatch.setenv('META_TOKEN_B', 'tb')
    meta.contas['ta'] = requests.HTTPError('403')
    meta.contas['tb'] = ['act_2']
    banco.campanha('123', plataforma='meta')
    meta.insights['act_2'] = [[linha()]]
    resumo = processar_orcamento_meta()
    assert len(_orcamento(banco)) == 1 and resumo['erros'] == 1


def test_39_erro_numa_conta_nao_atrapalha_as_outras(banco, meta):
    meta.contas['ta'] = ['act_1', 'act_2']
    banco.campanha('123', plataforma='meta')
    meta.insights['act_1'] = requests.ConnectionError('fora')
    meta.insights['act_2'] = [[linha()]]
    resumo = processar_orcamento_meta()
    assert len(_orcamento(banco)) == 1 and resumo['erros'] == 1 and resumo['contas'] == 1


def test_39_conta_vista_por_dois_tokens_e_lida_uma_vez(banco, meta, monkeypatch):
    monkeypatch.setenv('META_TOKEN_B', 'tb')
    meta.contas['tb'] = ['act_1']
    meta.insights['act_1'] = [[]]
    processar_orcamento_meta()
    assert len([c for c in meta.chamadas if c['url'].endswith('act_1/insights')]) == 1


def test_39_conta_que_falhou_com_um_token_e_tentada_com_o_outro(banco, meta, monkeypatch):
    monkeypatch.setenv('META_TOKEN_B', 'tb')
    meta.contas['tb'] = ['act_1']
    banco.campanha('123', plataforma='meta')

    def insights_por_token(url, headers=None, params=None, timeout=None):
        if url.endswith('/insights') and headers['Authorization'] == 'Bearer ta':
            raise requests.ConnectionError('fora')
        return original(url, headers=headers, params=params, timeout=timeout)
    original = fluxo.requests.get
    monkeypatch.setattr(fluxo.requests, 'get', insights_por_token)
    meta.insights['act_1'] = [[linha()]]
    resumo = processar_orcamento_meta()
    assert len(_orcamento(banco)) == 1 and resumo['erros'] == 1 and resumo['contas'] == 1


def test_variavel_vazia_nao_conta_como_token(banco, meta, monkeypatch):
    monkeypatch.setenv('META_TOKEN_VAZIO', '  ')
    meta.insights['act_1'] = [[]]
    processar_orcamento_meta()
    assert {c['token'] for c in meta.chamadas} == {'ta'}


# ─── Task ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def task(monkeypatch):
    import tasks
    import fluxos.fluxo_orcamento_sheets as sheets
    monkeypatch.setattr(tasks._redis, 'set', lambda *a, **k: True)
    monkeypatch.setattr(tasks._redis, 'delete', lambda *a: None)
    registro = {'google': [], 'meta': []}
    monkeypatch.setattr(sheets, 'processar_orcamento_sheets', lambda data: registro['google'].append(data) or {})
    monkeypatch.setattr(fluxo, 'processar_orcamento_meta', lambda data: registro['meta'].append(data) or {})
    registro['sheets'] = sheets
    registro['task'] = tasks.processar_orcamento_sheets
    return registro


def test_40_meta_roda_depois_do_google_e_recebe_a_data(task):
    task['task'].run('2026-10-15')
    assert task['google'] == ['2026-10-15'] and task['meta'] == ['2026-10-15']


def test_40_sem_data_a_meta_recebe_none_uma_vez(task):
    task['task'].run()
    assert task['meta'] == [None]


def test_40_erro_na_meta_nao_vira_retry(task, monkeypatch):
    def falha(data):
        raise RuntimeError('meta fora')
    monkeypatch.setattr(fluxo, 'processar_orcamento_meta', falha)
    task['task'].run('2026-10-15')  # não levanta


def test_40_erro_no_google_nao_impede_a_meta_e_mantem_o_retry(task, monkeypatch):
    def falha(data):
        raise ValueError('planilha fora')
    monkeypatch.setattr(task['sheets'], 'processar_orcamento_sheets', falha)

    class Reagendou(Exception):
        pass

    pedidos_retry = []

    def retry(exc=None, countdown=None):
        pedidos_retry.append((exc, countdown))
        return Reagendou()
    monkeypatch.setattr(task['task'], 'retry', retry)
    with pytest.raises(Reagendou):
        task['task'].run('2026-10-15')
    assert task['meta'] == ['2026-10-15']
    assert isinstance(pedidos_retry[0][0], ValueError) and pedidos_retry[0][1] == 600


def test_40_erro_nos_dois_o_retry_e_do_google(task, monkeypatch):
    def falha_google(data):
        raise ValueError('planilha fora')

    def falha_meta(data):
        raise RuntimeError('meta fora')
    monkeypatch.setattr(task['sheets'], 'processar_orcamento_sheets', falha_google)
    monkeypatch.setattr(fluxo, 'processar_orcamento_meta', falha_meta)

    class Reagendou(Exception):
        pass

    pedidos_retry = []
    monkeypatch.setattr(task['task'], 'retry', lambda exc=None, countdown=None: pedidos_retry.append(exc) or Reagendou())
    with pytest.raises(Reagendou):
        task['task'].run('2026-10-15')
    assert isinstance(pedidos_retry[0], ValueError)


# ─── Agendamento do envio ─────────────────────────────────────────────────────

def test_envio_agendado_no_minuto_23_na_fila_baixa():
    from celery_app import celery_app
    agendamento = celery_app.conf.beat_schedule['conversoes-meta-horario']
    assert agendamento['task'] == 'tasks.processar_conversoes_meta'
    assert agendamento['schedule'].minute == {23}
    assert agendamento['options']['queue'] == 'baixa'
    assert celery_app.conf.task_routes['tasks.processar_conversoes_meta'] == {'queue': 'baixa'}


def test_envio_com_trava_no_redis_e_sem_retry(monkeypatch):
    import tasks
    import fluxos.fluxo_meta_conversoes as envio
    chamadas = []
    monkeypatch.setattr(envio, 'executar', lambda: chamadas.append(1))
    monkeypatch.setattr(tasks._redis, 'delete', lambda *a: None)

    monkeypatch.setattr(tasks._redis, 'set', lambda *a, **k: False)
    tasks.processar_conversoes_meta.run()
    assert chamadas == []

    monkeypatch.setattr(tasks._redis, 'set', lambda *a, **k: True)
    tasks.processar_conversoes_meta.run()
    assert chamadas == [1]

    def falha():
        raise RuntimeError('fora')
    monkeypatch.setattr(envio, 'executar', falha)
    tasks.processar_conversoes_meta.run()  # não levanta nem reagenda
