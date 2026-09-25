"""
Correções vindas da revisão de código. Cada teste descreve o cenário que falhava antes.
"""
import importlib
from contextlib import contextmanager

import pytest

import database
import whatsapp
import wpp_web_gateway
from fluxos import fluxo_followup_dinamico as followup
from fluxos import fluxo_followup_interesse_dinamico as followup_int
from whatsapp import ChipForaDoArWhatsApp


# ─── chip com status velho: confirmação ao vivo no gateway ───────────────────

class _RespStatus:
    def __init__(self, ok, status):
        self.ok, self._status = ok, status

    def json(self):
        return {'status': self._status}


@pytest.fixture
def chip_wpp(monkeypatch):
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda _p: 'wpp_web')
    monkeypatch.setattr(whatsapp, 'get_whatsapp_api_url', lambda _p: 'http://gw:3100/v24.0/')
    monkeypatch.setattr(whatsapp, 'get_whatsapp_token', lambda _p: 'tok')
    gravados = []
    monkeypatch.setattr(whatsapp, 'atualizar_status_api_numero', lambda pid, st: gravados.append((pid, st)))
    return gravados


def test_status_velho_ruim_mas_gateway_confirma_conectado_libera_e_corrige(monkeypatch, chip_wpp):
    """Chip foi re-pareado, status_api ainda diz LOGGED_OUT até a checagem horária: não pode bloquear por 1 h."""
    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional', lambda _p: False)
    monkeypatch.setattr(whatsapp.requests, 'get', lambda *a, **k: _RespStatus(True, 'CONNECTED'))
    whatsapp.exigir_numero_operacional({'id': 1, 'phone_number_id': 'web-5561982402450'})
    assert chip_wpp == [('web-5561982402450', 'CONNECTED')]


def test_status_ruim_e_gateway_confirma_fora_bloqueia(monkeypatch, chip_wpp):
    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional', lambda _p: False)
    monkeypatch.setattr(whatsapp.requests, 'get', lambda *a, **k: _RespStatus(True, 'LOGGED_OUT'))
    with pytest.raises(ChipForaDoArWhatsApp):
        whatsapp.exigir_numero_operacional({'id': 1, 'phone_number_id': 'web-1'})
    assert chip_wpp == []


def test_status_ruim_e_gateway_inalcancavel_bloqueia(monkeypatch, chip_wpp):
    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional', lambda _p: False)

    def cai(*a, **k):
        raise whatsapp.requests.ConnectionError('gateway fora')

    monkeypatch.setattr(whatsapp.requests, 'get', cai)
    with pytest.raises(ChipForaDoArWhatsApp):
        whatsapp.exigir_numero_operacional({'id': 1, 'phone_number_id': 'web-1'})


def test_status_bom_nao_consulta_o_gateway(monkeypatch, chip_wpp):
    monkeypatch.setattr(whatsapp, 'numero_empresa_operacional', lambda _p: True)
    monkeypatch.setattr(whatsapp.requests, 'get',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('não deve consultar o gateway')))
    whatsapp.exigir_numero_operacional({'id': 1, 'phone_number_id': 'web-1'})


# ─── sorteio de número: chip do gateway sem pareamento não recebe lead ───────

def test_sorteio_de_numero_exclui_gateway_nao_conectado(monkeypatch):
    sqls = []

    class Cursor:
        def execute(self, sql, params=None):
            sqls.append(sql)

        def fetchone(self):
            return None

    @contextmanager
    def fake_cursor():
        yield Cursor()

    monkeypatch.setattr(database.db, 'get_cursor', fake_cursor)
    database.selecionar_telefone_produto(1)
    sql = ' '.join(sqls[0].split())
    assert "provedor = 'meta' OR status_api = 'CONNECTED'" in sql


# ─── provedor: falha de banco não vira 'meta' ────────────────────────────────

