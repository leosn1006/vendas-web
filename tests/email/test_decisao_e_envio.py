"""
Decisão (triagem × vínculo → resposta), textos prontos, proteção do dev e regras do envio
automático do atendimento por e-mail.
"""
import pytest

from tests.email.conftest import pedido
from fluxos import email_respostas
from fluxos.email_respostas import decidir, montar_resposta, primeiro_nome
from fluxos.email_vinculo import Vinculo

PRODUTO = {'id': 11, 'nome': 'Temperos Caseiros no Pote', 'email_nome_remetente': 'Luiza',
           'url_pagina_vendas': '/tempero-e', 'email_cor_primaria': '#aa3300'}


def _d(categoria, vinculo=None, produto=PRODUTO, tipo='vendas', chave_pix=False):
    return decidir(tipo, categoria, vinculo or Vinculo(), produto, chave_pix)


# ─── tabela de decisão ───────────────────────────────────────────────────────

def test_pago_recebe_link_da_estante():
    d = _d('acesso_estante', Vinculo(pedido(1, 1000, 'a@x.com'), 'email'))
    assert (d.estado, d.resposta_tipo) == ('aguardando_aprovacao', 'estante_pago')


def test_ja_pagou_e_foi_cobrado_tambem_recebe_a_estante():
    d = _d('pagou_e_cobrado', Vinculo(pedido(1, 0, phone='5561'), 'nome'))
    assert d.resposta_tipo == 'estante_pago'


def test_site_nao_pago_recebe_pagina_de_vendas_e_sem_url_vai_pro_humano():
    v = Vinculo(pedido(1, 1002, 'a@x.com'), 'email')
    assert _d('acesso_estante', v).resposta_tipo == 'pagina_vendas_nao_pago'
    assert _d('acesso_estante', v, produto={**PRODUTO, 'url_pagina_vendas': None}).estado == 'a_responder'


def test_whatsapp_nao_pago_so_recebe_estante_se_o_livro_ja_foi_entregue(monkeypatch):
    v = Vinculo(pedido(1, 4, phone='5561'), 'telefone')
    monkeypatch.setattr(email_respostas, '_entregue_whatsapp', lambda p: True)
    assert _d('acesso_estante', v).resposta_tipo == 'estante_nao_pago_wpp'
    monkeypatch.setattr(email_respostas, '_entregue_whatsapp', lambda p: False)
    assert _d('acesso_estante', v).estado == 'a_responder'


def test_sem_pedido_pede_dados_ou_explica_a_chave_pix():
    assert _d('acesso_estante').resposta_tipo == 'pedir_dados'
    assert _d('chave_pix').resposta_tipo == 'chave_pix'
    assert _d('acesso_estante', chave_pix=True).resposta_tipo == 'chave_pix'


@pytest.mark.parametrize('categoria', ['pagamento', 'reclamacao'])
def test_pagamento_e_reclamacao_vao_para_humano_mesmo_com_pedido_pago(categoria):
    d = _d(categoria, Vinculo(pedido(1, 1000, 'a@x.com'), 'email'))
    assert (d.estado, d.resposta_tipo) == ('a_responder', None)


def test_nome_ambiguo_vai_para_humano():
    d = _d('acesso_estante', Vinculo(candidatos=[pedido(1, 1000), pedido(2, 1000)]))
    assert (d.estado, d.resposta_tipo) == ('a_responder', None)


def test_agradecimento_ruido_e_administrativo():
    assert _d('agradecimento').estado == 'sem_acao'
    assert _d('ruido', tipo='ruido').estado == 'sem_acao'
    assert _d('administrativo', tipo='administrativo').estado == 'a_responder'


def test_duvida_de_uso_com_pedido_usa_a_ia_e_sem_pedido_vai_pro_humano():
    assert _d('duvida_uso', Vinculo(pedido(1, 1000, 'a@x.com'), 'email')).resposta_tipo == 'ia'
    assert _d('duvida_uso').estado == 'a_responder'


# ─── textos ──────────────────────────────────────────────────────────────────

@pytest.fixture
def links(monkeypatch):
    import database
    monkeypatch.setattr(database, 'garantir_guid_pedido', lambda pid: 'AbCd1234')
    monkeypatch.setenv('APP_BASE_URL', 'https://lsnlivros.com.br')


def test_estante_pago_tem_numero_link_da_estante_2_e_assinatura(links):
    html = montar_resposta('estante_pago', pedido(287055, 1000, 'a@x.com', dns_origem='lclivros.com.br'),
                           PRODUTO, 'Vera')
    assert 'Olá, Vera!' in html
    assert '#287055' in html
    assert 'https://lclivros.com.br/pedido2/AbCd1234' in html  # domínio de onde a cliente veio
    assert 'Luiza' in html and '#aa3300' in html


