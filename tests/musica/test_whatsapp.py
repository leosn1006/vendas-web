"""WhatsApp da Música: musica_pronta para quem comprou, presente_surpresa para quem ganha, os avisos da Meta
(entregue/falhou), o toque em "Ouvir minha música" e o número só de avisos fora do fluxo de venda."""
from datetime import datetime, timedelta

import pytest

from musica import casos_de_uso as uc
from musica import config
from musica.casos_de_uso import Recusa
from musica.dominio import regras
from tests.musica.test_casos_de_uso import PRODUTO, _com_previa, _pagar


@pytest.fixture(autouse=True)
def whatsapp_ligado(monkeypatch):
    monkeypatch.setattr(config, 'WHATSAPP_ATIVO', True)


def _comprada(s, recursos=('musica', 'entrega_email'), whatsapp='(61) 98111-2222'):
    musica = _com_previa(s)
    s.repositorio.pedidos[500] = {'id': 500, 'guid': 'g-500', 'email': 'patricia@exemplo.com', 'estado_id': 1002,
                                  'dns_origem': 'site.com.br', 'contact_name': 'Patrícia Souza'}
    uc.vincular_ao_pedido(s, musica['token'], 500, PRODUTO, whatsapp)
    s.repositorio.pedidos[500]['estado_id'] = 1000
    s.repositorio.itens[500] = list(recursos)
    assert uc.liberar_do_pedido(s, 500)
    return s.repositorio.por_id(musica['id'])


def _status(wamid, status, erros=None, para='5561982223333'):
    st = {'id': wamid, 'status': status, 'recipient_id': para}
    if erros:
        st['errors'] = erros
    return {'metadata': {'phone_number_id': '1376511528883172'}, 'statuses': [st]}


def _botao(de, payload, tipo='button'):
    msg = {'from': de, 'type': tipo}
    if tipo == 'button':
        msg['button'] = {'payload': payload, 'text': 'Ouvir minha música'}
    else:
        msg['text'] = {'body': payload}
    return {'metadata': {'phone_number_id': '1376511528883172'}, 'messages': [msg]}


# ------------------------------------------------------------------ regras

@pytest.mark.parametrize('entrada,saida', [('(61) 98111-2222', '5561981112222'), ('61 8111-2222', '556181112222'),
                                           ('+55 61 98111-2222', '5561981112222'), ('123', ''), ('', '')])
def test_telefone_no_formato_da_meta(entrada, saida):
    assert regras.telefone_whatsapp(entrada) == saida


@pytest.mark.parametrize('entrada,ddi,saida', [('912 345 678', '351', '351912345678'), ('2025550123', '1', '12025550123'),
                                               ('351912345678', '351', '351912345678'), ('12', '351', '')])
def test_telefone_com_ddi_de_fora(entrada, ddi, saida):
    assert regras.telefone_whatsapp(entrada, ddi) == saida


def test_mesmo_telefone_com_e_sem_o_nove():
    assert regras.mesmo_telefone('556182696770', '5561982696770')
    assert not regras.mesmo_telefone('556182696770', '5511982696770')   # outro DDD
    assert not regras.mesmo_telefone('', '5561982696770')


@pytest.mark.parametrize('respostas,texto', [
    ({'para_quem': 'Mãe', 'nome': 'Helena', 'apelido': 'Dona Lena'}, 'sua mãe Dona Lena'),
    ({'para_quem': 'Amigo', 'nome': 'Marcelo', 'apelido': 'Celo'}, 'seu amigo Celo'),
    ({'para_quem': 'Mais de uma pessoa', 'nome': 'Ana, Bia e Carla'}, 'Ana, Bia e Carla'),
    ({'para_quem': 'Para mim', 'nome': 'Patrícia'}, 'você'),
    ({'para_quem': 'Outra pessoa', 'nome': 'Zé'}, 'Zé'),
    ({'para_quem': 'Minha ex', 'nome': 'Juliana', 'apelido': 'Ju'}, 'sua ex Ju'),
    ({'para_quem': 'Meu ex', 'nome': 'Rafael'}, 'seu ex Rafael'),
])
def test_para_quem_com_relacao(respostas, texto):
    assert regras.para_quem_com_relacao(respostas) == texto


