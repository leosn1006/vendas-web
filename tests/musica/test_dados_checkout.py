"""O checkout da Música abre com o e-mail e o WhatsApp do quiz (integracao.dados_para_checkout)."""
from types import SimpleNamespace

from musica import integracao


class _Repo:
    def __init__(self, musica):
        self.musica = musica

    def por_token(self, token):
        return self.musica


def _com(monkeypatch, musica):
    monkeypatch.setattr(integracao, 'servicos', lambda: SimpleNamespace(repositorio=_Repo(musica)))


def test_traz_email_e_whatsapp_do_quiz(monkeypatch):
    _com(monkeypatch, {'email': 'ana@gmail.com', 'whatsapp': '5561981163324'})
    assert integracao.dados_para_checkout('t') == {'email': 'ana@gmail.com', 'whatsapp': '5561981163324'}


def test_sem_whatsapp_no_quiz(monkeypatch):
    _com(monkeypatch, {'email': 'ana@gmail.com', 'whatsapp': None})
    assert integracao.dados_para_checkout('t') == {'email': 'ana@gmail.com', 'whatsapp': ''}


def test_token_desconhecido(monkeypatch):
    _com(monkeypatch, None)
    assert integracao.dados_para_checkout('t') == {}


def test_quiz_antigo_sem_o_55(monkeypatch):
    _com(monkeypatch, {'email': 'ana@gmail.com', 'whatsapp': '61981163324'})
    assert integracao.dados_para_checkout('t')['whatsapp'] == '5561981163324'


def test_numero_de_fora_ou_fixo_nao_preenche(monkeypatch):
    for numero in ('14155550123', '351912345678', '556133224455'):
        _com(monkeypatch, {'email': 'ana@gmail.com', 'whatsapp': numero})
        assert integracao.dados_para_checkout('t')['whatsapp'] == '', numero