def test_falha_de_banco_sem_cache_propaga(monkeypatch):
    def cai(*a, **k):
        raise RuntimeError('mysql fora')

    monkeypatch.setattr(database.db, 'execute_query', cai)
    with pytest.raises(RuntimeError):
        database.get_provedor_numero('web-1')  # antes: seria adivinhado; agora: erro explícito


def test_falha_de_banco_com_cache_vencido_reaproveita(monkeypatch):
    database._whatsapp_provedor_cache['web-1'] = ('wpp_web', 0)  # vencido

    def cai(*a, **k):
        raise RuntimeError('mysql fora')

    monkeypatch.setattr(database.db, 'execute_query', cai)
    assert database.get_provedor_numero('web-1') == 'wpp_web'


# ─── config: barra final ─────────────────────────────────────────────────────

@pytest.mark.parametrize('valor,esperado', [
    ('http://127.0.0.1:9', 'http://127.0.0.1:9/'),
    ('http://127.0.0.1:9/', 'http://127.0.0.1:9/'),
    ('', 'https://graph.facebook.com/v24.0/'),
])
def test_whatsapp_api_url_sempre_termina_em_barra(monkeypatch, valor, esperado):
    import config
    monkeypatch.setenv('WHATSAPP_API_URL', valor)
    try:
        importlib.reload(config)
        assert config.WHATSAPP_API_URL == esperado
    finally:
        monkeypatch.delenv('WHATSAPP_API_URL', raising=False)
        importlib.reload(config)


# ─── cadastro do número: provedor x id x token ───────────────────────────────

def test_cadastro_wpp_web_preenche_id_e_token_do_gateway():
    assert wpp_web_gateway.normalizar_cadastro_numero('wpp_web', '5561982402450', None, None) == \
        ('web-5561982402450', 'GATEWAY_TOKEN_WPP')


def test_cadastro_wpp_web_troca_o_token_padrao_da_meta_pelo_do_gateway():
    """O formulário vem com WHATSAPP_ACCESS_TOKEN: o token real da Meta iria como Bearer para o gateway."""
    _, token = wpp_web_gateway.normalizar_cadastro_numero('wpp_web', '5561982402450', 'web-5561982402450',
                                                          'WHATSAPP_ACCESS_TOKEN')
    assert token == 'GATEWAY_TOKEN_WPP'


@pytest.mark.parametrize('api_id', ['web-55 61 98240-2450', 'web-5561999999999', '5561982402450', 'web-1'])
def test_cadastro_wpp_web_rejeita_id_que_nao_bate_com_o_telefone(api_id):
    with pytest.raises(ValueError, match='web-5561982402450'):
        wpp_web_gateway.normalizar_cadastro_numero('wpp_web', '5561982402450', api_id, None)


def test_cadastro_wpp_web_rejeita_token_de_outra_conta():
    with pytest.raises(ValueError, match='GATEWAY_TOKEN_WPP'):
        wpp_web_gateway.normalizar_cadastro_numero('wpp_web', '5561982402450', None, 'WHATSAPP_ACCESS_TOKEN_RC')


def test_cadastro_meta_rejeita_token_do_gateway():
    with pytest.raises(ValueError, match='só vale para o provedor WhatsApp Web'):
        wpp_web_gateway.normalizar_cadastro_numero('meta', '556181256294', '1012710858592627', 'GATEWAY_TOKEN_WPP')


def test_cadastro_meta_continua_igual():
    assert wpp_web_gateway.normalizar_cadastro_numero('meta', '556181256294', ' 1012710858592627 ', '') == \
        ('1012710858592627', 'WHATSAPP_ACCESS_TOKEN')


def test_id_do_chip_vai_escapado_no_path(monkeypatch):
    chamados = []
    monkeypatch.setattr(wpp_web_gateway, '_chamar', lambda m, caminho, body=None: chamados.append(caminho) or {})
    wpp_web_gateway.buscar_qr('web-1/../../x')
    assert chamados == ['/admin/chips/web-1%2F..%2F..%2Fx/qr']


