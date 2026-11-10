"""
Imagem com legenda (caption) no WhatsApp.

Por que importa: juntar imagem + texto numa mensagem só diminui a quantidade de mensagens cobradas pela
Meta. Sem legenda o envio tem de continuar idêntico ao de antes (payload sem 'caption').
"""
import pytest

import whatsapp
from fluxos import _executor_acao as executor


class _Resp:
    status_code = 200

    def json(self):
        return {'messages': [{'id': 'wamid.X'}]}


@pytest.fixture
def captura_post(monkeypatch, provedores):
    provedores['web-1'] = 'wpp_web'   # payload é o mesmo para Meta e gateway; só evita consultar o banco
    chamadas = []

    def fake_post(url, headers=None, json=None, timeout=None):
        chamadas.append({'url': url, 'json': json})
        return _Resp()

    monkeypatch.setattr(whatsapp.requests, 'post', fake_post)
    monkeypatch.setattr(whatsapp, 'get_whatsapp_token', lambda _pid: 'token-teste')
    monkeypatch.setattr(whatsapp, 'get_whatsapp_api_url', lambda _pid: 'http://api/v24.0/')
    return chamadas


PEDIDO = {'id': 7, 'phone_number_id': 'web-1', 'contact_to': '556181163324', 'contact_name': 'Maria Silva'}


def test_imagem_com_legenda_vai_no_payload(captura_post):
    whatsapp.enviar_imagem(PEDIDO, 'https://x.com/a.jpg', caption='  Olha que lindo\nsegunda linha ')
    assert captura_post[0]['json']['image'] == {'link': 'https://x.com/a.jpg',
                                                 'caption': 'Olha que lindo\nsegunda linha'}


@pytest.mark.parametrize('legenda', [None, '', '   '])
def test_imagem_sem_legenda_nao_manda_caption(captura_post, legenda):
    whatsapp.enviar_imagem(PEDIDO, 'https://x.com/a.jpg', caption=legenda)
    assert captura_post[0]['json']['image'] == {'link': 'https://x.com/a.jpg'}


def test_imagem_assinatura_antiga_continua_valendo(captura_post):
    whatsapp.enviar_imagem(PEDIDO, 'https://x.com/a.jpg')
    assert 'caption' not in captura_post[0]['json']['image']


# ─── ação de fluxo enviar_imagem: legenda vem de 'mensagem' ─────────────────────

def _acao(mensagem):
    return {'acao': 'enviar_imagem', 'url': 'https://x.com/a.jpg', 'mensagem': mensagem, 'caption': None,
            'nome_arquivo': None, 'delay_inicial': 0, 'delay_final': 0, 'produto_id': 1,
            'fluxo': 'introducao', 'condicao': 'sempre', 'ordem': 1}


@pytest.fixture
def executor_imagem(monkeypatch):
    enviados, historico = [], []
    monkeypatch.setattr(executor, 'exigir_numero_operacional', lambda _p: None)
    monkeypatch.setattr(executor, 'enviar_imagem',
                        lambda pedido, url, caption='': enviados.append((url, caption)) or 'wamid.X')
    monkeypatch.setattr(executor, 'salvar_mensagem_pedido', lambda mid, pid, texto, **k: historico.append(texto))
    return enviados, historico


def test_acao_imagem_com_legenda_troca_nome_cliente(executor_imagem):
    enviados, historico = executor_imagem
    executor.executar_acao(_acao('Oi @nome_cliente, veja!'), PEDIDO, None, 7, aplicar_delay=False)
    assert enviados == [('https://x.com/a.jpg', 'Oi Maria, veja!')]
    assert historico == ['[imagem] Oi Maria, veja!']


def test_acao_imagem_antiga_sem_mensagem_sai_sem_legenda(executor_imagem):
    enviados, historico = executor_imagem
    executor.executar_acao(_acao(None), PEDIDO, None, 7, aplicar_delay=False)
    assert enviados == [('https://x.com/a.jpg', '')]
    assert historico == ['[imagem enviada]']


def test_legenda_com_quebra_de_linha_do_formulario_vira_lf(captura_post):
    whatsapp.enviar_imagem(PEDIDO, 'https://x.com/a.jpg', caption='linha 1\r\nlinha 2')
    assert captura_post[0]['json']['image']['caption'] == 'linha 1\nlinha 2'


def test_legenda_acima_do_limite_e_cortada_e_imagem_sai_mesmo_assim(captura_post):
    """Ex.: @nome_cliente trocado por nome comprido estoura o limite — a cliente recebe a imagem igual."""
    whatsapp.enviar_imagem(PEDIDO, 'https://x.com/a.jpg', caption='a' * 1100)
    legenda = captura_post[0]['json']['image']['caption']
    assert len(legenda) == whatsapp.LIMITE_LEGENDA_IMAGEM
    assert legenda.endswith('…')


def test_legenda_no_limite_exato_nao_e_cortada(captura_post):
    whatsapp.enviar_imagem(PEDIDO, 'https://x.com/a.jpg', caption='a' * 1024)
    assert captura_post[0]['json']['image']['caption'] == 'a' * 1024


# ─── validação no admin ──────────────────────────────────────────────────────────

def test_admin_conta_quebra_de_linha_como_o_navegador():
    from admin.views import _validar_legenda_imagem
    _validar_legenda_imagem('enviar_imagem', ('x' * 99 + '\r\n') * 10)   # 1000 caracteres para o navegador


def test_admin_recusa_legenda_de_imagem_grande_e_ignora_outras_acoes():
    from admin.views import _validar_legenda_imagem
    with pytest.raises(ValueError):
        _validar_legenda_imagem('enviar_imagem', 'a' * 1025)
    _validar_legenda_imagem('enviar_mensagem', 'a' * 5000)
