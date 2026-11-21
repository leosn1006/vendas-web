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


@pytest.mark.parametrize('texto', [
    # frase real (pedido 459672), com o erro de escrita
    'Só começa quando eu compra as coisas também, eu perde as confianças da minha família, só porque eu tentei '
    'tira a minha vida,é escondendo faca é tudo',
    'perdi a confiança porque tentei tirar a minha vida', 'tentei me matar', 'to pensando em me matar',
    'vou me mata', 'quero morrer', 'to com vontade de morrer', 'não quero mais viver',
    'não aguento mais viver', 'pensei em suicídio', 'vou acabar com a minha vida', 'pensei em tirar a própria vida',
    'vontade de me enforcar', 'quero morrer, de verdade', 'vontade de morrer, de tão cansada',
    # revisão de 21/11: "de" no começo de outra palavra e outras formas de intenção
    'vou me matar depois que meu filho dormir', 'quero morrer dessa vez', 'eu queria me matar', 'quis me matar',
    'tenho desejo de me matar', 'quero muito me matar', 'queria tirar a própria vida', 'queria morrer',
])
def test_fala_explicita_de_risco_a_vida(texto):
    from fluxos._mensagem_sem_resposta import fala_em_risco_a_vida
    assert fala_em_risco_a_vida(texto) is True


@pytest.mark.parametrize('texto', [
    # desabafo de saúde (caso real de 18/11): a IA escala, mas a resposta é só carinho, sem CVV
    'Hoje a pressão está alta e a diabetes também mas vou ficar bem em nome de Jesus',
    'não aguento mais essa vida de dor nas costas', 'Morri de rir com a receita', 'isso me mata de rir',
    'essa receita me mata de vontade', 'quero morrer de tanto comer esse bolo kkk', 'vontade de morrer de rir',
    'quero morrer de vergonha', 'tentei me comunicar com vocês e nada', 'obrigada', None, '',
    # exagero e terceiros (revisão de 21/11)
    'esse doce vai me matar kkk', 'se eu comer isso vou morrer', 'prefiro morrer do que pagar isso',
    'o diabetes tira a vida de muita gente', 'meu marido vai me matar', 'meu marido quer me matar',
])
def test_nao_e_fala_explicita(texto):
    from fluxos._mensagem_sem_resposta import fala_em_risco_a_vida
    assert fala_em_risco_a_vida(texto) is False