# ─── followup: chip cai no meio da sequência ─────────────────────────────────

@pytest.fixture
def banco():
    """Estado "real" do pedido no banco, que outro fluxo (comprovante) pode mudar durante o lote."""
    return {'estado_id': 3}


@pytest.fixture
def followup_env(monkeypatch, banco):
    pedido = {'id': 9, 'produto_id': 1, 'interesse_produto': 1, 'phone_number_id': 'web-1'}
    acoes = [{'ordem': i, 'acao': 'enviar_mensagem', 'condicao': 'sempre'} for i in (1, 2, 3)]
    avancos = []
    monkeypatch.setattr(followup, 'buscar_pedidos_followup', lambda *a, **k: [pedido])
    monkeypatch.setattr(followup, 'listar_acoes_fluxo', lambda *a, **k: acoes)
    monkeypatch.setattr(followup, 'filtrar_e_ordenar', lambda a, c: a)
    monkeypatch.setattr(followup, 'selecionar_variantes', lambda a: a)
    monkeypatch.setattr(followup, 'get_pedido', lambda pid: {**pedido, 'estado_id': banco['estado_id']})

    def muda_se(pid, esperado, novo):
        if banco['estado_id'] != esperado:
            return False
        banco['estado_id'] = novo
        avancos.append(('estado', novo))
        return True

    monkeypatch.setattr(followup, 'atualizar_estado_pedido_se', muda_se)
    monkeypatch.setattr(followup, 'atualizar_pedido_com_data_followup', lambda pid: avancos.append(('data', pid)))
    return avancos


def test_followup_chip_cai_antes_de_enviar_adia_e_nao_avanca(monkeypatch, followup_env):
    def executa(acao, *a, **k):
        raise ChipForaDoArWhatsApp('fora')

    monkeypatch.setattr(followup, 'executar_acao', executa)
    followup.executar()
    assert followup_env == []  # continua elegível na próxima rodada


def test_followup_chip_cai_no_meio_conclui_para_nao_duplicar(monkeypatch, followup_env):
    """Antes: `continue` sem avançar o estado → na rodada seguinte a ação 1 saía de novo (mensagem duplicada)."""
    enviadas = []

    def executa(acao, *a, **k):
        if acao['ordem'] == 2:
            raise ChipForaDoArWhatsApp('caiu')
        enviadas.append(acao['ordem'])

    monkeypatch.setattr(followup, 'executar_acao', executa)
    followup.executar()
    assert enviadas == [1]
    assert ('estado', 4) in followup_env  # dado como concluído: não reenvia a ação 1


# ─── followup: cliente paga enquanto o lote roda ─────────────────────────────

def test_followup_pula_pedido_que_pagou_antes_da_sua_vez(monkeypatch, followup_env, banco):
    """Lista lida no início do lote; o comprovante chegou enquanto outros pedidos eram processados."""
    enviadas = []
    banco['estado_id'] = 0
    monkeypatch.setattr(followup, 'executar_acao', lambda acao, *a, **k: enviadas.append(acao['ordem']))
    followup.executar()
    assert enviadas == []        # não cobra quem já pagou
    assert followup_env == []    # e não mexe no estado
    assert banco['estado_id'] == 0


def test_followup_nao_sobrescreve_pagamento_feito_durante_as_acoes(monkeypatch, followup_env, banco):
    """Produção (16 a 24/09): 42 pagos presos no 4, com o 4 gravado 0 a 3 min depois do comprovante."""
    enviadas = []

    def executa(acao, *a, **k):
        enviadas.append(acao['ordem'])
        if acao['ordem'] == 2:
            banco['estado_id'] = 0   # comprovante processado durante o delay da ação 2

    monkeypatch.setattr(followup, 'executar_acao', executa)
    followup.executar()
    assert enviadas == [1, 2]    # a ação 3 (mais cobrança) não sai para quem já pagou
    assert banco['estado_id'] == 0
    assert ('estado', 4) not in followup_env


