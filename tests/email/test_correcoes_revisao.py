"""
Correções da revisão de código do atendimento por e-mail (28/09/2026).
"""
from datetime import datetime
from types import SimpleNamespace

import pytest


def test_telefone_gera_as_formas_com_e_sem_o_nove():
    from database import _variantes_telefone
    # Pedidos antigos do WhatsApp guardam 12 dígitos (sem o 9); os novos, 13
    assert _variantes_telefone('(17) 2136-8696') == {'551721368696', '5517921368696'}
    assert _variantes_telefone('17 92136-8696') == {'5517921368696', '551721368696'}
    assert _variantes_telefone('+55 61 99999-8888') == {'5561999998888', '556199998888'}
    assert _variantes_telefone('123') == set()


# ─── envio: reserva atômica ──────────────────────────────────────────────────

@pytest.fixture
def envio(monkeypatch):
    import database
    from fluxos import fluxo_resposta_atendimento as mod
    estado = {'reserva': True, 'enviados': [], 'liberados': [], 'falhar': False}
    atendimento = {'id': 1, 'produto_id': None, 'estado': 'aguardando_aprovacao', 'tipo': 'vendas',
                   'remetente_email': 'c@x.com', 'assunto': 'Oi', 'gmail_thread_id': 't', 'rfc_message_id': None,
                   'resposta_tipo': 'estante_pago', 'pedido_id': None, 'gmail_message_id': 'm'}
    monkeypatch.setattr(database, 'get_email_atendimento', lambda i: atendimento)
    monkeypatch.setattr(database, 'reservar_envio_atendimento', lambda i, por: estado['reserva'])
    monkeypatch.setattr(database, 'liberar_envio_atendimento', lambda i: estado['liberados'].append(i))
    monkeypatch.setattr(database, 'atualizar_email_atendimento', lambda i, **c: None)
    monkeypatch.setattr(mod.labels, 'caixa_atendimento', lambda: 'teste@lsnlivros.com.br')
    monkeypatch.setattr(mod.labels, 'servico', lambda caixa: (_ for _ in ()).throw(RuntimeError('sem gmail')))

    def enviar_gmail(**kw):
        if estado['falhar']:
            raise RuntimeError('Gmail fora')
        estado['enviados'].append(kw['destinatario'])
        return {'id': 'x'}
    monkeypatch.setattr(mod, '_enviar_gmail', enviar_gmail)
    return estado


def test_clique_duplo_nao_manda_dois_emails(envio):
    from fluxos.fluxo_resposta_atendimento import enviar
    enviar(1, '<p>oi</p>', por='admin@x')
    envio['reserva'] = False  # o segundo clique perde a reserva
    with pytest.raises(ValueError, match='já foi respondido'):
        enviar(1, '<p>oi</p>', por='admin@x')
    assert envio['enviados'] == ['c@x.com']


def test_falha_no_gmail_libera_a_reserva(envio):
    from fluxos.fluxo_resposta_atendimento import enviar
    envio['falhar'] = True
    with pytest.raises(RuntimeError, match='Gmail fora'):
        enviar(1, '<p>oi</p>', por='admin@x')
    assert envio['liberados'] == [1]


# ─── triagem e leitor à prova de falha ───────────────────────────────────────

@pytest.mark.parametrize('falha', ['excecao', 'recusa'])
def test_triagem_com_erro_ou_recusa_vai_pro_humano(monkeypatch, falha):
    import agente_triagem_email as mod

    def parse(**kw):
        if falha == 'excecao':
            raise RuntimeError('500 da OpenAI')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=None, refusal='não posso'))])
    monkeypatch.setattr(mod.client.beta.chat.completions, 'parse', parse)
    t = mod.triar_email('Assunto', 'texto', 'admin@', 0)
    assert (t.tipo, t.categoria) == ('vendas', 'outros')


class _GmailFalso:
    """Só o necessário para _processar_mensagem: messages().get() e marcadores."""
    def __init__(self, mensagem):
        self.mensagem = mensagem

    def users(self):
        return self

    def messages(self):
        return self

    def get(self, **kw):
        return SimpleNamespace(execute=lambda: self.mensagem)


def test_erro_na_analise_manda_para_a_fila_humana_em_vez_de_reprocessar(monkeypatch):
    import database
    from fluxos import fluxo_email_conversas as mod
    from fluxos import fluxo_resposta_atendimento
    inseridos, rotulados = [], []
    monkeypatch.setattr(database, 'get_email_atendimento_por_mensagem', lambda m: None)
    monkeypatch.setattr(database, 'inserir_email_atendimento', lambda r: inseridos.append(dict(r)) or 99)
    monkeypatch.setattr(database, 'get_email_atendimento', lambda i: {**inseridos[-1], 'id': i})
    monkeypatch.setattr(database, 'fechar_atendimentos_anteriores_do_thread', lambda t, i: [])
    monkeypatch.setattr(fluxo_resposta_atendimento, 'aplicar_rotulos', lambda s, a: rotulados.append(a['estado']))
    monkeypatch.setattr(mod, '_analisar', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('OpenAI 500')))
    mensagem = {'id': 'm1', 'threadId': 't1', 'internalDate': str(int(datetime(2026, 9, 28).timestamp() * 1000)),
                'payload': {'headers': [{'name': 'From', 'value': 'Maria <maria@gmail.com>'},
                                        {'name': 'To', 'value': 'admin@lsnlivros.com.br'},
                                        {'name': 'Subject', 'value': 'não abre'}]}}
    mod._processar_mensagem(_GmailFalso(mensagem), database, 'm1')
    assert inseridos[0]['estado'] == 'a_responder' and inseridos[0]['categoria'] == 'outros'
    assert 'OpenAI 500' in inseridos[0]['motivo_triagem']
    assert rotulados == ['a_responder']  # recebeu marcador (e o Processado junto): não volta na próxima rodada


def test_detalhe_nao_poe_o_email_do_remetente_dentro_de_javascript():
    import pathlib
    template = pathlib.Path(__file__).parents[2] / 'app/admin/templates/admin/atendimento_email_detalhe.html'
    for linha in template.read_text().splitlines():
        if 'onclick' in linha:
            assert '{{' not in linha, linha


def test_marcador_criado_por_outro_processo_recarrega_o_cache(monkeypatch):
    import httplib2
    from googleapiclient.errors import HttpError
    from fluxos import _gmail_labels as labels
    monkeypatch.setattr(labels, '_cache_ids', {'Sistema/Processado': 'L1', 'Enviados': 'L2'})
    no_gmail = {'Sistema/Processado': 'L1', 'Enviados': 'L2', 'Enviados/Pudim': 'L9'}  # outro worker criou

    class Labels:
        def list(self, userId):
            return SimpleNamespace(execute=lambda: {'labels': [{'name': n, 'id': i} for n, i in no_gmail.items()]})

        def create(self, userId, body):
            def conflito():
                raise HttpError(httplib2.Response({'status': 409}), b'{"error": "exists"}')
            return SimpleNamespace(execute=conflito)

    service = SimpleNamespace(users=lambda: SimpleNamespace(labels=lambda: Labels()))
    assert labels.garantir_label(service, 'Enviados/Pudim') == 'L9'