def test_sem_dns_origem_usa_o_dominio_padrao(links):
    html = montar_resposta('estante_pago', pedido(5, 0, phone='5561'), PRODUTO, '')
    assert 'https://lsnlivros.com.br/pedido2/AbCd1234' in html and 'Olá! Tudo bem?' in html


def test_pagina_de_vendas_relativa_vira_link_absoluto(links):
    html = montar_resposta('pagina_vendas_nao_pago', pedido(5, 1002, 'a@x.com'), PRODUTO, 'Ana')
    assert 'https://lsnlivros.com.br/tempero-e' in html


def test_chave_pix_explica_o_endereco_e_pede_dados_sem_produto(links):
    html = montar_resposta('chave_pix', None, None, 'Selma', destinatario='pudim@lsnlivros.com.br')
    assert 'pudim@lsnlivros.com.br' in html and 'comprovante' in html
    assert 'Equipe LBE Livros' in html  # sem produto: assinatura neutra


def test_primeiro_nome_ignora_email_e_digitos():
    assert primeiro_nome('dalmo46@bol.com.br', 'DALMO SILVA') == 'Dalmo'
    assert primeiro_nome('', None) == ''


# ─── proteção do dev e marcadores ────────────────────────────────────────────

def test_dev_nunca_usa_a_caixa_de_producao(monkeypatch):
    from fluxos import _gmail_labels as labels
    monkeypatch.setattr(labels, 'EH_PRODUCAO', False)
    monkeypatch.delenv('EMAIL_ATENDIMENTO_CAIXA', raising=False)
    assert labels.caixa_atendimento() is None
    monkeypatch.setenv('EMAIL_ATENDIMENTO_CAIXA', 'admin@lsnlivros.com.br')
    assert labels.caixa_atendimento() is None
    monkeypatch.setenv('EMAIL_ATENDIMENTO_CAIXA', 'teste@lsnlivros.com.br')
    assert labels.caixa_atendimento() == 'teste@lsnlivros.com.br'
    monkeypatch.setattr(labels, 'EH_PRODUCAO', True)
    monkeypatch.delenv('EMAIL_ATENDIMENTO_CAIXA')
    assert labels.caixa_atendimento() == 'admin@lsnlivros.com.br'


def test_marcador_de_status_troca_o_anterior():
    from fluxos._gmail_labels import rotulos_do_estado
    add, rem = rotulos_do_estado('vendas', 'respondido')
    assert add == ['Atendimento/Respondido']
    assert 'Atendimento/A responder' in rem and 'Atendimento/Respondido' not in rem
    add, _ = rotulos_do_estado('administrativo', 'a_responder')
    assert add == ['Administrativo/A responder']
    assert rotulos_do_estado('ruido', 'sem_acao')[0] == ['Ruído']


# ─── envio automático e atalhos da triagem ──────────────────────────────────

@pytest.fixture
def auto(monkeypatch):
    import database
    estado = {'thread_respondido': False, 'recentes': 0}
    monkeypatch.setattr(database, 'thread_email_ja_respondido', lambda t: estado['thread_respondido'])
    monkeypatch.setattr(database, 'contar_respostas_automaticas_recentes', lambda e, horas=24: estado['recentes'])
    monkeypatch.setenv('EMAIL_ATENDIMENTO_AUTO_TIPOS', 'estante_pago,pedir_dados')
    return estado


def test_fase_1_sem_tipos_liberados_nada_sai_sozinho(monkeypatch, auto):
    from fluxos.fluxo_email_conversas import _pode_enviar_sozinho
    monkeypatch.setenv('EMAIL_ATENDIMENTO_AUTO_TIPOS', '')
    assert not _pode_enviar_sozinho('estante_pago', 'email', 't', 'a@x.com')


def test_envio_automatico_so_com_identificacao_forte(auto):
    from fluxos.fluxo_email_conversas import _pode_enviar_sozinho
    assert _pode_enviar_sozinho('estante_pago', 'email', 't', 'a@x.com')
    assert not _pode_enviar_sozinho('estante_pago', 'nome', 't', 'a@x.com')
    assert not _pode_enviar_sozinho('estante_pago', 'comprovante', 't', 'a@x.com')
    assert not _pode_enviar_sozinho('chave_pix', None, 't', 'a@x.com')  # tipo não liberado
    assert _pode_enviar_sozinho('pedir_dados', None, 't', 'a@x.com')


def test_anti_loop_e_limite_de_24h(auto):
    from fluxos.fluxo_email_conversas import _pode_enviar_sozinho
    auto['thread_respondido'] = True
    assert not _pode_enviar_sozinho('estante_pago', 'email', 't', 'a@x.com')
    auto['thread_respondido'], auto['recentes'] = False, 1
    assert not _pode_enviar_sozinho('estante_pago', 'email', 't', 'a@x.com')