# ─── followup de interesse: chip cai ─────────────────────────────────────────

@pytest.fixture
def followup_int_env(monkeypatch):
    pedido = {'id': 7, 'produto_id': 1, 'phone_number_id': 'web-1'}
    acoes = [{'ordem': i, 'acao': 'enviar_mensagem', 'condicao': 'sempre'} for i in (1, 2, 3)]
    marcados = []
    monkeypatch.setattr(followup_int, 'listar_acoes_fluxo', lambda *a, **k: acoes)
    monkeypatch.setattr(followup_int, 'filtrar_e_ordenar', lambda a, c: a)
    monkeypatch.setattr(followup_int, 'selecionar_variantes', lambda a: a)
    rodar = lambda: followup_int._executar_rodada([pedido], 'followup_interesse_1', marcados.append)
    return rodar, marcados


def test_followup_interesse_chip_fora_antes_de_enviar_adia_sem_traceback(monkeypatch, followup_int_env, caplog):
    rodar, marcados = followup_int_env
    monkeypatch.setattr(followup_int, 'executar_acao',
                        lambda *a, **k: (_ for _ in ()).throw(ChipForaDoArWhatsApp('fora')))
    rodar()
    assert marcados == []   # segue elegível (até sair da janela de 24h)
    assert not [r for r in caplog.records if r.exc_info]  # situação esperada: sem traceback no log


def test_followup_interesse_chip_cai_no_meio_conclui_para_nao_duplicar(monkeypatch, followup_int_env):
    """Antes: exceção genérica → continue sem marcar → a ação 1 saía de novo na rodada seguinte."""
    rodar, marcados = followup_int_env
    enviadas = []

    def executa(acao, *a, **k):
        if acao['ordem'] == 2:
            raise ChipForaDoArWhatsApp('caiu')
        enviadas.append(acao['ordem'])

    monkeypatch.setattr(followup_int, 'executar_acao', executa)
    rodar()
    assert enviadas == [1]
    assert marcados == [7]


# ─── followups: janela de 24h do WhatsApp ────────────────────────────────────

@pytest.mark.parametrize('busca, coluna', [
    (lambda: database.buscar_pedidos_followup(2), 'data_envio_pedido >='),
    (database.buscar_pedidos_followup_interesse_1, 'data_pedido >='),
    (database.buscar_pedidos_followup_interesse_2, 'data_pedido >='),
])
def test_buscas_de_followup_nao_pegam_pedido_fora_da_janela(monkeypatch, busca, coluna):
    """Pedidos presos atrás de chip fora do ar (21 a 25/09) seriam cobrados dias depois quando o chip voltasse."""
    chamadas = []
    monkeypatch.setattr(database.db, 'execute_query', lambda q, p=None, **k: chamadas.append((q, p)) or [])
    busca()
    query, params = chamadas[0]
    assert coluna in query
    assert database.JANELA_FOLLOWUP_HORAS in params
    assert database.JANELA_FOLLOWUP_HORAS < 24


# ─── recursos que só existem na Meta ─────────────────────────────────────────

@pytest.mark.parametrize('funcao', [whatsapp.bloquear_numero_whatsapp, whatsapp.desbloquear_numero_whatsapp])
def test_block_users_em_numero_do_gateway_nao_manda_token_para_a_meta(monkeypatch, funcao):
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda _p: 'wpp_web')
    monkeypatch.setattr(whatsapp.requests, 'post',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('não deve chamar a Graph API')))
    monkeypatch.setattr(whatsapp.requests, 'delete',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('não deve chamar a Graph API')))
    with pytest.raises(ValueError, match='block_users'):
        funcao('556181163324', 'web-5561982402450')


# ─── onboarding: webhook do chip configurado ao parear ───────────────────────

URL_WEBHOOK = 'https://lsnlivros.com.br/api/v1/webhook-whatsapp'