# ------------------------------------------------------------- comprador

def test_musica_pronta_para_o_whatsapp_do_checkout(s):
    musica = _comprada(s)
    assert musica['whatsapp'] == '5561981112222'
    assert ('whatsapp_comprador', musica['id']) in s.agenda.chamadas
    uc.whatsapp_comprador(s, musica['id'])
    telefone, modelo, variaveis, _ = s.notificador.whatsapps[0]
    assert (telefone, modelo) == ('5561981112222', 'musica_pronta')
    assert variaveis[0] == 'Patrícia' and variaveis[1] == 'sua mãe Dona Lena' and variaveis[2].endswith('/musica/compra/g-500')
    uc.whatsapp_comprador(s, musica['id'])                     # tarefa repetida: não manda de novo
    assert len(s.notificador.whatsapps) == 1


def test_sem_whatsapp_no_checkout_nao_agenda(s):
    musica = _comprada(s, whatsapp='')
    assert not any(c[0] == 'whatsapp_comprador' for c in s.agenda.chamadas)
    assert musica['whatsapp'] in (None, '')


# --------------------------------------------------------- quem ganha

def test_agendamento_pede_email_ou_whatsapp_e_confirmacao(s):
    _comprada(s)
    with pytest.raises(Recusa, match='e-mail ou o WhatsApp'):
        uc.agendar_presente(s, 'g-500', 'Lena', '', '', None)
    with pytest.raises(Recusa, match='Confirme'):
        uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333')
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)


def test_whatsapp_desligado_ignora_o_numero(s, monkeypatch):
    _comprada(s)
    monkeypatch.setattr(config, 'WHATSAPP_ATIVO', False)
    with pytest.raises(Recusa, match='e-mail ou o WhatsApp'):
        uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)


def test_presente_por_email_e_whatsapp_cada_um_uma_vez(s):
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', 'lena@exemplo.com', '', None, whatsapp='61 98222-3333', confirmo=True)
    assert uc.enviar_presentes(s) == 2
    presente = [w for w in s.notificador.whatsapps if w[1] == 'presente_surpresa']
    assert presente == [('5561982223333', 'presente_surpresa', ['Lena', 'Patrícia'], musica['token'])]
    m = s.repositorio.por_id(musica['id'])
    assert m['presente_wa_status'] == 'enviado' and m['presente_wa_msg_id']
    # o e-mail volta (caixa lotada): a nova tentativa manda só o e-mail
    uc.presente_devolvido(s, m['presente_thread_id'], ['lena@exemplo.com'])
    s.repositorio.atualizar(musica['id'], presente_em=datetime.now() - timedelta(minutes=1))
    assert uc.enviar_presentes(s) == 1
    assert len([w for w in s.notificador.whatsapps if w[1] == 'presente_surpresa']) == 1


def test_entregue_e_lido_avisam_quem_comprou_uma_vez(s):
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    wamid = s.repositorio.por_id(musica['id'])['presente_wa_msg_id']
    uc.webhook_whatsapp(s, _status(wamid, 'delivered'))
    uc.webhook_whatsapp(s, _status(wamid, 'read'))
    feitas = [w for w in s.notificador.whatsapps if w[1] == 'entrega_feita']
    assert feitas == [('5561981112222', 'entrega_feita', ['Patrícia', 'Lena'], None)]
    assert s.repositorio.por_id(musica['id'])['presente_wa_status'] == 'entregue'


def test_entregue_sem_whatsapp_do_comprador_vai_por_email(s):
    musica = _comprada(s, whatsapp='')
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    uc.webhook_whatsapp(s, _status(s.repositorio.por_id(musica['id'])['presente_wa_msg_id'], 'delivered'))
    assert any('chegou' in e['assunto'] and e['destino'] == 'patricia@exemplo.com' for e in s.notificador.emails)


def test_entrega_feita_que_nao_sai_vai_por_email(s):
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    wamid = s.repositorio.por_id(musica['id'])['presente_wa_msg_id']
    original = s.notificador.whatsapp

    def falha_no_aviso(telefone, modelo, variaveis, payload_botao=None):
        if modelo == 'entrega_feita':
            raise ValueError('Meta fora')
        return original(telefone, modelo, variaveis, payload_botao)
    s.notificador.whatsapp = falha_no_aviso
    uc.webhook_whatsapp(s, _status(wamid, 'delivered'))
    assert any('chegou' in e['assunto'] for e in s.notificador.emails)


