"""SMS do sistema (docs/SMS.md): número, texto em 1 parte, trava do dev, registro antes do envio, Comtele e o aviso
de entrega."""
import pytest

import config as config_geral
from sms import comtele, config, servico, tarefas
from sms.texto import partes, sem_acento

CELULAR = '5561982696770'


@pytest.fixture
def agendados(monkeypatch):
    lista = []
    monkeypatch.setattr(tarefas.enviar_sms, 'delay', lambda envio_id: lista.append(envio_id))
    monkeypatch.setattr(config, 'ATIVO', True)
    return lista


def _enviar(texto='Oi! Ouca: {link} Marca', telefone='(61) 98269-6770', dominio='https://lsnlivros.com.br', **extra):
    return servico.enviar(12, telefone, lambda link: texto.format(link=link), 'https://lsnlivros.com.br/musica/p/tok',
                          dominio, 'musica_lembrete', etapa='previa 1', ref_tipo='musica', ref_id=9, **extra)


@pytest.mark.parametrize('entrada,saida', [
    ('(61) 98269-6770', CELULAR), ('+55 61 98269-6770', CELULAR), ('061982696770', CELULAR),
    ('6132345678', ''), ('6182696770', ''), ('+1 415 555 0100', ''), ('', ''), (None, ''),
])
def test_celular(entrada, saida):
    assert servico.celular(entrada) == saida


def test_sem_acento_e_partes():
    assert sem_acento('Ouça a canção, Conceição! 💛 [ok]') == 'Ouca a cancao, Conceicao! ok'
    assert partes('a' * 160) == 1 and partes('a' * 161) == 2 and partes('a' * 307) == 3


def test_producao_grava_e_agenda(banco, agendados, monkeypatch):
    monkeypatch.setattr(config_geral, 'EH_PRODUCAO', True)
    envio_id = _enviar('Ouça já: {link} Canção')
    envio = banco.envios[envio_id]
    link = banco.links[envio['link_id']]
    assert agendados == [envio_id] and envio['status'] == 'pendente' and envio['telefone'] == CELULAR
    assert envio['texto'] == f"Ouca ja: lsnlivros.com.br/m/{link['codigo']} Cancao"
    assert link['url_destino'] == 'https://lsnlivros.com.br/musica/p/tok' and len(link['codigo']) == 7
    assert (envio['ref_tipo'], envio['ref_id'], envio['etapa']) == ('musica', 9, 'previa 1')


def test_dev_so_envia_para_os_numeros_permitidos(banco, agendados, monkeypatch):
    monkeypatch.setattr(config_geral, 'EH_PRODUCAO', False)
    monkeypatch.setattr(config, 'DEV_PERMITIDOS', {'5561911112222'})
    envio_id = _enviar()
    assert banco.envios[envio_id]['status'] == 'ignorado_dev' and agendados == []
    envio_id = _enviar(telefone='61911112222')
    assert banco.envios[envio_id]['status'] == 'pendente' and agendados == [envio_id]


def test_texto_que_nao_cabe_nao_sai(banco, agendados, monkeypatch):
    monkeypatch.setattr(config_geral, 'EH_PRODUCAO', True)
    envio_id = _enviar('x' * 150 + ' {link}')
    assert banco.envios[envio_id]['status'] == 'falhou' and agendados == []


def test_numero_invalido_sem_dominio_ou_desligado_nao_grava(banco, agendados, monkeypatch):
    assert _enviar(telefone='6132345678') is None
    assert _enviar(dominio='') is None and _enviar(dominio='https://') is None
    monkeypatch.setattr(config, 'ATIVO', False)
    assert _enviar() is None
    assert banco.envios == {} and agendados == []


