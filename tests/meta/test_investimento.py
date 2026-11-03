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
        self.text = 'detalhe do erro'

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
        contas, insights, conjuntos, chamadas = {}, {}, {}, []

    estado = Estado()
    estado.contas, estado.insights, estado.conjuntos, estado.chamadas = {}, {}, {}, []

    def get(url, headers=None, params=None, timeout=None):
        token = headers['Authorization'].removeprefix('Bearer ')
        estado.chamadas.append({'url': url, 'token': token, 'params': dict(params)})
        caminho = url.removeprefix('https://meta.teste/v24.0/')
        if caminho == 'me/adaccounts':
            contas = estado.contas[token]
            if isinstance(contas, Exception):
                raise contas
            return Resposta({'data': [{'id': c} for c in contas]})
        if caminho.endswith('/adsets'):
            conjuntos = estado.conjuntos.get(caminho.removesuffix('/adsets'), [])
            if isinstance(conjuntos, Exception):
                raise conjuntos
            return Resposta({'data': conjuntos})
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


def _conjunto(campanha='123', dataset='555'):
    return {'campaign_id': campanha, 'promoted_object': {'pixel_id': dataset, 'custom_event_type': 'PURCHASE'}}


def test_35_descobre_conta_dataset_e_token_da_campanha(banco, meta):
    banco.campanha('123', plataforma='meta')
    meta.insights['act_1'] = [[]]
    meta.conjuntos['act_1'] = [_conjunto()]
    processar_orcamento_meta()
    campanha = banco.ler_campanha('123')
    assert campanha['meta_conta_id'] == '1' and campanha['meta_dataset_id'] == '555'
    assert campanha['meta_token_env_var'] == 'META_TOKEN_A'


def test_35_cada_bm_grava_o_proprio_token(banco, meta, monkeypatch):
    monkeypatch.setenv('META_TOKEN_B', 'tb')
    banco.campanha('123', plataforma='meta')
    banco.campanha('456', plataforma='meta')
    meta.contas['tb'] = ['act_2']
    meta.insights['act_1'] = meta.insights['act_2'] = [[]]
    meta.conjuntos['act_1'] = [_conjunto('123', '111')]
    meta.conjuntos['act_2'] = [_conjunto('456', '222')]
    processar_orcamento_meta()
    assert banco.ler_campanha('123')['meta_token_env_var'] == 'META_TOKEN_A'
    assert banco.ler_campanha('456')['meta_dataset_id'] == '222' and banco.ler_campanha('456')['meta_token_env_var'] == 'META_TOKEN_B'


def test_35_campanha_do_google_nao_ganha_destino(banco, meta):
    banco.campanha('123', plataforma='google')
    meta.insights['act_1'] = [[]]
    meta.conjuntos['act_1'] = [_conjunto()]
    processar_orcamento_meta()
    assert banco.ler_campanha('123')['meta_dataset_id'] is None


def test_35_conjunto_sem_dataset_nao_apaga_o_destino(banco, meta):
    banco.campanha('123', plataforma='meta')
    banco.dataset()
    meta.insights['act_1'] = [[]]
    meta.conjuntos['act_1'] = [{'campaign_id': '123', 'promoted_object': {}}, {'campaign_id': '123'}]
    processar_orcamento_meta()
    assert banco.ler_campanha('123')['meta_dataset_id'] == '999'


def test_35_mais_de_um_dataset_avisa_e_usa_um_so(banco, meta, caplog):
    banco.campanha('123', plataforma='meta')
    meta.insights['act_1'] = [[]]
    meta.conjuntos['act_1'] = [_conjunto(dataset='222'), _conjunto(dataset='111')]
    processar_orcamento_meta()
    assert banco.ler_campanha('123')['meta_dataset_id'] == '111' and 'mais de um dataset' in caplog.text