def test_falhou_avisa_com_botao_e_libera_para_corrigir(s):
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    wamid = s.repositorio.por_id(musica['id'])['presente_wa_msg_id']
    uc.webhook_whatsapp(s, _status(wamid, 'failed', [{'code': 131026, 'title': 'Message undeliverable'}]))
    uc.webhook_whatsapp(s, _status(wamid, 'failed'))                     # repetido: um aviso só
    avisos = [e for e in s.notificador.emails if 'pelo seu WhatsApp' in e['assunto']]
    assert len(avisos) == 1 and '/musica/compra/g-500/enviar' in avisos[0]['html']
    assert s.repositorio.por_id(musica['id'])['presente_wa_status'] == 'falhou'
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-4444', confirmo=True)   # corrige


def test_erro_no_envio_tambem_avisa_quem_comprou(s):
    _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)

    def falha(*a, **k):
        raise ValueError('(#131030) Recipient phone number not in allowed list')
    s.notificador.whatsapp = falha
    assert uc.enviar_presentes(s) == 0
    assert any('pelo seu WhatsApp' in e['assunto'] for e in s.notificador.emails)


def test_whatsapp_invalido_e_recusado_mesmo_com_email(s):
    _comprada(s)
    with pytest.raises(Recusa, match='DDD'):
        uc.agendar_presente(s, 'g-500', 'Lena', 'lena@exemplo.com', '', None, whatsapp='9123-4567', confirmo=True)


def test_corrigir_o_whatsapp_nao_reenvia_o_email_que_chegou(s):
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', 'lena@exemplo.com', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    wamid = s.repositorio.por_id(musica['id'])['presente_wa_msg_id']
    uc.webhook_whatsapp(s, _status(wamid, 'failed'))
    uc.agendar_presente(s, 'g-500', 'Lena', 'lena@exemplo.com', '', None, whatsapp='61 98222-4444', confirmo=True)
    emails_antes = len([e for e in s.notificador.emails if e['destino'] == 'lena@exemplo.com'])
    assert uc.enviar_presentes(s) == 1
    assert len([e for e in s.notificador.emails if e['destino'] == 'lena@exemplo.com']) == emails_antes
    assert [w[0] for w in s.notificador.whatsapps if w[1] == 'presente_surpresa'] == ['5561982223333', '5561982224444']


def test_aviso_da_meta_antes_do_wamid_gravado_e_lido_de_novo(s):
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    wamid = s.repositorio.por_id(musica['id'])['presente_wa_msg_id']
    s.repositorio.atualizar(musica['id'], presente_wa_msg_id=None)          # o "failed" chegou antes do UPDATE
    uc.webhook_whatsapp(s, _status(wamid, 'failed'))
    _, statuses, depois = [c for c in s.agenda.chamadas if c[0] == 'reler_status_whatsapp'][0]
    assert depois == 60
    s.repositorio.atualizar(musica['id'], presente_wa_msg_id=wamid)
    uc.webhook_whatsapp(s, {'statuses': statuses}, ultima_tentativa=True)
    assert s.repositorio.por_id(musica['id'])['presente_wa_status'] == 'falhou'
    uc.webhook_whatsapp(s, _status('wamid-de-outra-coisa', 'sent'), ultima_tentativa=True)
    assert len([c for c in s.agenda.chamadas if c[0] == 'reler_status_whatsapp']) == 1


def test_erro_passageiro_tenta_de_novo_e_depois_avisa(s):
    from musica.portas import ErroPassageiro
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)

    def fora(*a, **k):
        raise ErroPassageiro('503')
    s.notificador.whatsapp = fora
    assert uc.enviar_presentes(s) == 0
    assert s.repositorio.por_id(musica['id'])['presente_wa_status'] == 'erro1'
    assert not any('pelo seu WhatsApp' in e['assunto'] for e in s.notificador.emails)
    uc.enviar_presentes(s)                                                   # 2ª rodada
    uc.enviar_presentes(s)                                                   # 3ª: desiste e avisa
    assert s.repositorio.por_id(musica['id'])['presente_wa_status'] == 'falhou'
    assert len([e for e in s.notificador.emails if 'pelo seu WhatsApp' in e['assunto']]) == 1