def test_atalhos_da_triagem_nao_chamam_a_ia(monkeypatch):
    import agente_triagem_email
    from fluxos.fluxo_email_conversas import _triar

    def ia(*a, **k):
        raise AssertionError('não devia chamar a IA')
    monkeypatch.setattr(agente_triagem_email, 'triar_email', ia)
    assert _triar('', '', 'pudim@lsnlivros.com.br', [], True).categoria == 'chave_pix'
    assert _triar('pudim@lsnlivros.com.br', 'Pagamento', 'pudim@', [], True).categoria == 'chave_pix'
    assert _triar('Muito obrigada!', 'Re: Pedido', 'admin@', [], False).categoria == 'agradecimento'
    # Dúvida de pagamento para a chave PIX não cai no atalho: a IA decide (vai p/ humano)
    with pytest.raises(AssertionError, match='não devia chamar a IA'):
        _triar('Não consigo fazer seu Pix', '', 'pudim@lsnlivros.com.br', [], True)
    with pytest.raises(AssertionError, match='não devia chamar a IA'):
        _triar('Quero enviar 20 reais pelo pix do livro', '', 'pudim@lsnlivros.com.br', [], True)


def test_ruido_por_cabecalho_e_por_remetente_mas_nao_cliente_gmail():
    from fluxos.fluxo_email_conversas import _e_ruido
    assert _e_ruido('news@loja.com', {'list-unsubscribe': '<mailto:x>'})
    assert _e_ruido('ads-account-noreply@google.com', {})
    assert _e_ruido('comunicado@bbclientesmpe.com.br', {})
    assert not _e_ruido('maria.silva@gmail.com', {})
    assert not _e_ruido('cliente@hotmail.com', {})


def test_resposta_da_equipe_nao_vira_pendencia(monkeypatch):
    from fluxos.fluxo_email_conversas import _e_da_equipe
    monkeypatch.setenv('EMAIL_ATENDIMENTO_EQUIPE', 'lneditoraadm@gmail.com, outra@gmail.com')
    assert _e_da_equipe('lneditoraadm@gmail.com')
    assert _e_da_equipe('pudim@lsnlivros.com.br')
    assert not _e_da_equipe('cliente@gmail.com')


def test_resposta_de_email_antigo_pede_desculpas_pela_demora(links):
    from datetime import datetime, timedelta
    from fluxos.email_respostas import e_atrasada
    assert e_atrasada(datetime.now() - timedelta(days=4))
    assert not e_atrasada(datetime.now() - timedelta(hours=5))
    ped = pedido(5, 1000, 'a@x.com')
    assert 'Desculpe a demora' in montar_resposta('estante_pago', ped, PRODUTO, 'Ana', atrasada=True)
    assert 'Desculpe a demora' not in montar_resposta('estante_pago', ped, PRODUTO, 'Ana')


def test_remetente_da_resposta(monkeypatch):
    from fluxos import _gmail_labels as labels
    from fluxos.fluxo_resposta_atendimento import escolher_remetente
    producao = labels.CAIXA_PRODUCAO
    monkeypatch.delenv('EMAIL_ATENDIMENTO_REMETENTE', raising=False)
    # Com produto: o alias do produto (mesma persona da entrega e das cobranças)
    assert escolher_remetente(producao, {'email_remetente': 'tempero@lsnlivros.com.br'}) == 'tempero@lsnlivros.com.br'
    # Sem produto: suporte, nunca o admin@
    assert escolher_remetente(producao, None) == 'suporte@lsnlivros.com.br'
    assert escolher_remetente(producao, {'email_remetente': None}) == 'suporte@lsnlivros.com.br'
    monkeypatch.setenv('EMAIL_ATENDIMENTO_REMETENTE', 'ajuda@lsnlivros.com.br')
    assert escolher_remetente(producao, None) == 'ajuda@lsnlivros.com.br'
    # Dev: sempre a caixa de teste
    assert escolher_remetente('teste@lsnlivros.com.br', {'email_remetente': 'tempero@lsnlivros.com.br'}) == 'teste@lsnlivros.com.br'


def test_pedido_nao_pago_com_comprovante_anexado_vai_para_o_humano():
    v = Vinculo(pedido(1, 4, phone='5561'), 'nome')
    d = decidir('vendas', 'chave_pix', v, PRODUTO, True, tem_comprovante=True)
    assert (d.estado, d.resposta_tipo) == ('a_responder', None)
    # Pago continua recebendo a Estante mesmo com anexo
    d = decidir('vendas', 'pagou_e_cobrado', Vinculo(pedido(2, 1000, 'a@x.com'), 'email'), PRODUTO, False, True)
    assert d.resposta_tipo == 'estante_pago'