def test_35_mais_de_um_dataset_compara_como_numero(banco, meta):
    banco.campanha('123', plataforma='meta')
    meta.insights['act_1'] = [[]]
    meta.conjuntos['act_1'] = [_conjunto(dataset='999'), _conjunto(dataset='1000')]
    processar_orcamento_meta()
    assert banco.ler_campanha('123')['meta_dataset_id'] == '999'


def test_39_falha_no_destino_deixa_outro_token_tentar(banco, meta, monkeypatch):
    monkeypatch.setenv('META_TOKEN_B', 'tb')
    banco.campanha('123', plataforma='meta')
    meta.contas['tb'] = ['act_1']
    meta.insights['act_1'] = [[]]
    estado = iter([requests.ConnectionError('fora'), [_conjunto()]])
    original = fluxo.requests.get

    def get(url, **kw):
        if url.endswith('/adsets'):
            r = next(estado)
            if isinstance(r, Exception):
                raise r
            meta.conjuntos['act_1'] = r
        return original(url, **kw)
    monkeypatch.setattr(fluxo.requests, 'get', get)
    processar_orcamento_meta()
    campanha = banco.ler_campanha('123')
    assert campanha['meta_dataset_id'] == '555' and campanha['meta_token_env_var'] == 'META_TOKEN_B'


def test_39_erro_ao_ler_os_conjuntos_nao_impede_o_gasto(banco, meta):
    banco.campanha('123', plataforma='meta')
    meta.conjuntos['act_1'] = requests.ConnectionError('fora')
    meta.insights['act_1'] = [[linha()]]
    resumo = processar_orcamento_meta()
    assert len(_orcamento(banco)) == 1 and resumo['erros'] == 1


def test_39_linha_ruim_nao_descarta_o_resto_da_conta(banco, meta):
    meta.contas['ta'] = ['act_1']
    banco.campanha('123', plataforma='meta')
    ruim = linha()
    del ruim['date_start']
    meta.insights['act_1'] = [[ruim, linha()]]
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
    monkeypatch.setattr(tasks._redis, 'set', lambda *a, **k: True)
    monkeypatch.setattr(tasks._redis, 'delete', lambda *a: None)
    return tasks


def test_40_task_propria_recebe_a_data(task, monkeypatch):
    datas = []
    monkeypatch.setattr(fluxo, 'processar_orcamento_meta', datas.append)
    task.processar_orcamento_meta.run('2026-10-15')
    task.processar_orcamento_meta.run()
    assert datas == ['2026-10-15', None]


def test_40_erro_na_meta_nao_levanta_nem_reagenda(task, monkeypatch):
    def falha(data):
        raise RuntimeError('meta fora')
    monkeypatch.setattr(fluxo, 'processar_orcamento_meta', falha)
    monkeypatch.setattr(task.processar_orcamento_meta, 'retry', lambda **k: pytest.fail('não pode reagendar'), raising=False)
    task.processar_orcamento_meta.run()


def test_40_rotina_do_google_nao_chama_a_meta(task, monkeypatch):
    import fluxos.fluxo_orcamento_sheets as sheets
    monkeypatch.setattr(sheets, 'processar_orcamento_sheets', lambda data: {})
    monkeypatch.setattr(fluxo, 'processar_orcamento_meta', lambda data: pytest.fail('não pode chamar a Meta'))
    task.processar_orcamento_sheets.run('2026-10-15')


def test_40_trava_impede_duas_execucoes(task, monkeypatch):
    monkeypatch.setattr(task._redis, 'set', lambda *a, **k: False)
    monkeypatch.setattr(fluxo, 'processar_orcamento_meta', lambda data: pytest.fail('não pode rodar'))
    task.processar_orcamento_meta.run()


def test_40_agendada_no_minuto_17_na_fila_baixa():
    from celery_app import celery_app
    agendamento = celery_app.conf.beat_schedule['orcamento-meta-horario']
    assert agendamento['task'] == 'tasks.processar_orcamento_meta'
    assert agendamento['schedule'].minute == {17} and agendamento['options']['queue'] == 'baixa'
    assert celery_app.conf.task_routes['tasks.processar_orcamento_meta']['queue'] == 'baixa'


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