def test_corrigir_o_email_nao_reenvia_o_whatsapp_que_chegou(s):
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', 'lena@errado.com', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    m = s.repositorio.por_id(musica['id'])
    uc.webhook_whatsapp(s, _status(m['presente_wa_msg_id'], 'delivered'))
    uc.presente_devolvido(s, m['presente_thread_id'], ['lena@errado.com'])   # volta: nova tentativa, enviado_em limpo
    uc.agendar_presente(s, 'g-500', 'Lena', 'lena@certo.com', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    assert len([w for w in s.notificador.whatsapps if w[1] == 'presente_surpresa']) == 1
    assert s.notificador.emails[-1]['destino'] == 'lena@certo.com'


def test_status_de_outras_mensagens_nao_e_relido(s):
    musica = _comprada(s)
    uc.whatsapp_comprador(s, musica['id'])
    uc.webhook_whatsapp(s, _status('wamid-do-musica-pronta', 'delivered', para='5561981112222'))
    assert not any(c[0] == 'reler_status_whatsapp' for c in s.agenda.chamadas)


def test_whatsapp_antigo_sem_ddi_e_normalizado(s):
    musica = _comprada(s, whatsapp='')
    s.repositorio.atualizar(musica['id'], whatsapp='61981112222')            # gravado pelo quiz antigo
    uc.whatsapp_comprador(s, musica['id'])
    assert s.notificador.whatsapps[0][0] == '5561981112222'


# --------------------------------------------------------- botão e mensagens

def test_botao_manda_o_link_para_quem_ganhou(s):
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    uc.webhook_whatsapp(s, _botao('556182223333', musica['token']))     # a Meta devolve sem o 9
    texto = [w for w in s.notificador.whatsapps if w[1] == 'texto']
    assert len(texto) == 1 and texto[0][0] == '556182223333'
    assert f"/musica/m/{musica['token']}" in texto[0][2][0] and 'Lena' in texto[0][2][0]
    uc.webhook_whatsapp(s, _botao('556182223333', musica['token']))     # tocou de novo logo em seguida
    assert len([w for w in s.notificador.whatsapps if w[1] == 'texto']) == 1


@pytest.mark.parametrize('de,payload,tipo', [
    ('5511999998888', None, 'button'),          # outro número tocou com o token certo
    ('556182223333', 'f' * 32, 'button'),       # token que não existe
    ('556182223333', 'oi, tudo bem?', 'text'),  # mensagem comum: o número não responde
])
def test_o_resto_e_ignorado(s, de, payload, tipo):
    musica = _comprada(s)
    uc.agendar_presente(s, 'g-500', 'Lena', '', '', None, whatsapp='61 98222-3333', confirmo=True)
    uc.enviar_presentes(s)
    antes = len(s.notificador.whatsapps)
    uc.webhook_whatsapp(s, _botao(de, payload or musica['token'], tipo))
    assert len(s.notificador.whatsapps) == antes


# ------------------------------------------------ fora do fluxo de venda

def test_webhook_do_numero_so_avisos_nao_vira_lead(monkeypatch):
    import database
    import whatsapp_orquestrador as orq
    import musica.integracao as integ
    entregues = []
    monkeypatch.setattr(database, 'numero_so_avisos', lambda pid: pid == '1376511528883172')
    monkeypatch.setattr(integ, 'webhook_whatsapp', lambda valor: entregues.append(valor))
    monkeypatch.setattr(orq, 'extrair_dados_mensagem', lambda m: pytest.fail('número só de avisos entrou no fluxo de venda'))
    corpo = {'entry': [{'changes': [{'value': _status('wamid-1', 'delivered')}]}]}
    assert 'Música' in orq.recebe_webhook(corpo)
    assert entregues == [corpo['entry'][0]['changes'][0]['value']]


def test_outros_numeros_seguem_como_antes(monkeypatch):
    import database
    import whatsapp_orquestrador as orq
    seguiu = []
    monkeypatch.setattr(database, 'numero_so_avisos', lambda pid: False)
    monkeypatch.setattr(orq, 'extrair_dados_mensagem', lambda m: seguiu.append(m))
    orq.recebe_webhook({'entry': [{'changes': [{'value': {'metadata': {'phone_number_id': '999'}}}]}]})
    assert seguiu


def test_numero_so_avisos_fora_do_rodizio_da_tela_de_planos_e_do_pedido(monkeypatch):
    import database
    from admin import planos_views
    consultas = []

    class Db:
        def execute_query(self, sql, params=None, **k):
            consultas.append(sql)
            return None
    monkeypatch.setattr(database, 'db', Db())
    monkeypatch.setattr(planos_views, 'db', Db())
    database.get_phone_number_id_produto(17)
    planos_views._tem_whatsapp(17)
    assert all('responde_mensagens = 1' in c for c in consultas) and len(consultas) == 2


# --------------------------------------------------------- envio à Meta

def test_enviar_template_monta_o_botao_com_a_etiqueta(monkeypatch):
    import whatsapp
    enviado = {}

    class Resposta:
        status_code = 200

        def json(self):
            return {'messages': [{'id': 'wamid.ABC'}]}
    monkeypatch.setattr(whatsapp, 'get_whatsapp_api_url', lambda pid: 'https://meta.teste/v1/')
    monkeypatch.setattr(whatsapp, 'get_whatsapp_token', lambda pid: 'tok')
    monkeypatch.setattr(whatsapp, '_timeout_envio', lambda pid: 5)
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda pid: 'meta')
    monkeypatch.setattr(whatsapp.requests, 'post', lambda url, json, **k: enviado.update(url=url, json=json) or Resposta())
    assert whatsapp.enviar_template('1376511528883172', '5561982223333', 'presente_surpresa', ['Lena', 'Patrícia'],
                                    payload_botao='abc') == 'wamid.ABC'
    t = enviado['json']['template']
    assert enviado['url'] == 'https://meta.teste/v1/1376511528883172/messages'
    assert t['name'] == 'presente_surpresa' and t['language'] == {'code': 'pt_BR'}
    assert t['components'][0]['parameters'] == [{'type': 'text', 'text': 'Lena'}, {'type': 'text', 'text': 'Patrícia'}]
    assert t['components'][1] == {'type': 'button', 'sub_type': 'quick_reply', 'index': '0',
                                  'parameters': [{'type': 'payload', 'payload': 'abc'}]}
    whatsapp.enviar_template('1', '55', 'musica_pronta', ['a', 'b', 'c'])
    assert len(enviado['json']['template']['components']) == 1   # sem botão