def test_processar_envia_uma_vez(banco, agendados, monkeypatch):
    monkeypatch.setattr(config_geral, 'EH_PRODUCAO', True)
    chamadas = []
    monkeypatch.setattr(comtele, 'enviar', lambda tel, texto, tag, custom: chamadas.append((tel, tag, custom)) or 'req-1')
    envio_id = _enviar()
    servico.processar(envio_id)
    servico.processar(envio_id)   # tarefa repetida: não reenvia
    assert chamadas == [(CELULAR, 'musica_lembrete', str(envio_id))]
    assert banco.envios[envio_id]['status'] == 'enviado' and banco.envios[envio_id]['provedor_id'] == 'req-1'


def test_erro_passageiro_volta_para_pendente_e_recusa_vira_falhou(banco, agendados, monkeypatch):
    monkeypatch.setattr(config_geral, 'EH_PRODUCAO', True)
    envio_id = _enviar()

    def passageiro(*a):
        raise comtele.ErroPassageiro('HTTP 503')
    monkeypatch.setattr(comtele, 'enviar', passageiro)
    with pytest.raises(comtele.ErroPassageiro):
        servico.processar(envio_id)
    assert banco.envios[envio_id]['status'] == 'pendente'

    def recusa(*a):
        raise comtele.ErroSms('saldo insuficiente')
    monkeypatch.setattr(comtele, 'enviar', recusa)
    servico.processar(envio_id)
    assert banco.envios[envio_id]['status'] == 'falhou' and 'saldo' in banco.envios[envio_id]['erro']


def test_intervalo_minimo_por_celular(banco, agendados, monkeypatch):
    monkeypatch.setattr(config_geral, 'EH_PRODUCAO', True)
    assert _enviar(minimo_minutos=120)
    assert _enviar(minimo_minutos=120) is None                      # mesmo celular, há menos de 2 h
    assert _enviar(telefone='61911112222', minimo_minutos=120)     # outro celular sai
    assert len(agendados) == 2


def test_destravar_nao_reenvia(banco, monkeypatch):
    chamadas = []
    monkeypatch.setattr(banco, 'execute_query', lambda sql, params=(), **k: chamadas.append((sql, params)) or 3)
    assert servico.destravar(60) == 3
    assert "status = 'falhou'" in chamadas[0][0] and "status = 'enviando'" in chamadas[0][0] and chamadas[0][1] == (60,)


@pytest.mark.parametrize('status,esperado', [
    ('Delivered', 'entregue'), ('Undelivered', 'falhou'), ('Rejected', 'falhou'), ('Expired', 'falhou'),
    ('Error', 'falhou'), ('Accepted', None), ('Processed', None), ('', None),
])
def test_status_entrega(status, esperado):
    assert servico.status_entrega(status) == esperado


def test_aviso_de_entrega_pelo_id_e_pelo_telefone(banco, agendados, monkeypatch):
    monkeypatch.setattr(config_geral, 'EH_PRODUCAO', True)
    monkeypatch.setattr(comtele, 'enviar', lambda *a: 'req')
    a, b = _enviar(), _enviar(telefone='61911112222')
    servico.processar(a)
    servico.processar(b)
    assert servico.registrar_entrega({'Sender': str(a), 'Status': 'Delivered', 'PhoneNumber': CELULAR})
    assert banco.envios[a]['status'] == 'entregue'
    assert servico.registrar_entrega({'status': 'Undelivered', 'phoneNumber': '61911112222'})
    assert banco.envios[b]['status'] == 'falhou'
    # sem o nosso id, pelo telefone: só um envio ainda sem resposta da operadora, o mais antigo
    c, d = _enviar(), _enviar()
    servico.processar(c)
    servico.processar(d)
    assert servico.registrar_entrega({'Status': 'Delivered', 'PhoneNumber': CELULAR})
    assert banco.envios[c]['status'] == 'entregue' and banco.envios[d]['status'] == 'enviado'
    assert not servico.registrar_entrega({'Status': 'Delivered', 'PhoneNumber': '61900000000'})
    # "falhou" atrasado não desfaz uma entrega já confirmada
    servico.registrar_entrega({'Sender': str(a), 'Status': 'Error'})
    assert banco.envios[a]['status'] == 'entregue'