@pytest.fixture
def gw(monkeypatch):
    chamadas = []
    monkeypatch.setattr(wpp_web_gateway, 'WPP_WEB_WEBHOOK_URL', URL_WEBHOOK)
    monkeypatch.setattr(wpp_web_gateway, '_chamar', lambda m, caminho, body=None: chamadas.append((m, caminho, body)) or {})
    monkeypatch.setenv('WHATSAPP_APP_SECRET_LSN', 'segredo-de-teste-lsn')
    return chamadas


def test_chip_sem_webhook_recebe_url_e_segredo_do_dominio(gw):
    """O segredo vem do Host da URL (mesmo mapa da validação de entrada): lsnlivros.com.br -> APP_SECRET_LSN."""
    assert wpp_web_gateway.garantir_webhook({'webhook': {'custom': False}}, 'web-5561982402450') is True
    assert gw == [('PATCH', '/admin/chips/web-5561982402450',
                   {'webhookUrl': URL_WEBHOOK, 'appSecret': 'segredo-de-teste-lsn'})]


def test_chip_que_ja_tem_webhook_nao_e_sobrescrito(gw):
    assert wpp_web_gateway.garantir_webhook({'webhook': {'custom': True, 'url': 'http://outro'}}, 'web-1') is False
    assert gw == []


def test_sem_url_configurada_nao_faz_nada(gw, monkeypatch):
    monkeypatch.setattr(wpp_web_gateway, 'WPP_WEB_WEBHOOK_URL', '')
    assert wpp_web_gateway.garantir_webhook({'webhook': {}}, 'web-1') is False
    assert gw == []


def test_host_nao_mapeado_falha_explicito_e_nao_grava(gw, monkeypatch):
    monkeypatch.setattr(wpp_web_gateway, 'WPP_WEB_WEBHOOK_URL', 'https://desconhecido.com.br/x')
    with pytest.raises(wpp_web_gateway.ErroGatewayWppWeb, match='_HOST_SECRET_MAP'):
        wpp_web_gateway.garantir_webhook({'webhook': {}}, 'web-1')
    assert gw == []


def test_segredo_ausente_no_env_falha_explicito(gw, monkeypatch):
    monkeypatch.delenv('WHATSAPP_APP_SECRET_LSN')
    with pytest.raises(wpp_web_gateway.ErroGatewayWppWeb, match='WHATSAPP_APP_SECRET_LSN'):
        wpp_web_gateway.garantir_webhook({'webhook': {}}, 'web-1')
    assert gw == []


# ─── remover número do WhatsApp Web desconecta o chip no gateway ─────────────

def test_remover_chip_chama_delete_com_id_escapado(monkeypatch):
    chamados = []
    monkeypatch.setattr(wpp_web_gateway, '_chamar', lambda m, caminho, body=None: chamados.append((m, caminho)) or {})
    assert wpp_web_gateway.remover_chip('web-5561982402450') is True
    assert chamados == [('DELETE', '/admin/chips/web-5561982402450')]


def test_remover_chip_que_ja_nao_existe_no_gateway_nao_e_erro(monkeypatch):
    def nao_existe(*a, **k):
        raise wpp_web_gateway.ErroGatewayWppWeb('chip não cadastrado', status=404)

    monkeypatch.setattr(wpp_web_gateway, '_chamar', nao_existe)
    assert wpp_web_gateway.remover_chip('web-5561982402450') is False


def test_remover_chip_com_gateway_fora_propaga_para_a_view_nao_apagar_a_linha(monkeypatch):
    def fora(*a, **k):
        raise wpp_web_gateway.ErroGatewayWppWeb('Gateway inalcançável: ConnectionError')

    monkeypatch.setattr(wpp_web_gateway, '_chamar', fora)
    with pytest.raises(wpp_web_gateway.ErroGatewayWppWeb):
        wpp_web_gateway.remover_chip('web-5561982402450')


# ─── checagem rápida de status dos chips do gateway ──────────────────────────

