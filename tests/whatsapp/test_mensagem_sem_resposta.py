"""
Mensagens que não pedem resposta ficam sem resposta (economia de mensagens do WhatsApp, nov/2026).
Os exemplos positivos e negativos são mensagens reais de clientes, das conversas analisadas em produção.
"""
import pytest

from fluxos._mensagem_sem_resposta import mensagem_sem_resposta


@pytest.mark.parametrize('texto', [
    '👍', '👆', '🙏🙏', '❤️',
    'Obrigada', 'Muito obrigada!', 'Obrigada Deus abençoe', 'Deus continue te abençoando', 'Amém 🙏🙏',
    'Obrigada, boa noite', 'ok', 'Ok, obrigada',
])
def test_silencia_em_qualquer_estado(texto):
    assert mensagem_sem_resposta(texto) is True
    assert mensagem_sem_resposta(texto, pedido_pago=True) is True


@pytest.mark.parametrize('texto', [
    'obrigada, mas não abriu', 'segue o comprovante, cadê o bônus?', 'quanto é?', 'Coloquei 30',
    'não recebi', '61900000000', 'Depois q eu receber vou enviar um pouco mais',
    'sim',   # pode ser resposta a uma pergunta da IA
    'Oi',    # abre conversa
    'Pix',   # pode ser pedido da chave
    'Bom dia', 'Boa tarde tudo bem', 'Boa noite querida',  # saudação sozinha abre conversa
    'tata', 'okta', 'lindaflor',  # expressões coladas sem espaço não são a lista
    'Mais eu não lhe paguei a minha prima disse só pode paga no começo do mês',
    '', None,
])
def test_vai_para_a_ia(texto):
    assert mensagem_sem_resposta(texto) is False
    assert mensagem_sem_resposta(texto, pedido_pago=True) is False


@pytest.mark.parametrize('texto', [
    'Já fiz o pix', 'paguei', 'Já paguei viu', 'pronto, enviei', 'feito',
    'Segue', 'Segui comprovante de pagamento.', 'Segue comprovante', 'Aí está o comprovante 👆', 'Aí o comprovante',
    'Olhe o comprovante obrigada', 'Confira por gentileza', 'Está aí muito obrigado Deus abençoe vc 🙏🙏',
])
def test_aviso_de_pagamento_so_silencia_pedido_pago(texto):
    """Em pedido não pago, o aviso precisa chegar à IA, que registra o pagamento informado (se a imagem não vier,
    a cliente não fica sem resposta nem continua sendo cobrada)."""
    assert mensagem_sem_resposta(texto) is False
    assert mensagem_sem_resposta(texto, pedido_pago=True) is True


def test_mensagem_longa_vai_para_a_ia():
    assert mensagem_sem_resposta('obrigada ' * 10) is False


@pytest.mark.parametrize('texto,esperado', [
    ('perdi a confiança porque tentei tirar a minha vida', True), ('quero morrer', True),
    ('tentei me matar', True),
    ('Morri de rir com a receita', False), ('obrigada', False), (None, False),
    ('tentei me comunicar com vocês e nada', False), ('essa receita me mata de vontade', False),
    ('quero morrer de tanto comer esse bolo kkk', False), ('vontade de morrer de rir', False),
    ('to com vontade de morrer', True),
])
def test_fala_em_risco_a_vida(texto, esperado):
    from fluxos._mensagem_sem_resposta import fala_em_risco_a_vida
    assert fala_em_risco_a_vida(texto) is esperado
