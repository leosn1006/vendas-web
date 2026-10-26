"""Tema do checkout por produto (web/tema_checkout.py, migration 093)."""
import pytest

from web.tema_checkout import _rgb, contraste, tema_checkout

PRODUTOS = {
    'musica': ('#0F0E0D', '#FB7185'),
    'fatia': ('#0F0C0A', '#D7473C'),
    'tempero': ('#0C0A09', '#10B981'),
}


def _tema(fundo, destaque, marca='Canção de Presente'):
    return tema_checkout({'checkout_cor_fundo': fundo, 'checkout_cor_destaque': destaque, 'checkout_marca': marca})


@pytest.mark.parametrize('fundo,destaque', [
    (None, '#FB7185'), ('#0F0E0D', None), ('', ''), ('0F0E0D', '#FB7185'), ('#0F0E0D', '#FB71'),
    ('#0F0E0D', 'red'), ('#0F0E0D;}body{', '#FB7185'),
])
def test_sem_cor_valida_fica_o_checkout_padrao(fundo, destaque):
    assert _tema(fundo, destaque) is None
    assert tema_checkout(None) is None


@pytest.mark.parametrize('nome', PRODUTOS)
def test_destaque_legivel_sobre_o_card_branco(nome):
    tema = _tema(*PRODUTOS[nome])
    assert contraste(_rgb(tema['destaque_texto']), (255, 255, 255)) >= 4.5


@pytest.mark.parametrize('nome', PRODUTOS)
def test_texto_do_botao_legivel(nome):
    tema = _tema(*PRODUTOS[nome])
    assert contraste(_rgb(tema['sobre_destaque']), _rgb(tema['destaque'])) >= 3


def test_texto_do_botao_branco_no_vermelho_e_escuro_no_rosa():
    assert _tema(*PRODUTOS['fatia'])['sobre_destaque'] == '#FFFFFF'
    assert _tema(*PRODUTOS['musica'])['sobre_destaque'] != '#FFFFFF'


def test_marca_e_inicial():
    tema = _tema(*PRODUTOS['musica'])
    assert tema['marca'] == 'Canção de Presente' and tema['inicial'] == 'C'
    assert _tema(*PRODUTOS['musica'], marca=None)['marca'] == ''