@pytest.fixture
def tarefa_status(monkeypatch):
    import tasks
    checados = []
    monkeypatch.setattr(database, 'listar_telefones_com_token', lambda *a, **k: [
        {'id': 1, 'api_phone_number_id': '1012710858592627', 'provedor': 'meta', 'telefone': 'm'},
        {'id': 2, 'api_phone_number_id': 'web-5561982402450', 'provedor': 'wpp_web', 'telefone': 'w'},
    ])
    monkeypatch.setattr(tasks, '_checar_qualidade_telefone', lambda t, tag: checados.append((t['id'], tag)))
    monkeypatch.setattr(tasks, '_redis', type('R', (), {'set': staticmethod(lambda *a, **k: True)})())
    return tasks, checados


def test_checagem_rapida_so_consulta_chips_do_gateway(tarefa_status):
    """Nunca a Graph API: número da Meta fica de fora (a checagem horária cuida dele)."""
    tasks, checados = tarefa_status
    tasks.verificar_status_wpp_web.run()
    assert checados == [(2, 'TASK-STATUS-WPP-WEB')]


def test_checagem_rapida_nao_alerta_admin_quando_o_gateway_falha(tarefa_status, monkeypatch):
    tasks, _ = tarefa_status
    alertas = []
    monkeypatch.setattr(tasks, 'notificar_admin_erro_sistema', lambda msg: alertas.append(msg))
    monkeypatch.setattr(tasks, '_checar_qualidade_telefone',
                        lambda t, tag: (_ for _ in ()).throw(RuntimeError('gateway fora')))
    tasks.verificar_status_wpp_web.run()  # não propaga
    assert alertas == []  # senão seria um alerta a cada 2 minutos


def test_checagem_rapida_nao_roda_duas_vezes_ao_mesmo_tempo(tarefa_status, monkeypatch):
    tasks, checados = tarefa_status
    monkeypatch.setattr(tasks, '_redis', type('R', (), {'set': staticmethod(lambda *a, **k: False)})())
    tasks.verificar_status_wpp_web.run()
    assert checados == []


def test_checagem_rapida_esta_agendada_a_cada_2_minutos_na_fila_baixa():
    import celery_app
    entrada = celery_app.celery_app.conf.beat_schedule['verificar-status-wpp-web']
    assert entrada['task'] == 'tasks.verificar_status_wpp_web'
    assert entrada['options'] == {'queue': 'baixa'}
    assert str(entrada['schedule'].minute) == str({m for m in range(0, 60, 2)})
    assert celery_app.celery_app.conf.task_routes['tasks.verificar_status_wpp_web'] == {'queue': 'baixa'}


# ─── recriar chip do zero (perfil de Chromium corrompido) ────────────────────

def test_recriar_do_zero_apaga_e_recria(monkeypatch):
    chamadas = []
    monkeypatch.setattr(wpp_web_gateway, '_chamar', lambda m, caminho, body=None: chamadas.append((m, caminho, body)) or {})
    wpp_web_gateway.recriar_do_zero('web-5561982397693', '5561982397693')
    assert chamadas == [
        ('DELETE', '/admin/chips/web-5561982397693', None),
        ('POST', '/admin/chips', {'phone': '5561982397693', 'pairing': 'qr'}),
    ]


def test_recriar_do_zero_funciona_mesmo_se_chip_ja_nao_existia(monkeypatch):
    """DELETE pode dar 404 (ex.: chip já tinha sido removido); ainda assim recria."""
    chamadas = []

    def fake(m, caminho, body=None):
        if m == 'DELETE':
            raise wpp_web_gateway.ErroGatewayWppWeb('não cadastrado', status=404)
        chamadas.append((m, caminho, body))
        return {}

    monkeypatch.setattr(wpp_web_gateway, '_chamar', fake)
    wpp_web_gateway.recriar_do_zero('web-1', '556100000000')
    assert chamadas == [('POST', '/admin/chips', {'phone': '556100000000', 'pairing': 'qr'})]