class _Resposta:
    def __init__(self, status, dados):
        self.status_code, self._dados, self.text = status, dados, str(dados)

    def json(self):
        return self._dados


def test_comtele_corpo_e_erros(monkeypatch):
    monkeypatch.setattr(config, 'COMTELE_CHAVE', 'chave-teste')
    enviados = []

    def post(url, json, timeout, headers):
        enviados.append((url, json, headers))
        return respostas.pop(0)
    monkeypatch.setattr(comtele.requests, 'post', post)
    respostas = [_Resposta(200, {'hasError': False, 'object': {'requestId': 'abc', 'status': 'queued'}}),
                 _Resposta(503, {}), _Resposta(400, {'hasError': True, 'message': 'numero invalido'}),
                 _Resposta(200, {'hasError': True, 'message': 'sem saldo'}), _Resposta(502, {})]
    assert comtele.enviar(CELULAR, 'oi', 'musica_lembrete', '7') == 'abc'
    url, corpo, cabecalhos = enviados[0]
    assert cabecalhos['x-api-key'] == 'chave-teste' and corpo['receivers'] == [CELULAR] and corpo['message'] == 'oi'
    assert corpo['custom'] == '7' and corpo['tag'] == 'musica_lembrete' and corpo['scheduleDate'] is None
    with pytest.raises(comtele.ErroPassageiro):
        comtele.enviar(CELULAR, 'oi', 't', '8')
    with pytest.raises(comtele.ErroSms, match='numero invalido'):
        comtele.enviar(CELULAR, 'oi', 't', '9')
    with pytest.raises(comtele.ErroSms, match='sem saldo'):
        comtele.enviar(CELULAR, 'oi', 't', '10')
    # 502: pode ter saído — não é passageiro (tentar de novo = SMS repetido)
    with pytest.raises(comtele.ErroSms) as erro:
        comtele.enviar(CELULAR, 'oi', 't', '11')
    assert not isinstance(erro.value, comtele.ErroPassageiro)


@pytest.mark.parametrize('excecao,passageiro', [
    (comtele.requests.ConnectionError("NewConnectionError: Failed to establish a new connection"), True),
    (comtele.requests.ConnectTimeout('lento'), True),
    (comtele.requests.ConnectionError("('Connection aborted.', RemoteDisconnected(...))"), False),
    (comtele.requests.ReadTimeout('sem resposta'), False),
])
def test_comtele_rede(monkeypatch, excecao, passageiro):
    monkeypatch.setattr(config, 'COMTELE_CHAVE', 'chave-teste')

    def post(*a, **k):
        raise excecao
    monkeypatch.setattr(comtele.requests, 'post', post)
    with pytest.raises(comtele.ErroSms) as erro:
        comtele.enviar(CELULAR, 'oi', 't', '1')
    assert isinstance(erro.value, comtele.ErroPassageiro) == passageiro


def test_webhook_exige_o_segredo(banco, monkeypatch):
    from flask import Flask
    from sms import rotas
    monkeypatch.setattr(config, 'WEBHOOK_SEGREDO', 'segredo-certo')
    avisos = []
    monkeypatch.setattr(servico, 'registrar_entrega', lambda dados: avisos.append(dados) or True)
    app = Flask(__name__)
    app.register_blueprint(rotas.bp)
    c = app.test_client()
    assert c.post('/sms/comtele/status/errado', json={'Status': 'Delivered'}).status_code == 404
    assert c.post('/sms/comtele/status/segredo-certo', json={'Status': 'Delivered'}).status_code == 200
    assert c.post('/sms/comtele/status/segredo-certo', json=[{'Status': 'Delivered'}, {'Status': 'Error'}]).status_code == 200
    assert len(avisos) == 3
    monkeypatch.setattr(config, 'WEBHOOK_SEGREDO', '')
    assert c.post('/sms/comtele/status/', json={}).status_code == 404
