"""Textos dos e-mails da Música (o corpo; a moldura com as cores do produto vem do notificador).
Público 35+: frases curtas, um botão grande."""
import html


def _p(texto):
    return f'<p style="font-size:18px; line-height:1.5; color:#1e1e1c; margin:0 0 16px;">{texto}</p>'


def _botao(rotulo, url):
    return (f'<p style="margin:24px 0; text-align:center;"><a href="{html.escape(url)}" '
            f'style="display:inline-block; background:#E11D48; color:#ffffff; text-decoration:none; font-size:18px; '
            f'font-weight:bold; padding:16px 28px; border-radius:16px;">{html.escape(rotulo)}</a></p>')


def presente(nome_quem_recebe, de, titulo, mensagem, link):
    """E-mail para quem ganha a música (com cópia para quem comprou). Só o link: nada anexado."""
    e = html.escape
    corpo = _p(f'Oi, {e(nome_quem_recebe)}!')
    corpo += _p(f'<b>{e(de)}</b> preparou uma surpresa para você: uma música feita só para você 🎁🎵')
    if mensagem:
        corpo += _p(f'<i>“{e(mensagem)}”</i>')
    corpo += _botao(f'Ouvir “{titulo}”', link)
    corpo += _p('Na página você ouve, baixa e guarda a música.')
    return f'{de} fez uma música para você 🎵', corpo


def presente_nao_entregue(nome_quem_recebe, email, link, tentativas):
    """Para quem comprou: o e-mail do presente não chegou em nenhuma tentativa (quase sempre caixa lotada)."""
    e = html.escape
    corpo = _p(f'Tentamos {tentativas} vezes, mas o e-mail com a música não chegou para <b>{e(nome_quem_recebe)}</b> '
               f'({e(email)}). Quase sempre é a caixa de e-mail cheia.')
    corpo += _p('Você recebeu uma cópia de cada envio. Para entregar o presente, mande este link para '
                f'{e(nome_quem_recebe)} pelo WhatsApp ou por mensagem:')
    corpo += _botao('Abrir a música do presente', link)
    corpo += _p(f'<span style="font-size:15px; color:#555;">{e(link)}</span>')
    return f'Não conseguimos entregar a música para {nome_quem_recebe}', corpo


# Lembretes (docs/MUSICA.md "Lembretes"): etapa → os 3 e-mails (15 min, 3 h, 24 h) como (assunto, parágrafos, botão).
# {oi}/{de_} = saudação/vocativo com o primeiro nome de quem cria (ou sem nome), {para} = nome de quem recebe. Sem urgência falsa: a música fica guardada 90 dias.
_LEMBRETES = {
    'letra': (
        ('A letra de {para} ficou pronta ✍️',
         ['{oi} A letra que você criou para <b>{para}</b> está te esperando.',
          'Leia, ajuste se quiser e toque em <b>Criar a música</b>: em poucos minutos você ouve como ficou.'],
         'Ver a letra'),
        ('Falta só um toque para ouvir a música de {para}',
         ['{de_}você já fez a parte mais difícil: contou a história.',
          'Agora é só criar a música e ouvir um trecho. Você só paga se gostar.'],
         'Criar a música'),
        ('{para} vai se emocionar 💛',
         ['{de_}a letra continua guardada.',
          'Imagina a reação de <b>{para}</b> ouvindo o próprio nome cantado. Leva só um minuto.'],
         'Ouvir como fica'),
    ),
    'previa': (
        ('Gostou da música de {para}? 🎶',
         ['{oi} Você ouviu um trecho da música de <b>{para}</b>.',
          'As duas versões completas ficam liberadas na hora, depois do pagamento.'],
         'Ouvir de novo'),
        ('A música de {para} está te esperando',
         ['{de_}ela ficou linda, e é única: foi feita com a história de vocês.',
          'Libere a versão completa e guarde para sempre.'],
         'Liberar a música'),
        ('Imagina a reação de {para}…',
         ['{de_}a música continua guardada aqui.',
          'Um presente que ninguém mais no mundo tem, com o nome de <b>{para}</b>.'],
         'Ouvir a música'),
    ),
    'checkout': (
        ('Ficou alguma dúvida no pagamento?',
         ['{oi} Vimos que você começou a liberar a música de <b>{para}</b>.',
          'Se algo deu errado no PIX ou no cartão, é só continuar de onde parou. Dúvidas? Responda este e-mail.'],
         'Continuar o pagamento'),
        ('A música de {para} está quase sua 🎁',
         ['{de_}falta só o pagamento para liberar a música completa.',
          'Pagamento seguro, no PIX ou no cartão, e a música chega na hora.'],
         'Liberar a música'),
        ('Ainda dá tempo de surpreender {para}',
         ['{de_}seu pedido continua guardado com tudo o que você escolheu.', 'É só finalizar.'],
         'Finalizar o pedido'),
    ),
}


def _maiuscula(texto):
    return texto[:1].upper() + texto[1:]


def lembrete(etapa, numero, de, para, link, link_sair):
    """Lembrete `numero` (1, 2 ou 3) da `etapa` (letra, previa, checkout), com o link de sair no rodapé."""
    e = html.escape
    assunto, paragrafos, botao = _LEMBRETES[etapa][numero - 1]
    # {oi} = "Oi, Leo!" ou "Oi!"; {de_} = "Leo, " ou nada (sem nome, a frase começa direto, com maiúscula)
    trocas = {'oi': f'Oi, {e(de)}!' if de else 'Oi!', 'de_': f'{e(de)}, ' if de else '', 'para': e(para or 'quem você ama')}
    corpo = ''.join(_p(_maiuscula(t.format(**trocas))) for t in paragrafos) + _botao(botao, link)
    corpo += (f'<p style="font-size:13px; color:#888; margin:24px 0 0; text-align:center;">Não quer mais estes lembretes? '
              f'<a href="{e(link_sair)}" style="color:#888;">Clique aqui</a>.</p>')
    return assunto.format(de=de or '', para=para or 'quem você ama'), corpo


def presente_whatsapp_nao_chegou(nome_quem_recebe, link):
    """Para quem comprou: o WhatsApp do presente não chegou (número errado, sem WhatsApp, bloqueio da Meta)."""
    e = html.escape
    corpo = _p(f'Não conseguimos entregar a música no WhatsApp de <b>{e(nome_quem_recebe)}</b>. Pode ser o número '
               'ou alguma configuração do WhatsApp da pessoa.')
    corpo += _p('Para a surpresa não se perder, toque no botão e mande pelo seu WhatsApp — a mensagem e o link já vão '
                'prontos:')
    corpo += _botao(f'Enviar para {nome_quem_recebe}', link)
    return f'Envie a música para {nome_quem_recebe} pelo seu WhatsApp 🎁', corpo


def presente_chegou(nome_quem_comprou, nome_quem_recebe):
    """Para quem comprou e não deu WhatsApp: a música chegou no WhatsApp de quem ganhou."""
    e = html.escape
    corpo = _p(f'Pronto, {e(nome_quem_comprou)}! 🎁') + _p(f'A música chegou no WhatsApp de <b>{e(nome_quem_recebe)}</b> '
                                                             'agora há pouco. Agora é só esperar a reação ❤️')
    return f'A música chegou para {nome_quem_recebe} 🎁', corpo


def link_do_presente(nome_quem_recebe, de, link):
    """Texto livre (WhatsApp) quando quem ganhou toca em "Ouvir minha música"."""
    linhas = [f'Aperte o play, {nome_quem_recebe} 🎵', link]
    if de:
        linhas += ['', f'Com carinho, {de}.']
    return '\n'.join(linhas)