def test_enviar_template_recusa_gateway_e_trata_rede_como_passageira(monkeypatch):
    import requests
    import whatsapp
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda pid: 'wpp_web')
    with pytest.raises(ValueError, match='gateway'):
        whatsapp.enviar_template('1', '55', 'musica_pronta', ['a', 'b', 'c'])
    monkeypatch.setattr(whatsapp, 'get_provedor_numero', lambda pid: 'meta')
    monkeypatch.setattr(whatsapp, 'get_whatsapp_api_url', lambda pid: 'https://meta.teste/v1/')
    monkeypatch.setattr(whatsapp, 'get_whatsapp_token', lambda pid: 'tok')
    monkeypatch.setattr(whatsapp, '_timeout_envio', lambda pid: 5)

    def demora(*a, **k):
        raise requests.exceptions.ReadTimeout('demorou')
    monkeypatch.setattr(whatsapp.requests, 'post', demora)
    with pytest.raises(whatsapp.ErroTransienteWhatsApp):
        whatsapp.enviar_template('1', '55', 'musica_pronta', ['a', 'b', 'c'])


def test_numero_so_avisos_usa_a_leitura_anterior_se_o_banco_falhar(monkeypatch):
    import database

    class Db:
        def execute_query(self, *a, **k):
            raise RuntimeError('MySQL fora')
    monkeypatch.setattr(database, 'db', Db())
    monkeypatch.setitem(database._CACHE_SO_AVISOS, 'ids', frozenset({'1376511528883172'}))
    monkeypatch.setitem(database._CACHE_SO_AVISOS, 'quando', 0)
    assert database.numero_so_avisos('1376511528883172')
