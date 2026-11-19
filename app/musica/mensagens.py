"""Textos dos e-mails da Música (o corpo; a moldura com as cores do produto vem do notificador).
Público 35+: frases curtas, um botão grande."""
import html


def _p(texto):
    return f'<p style="font-size:18px; line-height:1.5; color:#1e1e1c; margin:0 0 16px;">{texto}</p>'


def _botao(rotulo, url):
    return (f'<p style="margin:24px 0; text-align:center;"><a href="{html.escape(url)}" '
            f'style="display:inline-block; background:#E11D48; color:#ffffff; text-decoration:none; font-size:18px; '
            f'font-weight:bold; padding:16px 28px; border-radius:16px;">{html.escape(rotulo)}</a></p>')


def _brasil(idioma):
    """Os e-mails do Brasil são os textos deste arquivo (iguais aos de antes dos idiomas); os de outro idioma vêm do
    textos.json dele ("emails", "lembretes")."""
    from musica import idiomas
    return idiomas.valido(idioma) == idiomas.IDIOMA_PADRAO


def _txt(idioma, chave, escapar=True, **valores):
    """Frase de textos.json → emails.<chave>, com os valores escapados (corpo HTML) ou não (assunto, rótulo do botão,
    que _botao já escapa)."""
    from musica.idiomas import texto
    return texto(idioma, f'emails.{chave}',
                 **{k: (html.escape(str(v)) if escapar else v) for k, v in valores.items()})


def presente(nome_quem_recebe, de, titulo, mensagem, link, idioma=None):
    """E-mail para quem ganha a música (com cópia para quem comprou). Só o link: nada anexado."""
    e = html.escape
    if not _brasil(idioma):
        corpo = _p(_txt(idioma, 'presente_oi', nome=nome_quem_recebe)) + _p(_txt(idioma, 'presente_texto', de=de))
        if mensagem:
            corpo += _p(f'<i>“{e(mensagem)}”</i>')
        corpo += _botao(_txt(idioma, 'presente_botao', escapar=False, titulo=titulo), link)
        corpo += _p(_txt(idioma, 'presente_pagina'))
        return _txt(idioma, 'presente_assunto', escapar=False, de=de), corpo
    corpo = _p(f'Oi, {e(nome_quem_recebe)}!')
    corpo += _p(f'<b>{e(de)}</b> preparou uma surpresa para você: uma música feita só para você 🎁🎵')
    if mensagem:
        corpo += _p(f'<i>“{e(mensagem)}”</i>')
    corpo += _botao(f'Ouvir “{titulo}”', link)
    corpo += _p('Na página você ouve, baixa e guarda a música.')
    return f'{de} fez uma música para você 🎵', corpo


def presente_nao_entregue(nome_quem_recebe, email, link, tentativas, idioma=None):
    """Para quem comprou: o e-mail do presente não chegou em nenhuma tentativa (quase sempre caixa lotada)."""
    e = html.escape
    if not _brasil(idioma):
        corpo = _p(_txt(idioma, 'nao_entregue_texto', n=tentativas, nome=nome_quem_recebe, email=email))
        corpo += _p(_txt(idioma, 'nao_entregue_copia', nome=nome_quem_recebe))
        corpo += _botao(_txt(idioma, 'nao_entregue_botao'), link)
        corpo += _p(f'<span style="font-size:15px; color:#555;">{e(link)}</span>')
        return _txt(idioma, 'nao_entregue_assunto', escapar=False, nome=nome_quem_recebe), corpo
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


def lembrete(etapa, numero, de, para, link, link_sair, idioma=None):
    """Lembrete `numero` (1, 2 ou 3) da `etapa` (letra, previa, checkout), com o link de sair no rodapé. Brasil: os
    textos daqui (_LEMBRETES); outro idioma: os do textos.json dele ("lembretes", mesma estrutura)."""
    from musica import idiomas
    e = html.escape
    if idiomas.valido(idioma) == idiomas.IDIOMA_PADRAO:
        assunto, paragrafos, botao = _LEMBRETES[etapa][numero - 1]
        oi, oi_nome, sem_nome = 'Oi!', 'Oi, {de}!', 'quem você ama'
        rodape = 'Não quer mais estes lembretes? <a href="{link}" style="color:#888;">Clique aqui</a>.'
    else:
        L = idiomas.textos(idioma)['lembretes']
        assunto, paragrafos, botao = L[etapa][numero - 1]
        oi, oi_nome, sem_nome, rodape = L['oi'], L['oi_nome'], idiomas.texto(idioma, 'geral.sem_nome'), L['rodape']
    # {oi} = "Oi, Leo!" ou "Oi!"; {de_} = "Leo, " ou nada (sem nome, a frase começa direto, com maiúscula)
    trocas = {'oi': oi_nome.format(de=e(de)) if de else oi, 'de_': f'{e(de)}, ' if de else '', 'para': e(para or sem_nome)}
    corpo = ''.join(_p(_maiuscula(t.format(**trocas))) for t in paragrafos) + _botao(botao, link)
    corpo += (f'<p style="font-size:13px; color:#888; margin:24px 0 0; text-align:center;">'
              f'{rodape.format(link=e(link_sair))}</p>')
    return assunto.format(de=de or '', para=para or sem_nome), corpo


MARCA_SMS = 'Cancao de Presente'


def _sms_frase(numero, inicio, musica, para_mim):
    """O corpo de cada um dos 3 lembretes (1º avisa, 2º emociona, 3º último empurrão, sem urgência falsa)."""
    if numero == 1:
        return f'{_maiuscula(inicio + musica)} ficou pronta e esta guardada pra voce. Ouca de novo e finalize:'
    if numero == 2:
        final = 'pra ouvir inteira' if para_mim else 'pra emocionar quem voce ama'
        return f'{_maiuscula(inicio + musica)} continua guardada. Falta so finalizar {final}:'
    return f'{_maiuscula(inicio)}{"ainda" if inicio else "Ainda"} da tempo! {_maiuscula(musica)} esta esperando por voce. Finalize aqui:'


def lembrete_sms(de, respostas, link, marca=None, numero=1):
    """SMS que acompanha o lembrete `numero` (1, 2 ou 3) das etapas prévia e checkout (14/11/2026; o 1º texto veio do
    Bruno). A marca vem primeiro (o remetente é um número curto compartilhado com outras empresas) e o link fica
    sozinho no fim. Sem acento e com no máximo 160 caracteres (1 parte, docs/SMS.md): nomes longos são encurtados,
    nunca vira 2 SMS. "a musica da Juliana" / "do Pedro" / "de Ana, Bia e Carla" (grupo ou outra pessoa) /
    "a sua musica" (para mim)."""
    from musica.dominio import quiz, regras
    from sms.texto import LIMITE, sem_acento

    respostas = respostas or {}
    relacao = respostas.get('para_quem') or ''
    genero = next((r['genero'] for r in quiz.RELACOES if r['valor'] == relacao), 'x')
    marca = sem_acento(marca or MARCA_SMS)
    nome, para = sem_acento(de or ''), sem_acento(regras.para_quem(respostas))
    numero = numero if numero in (1, 2, 3) else 1

    def montar(nome, para):
        if relacao == quiz.PARA_MIM:
            musica = 'a sua musica'
        elif not para:
            musica = 'a musica'
        else:
            musica = f"a musica {'da' if genero == 'f' else 'do' if genero == 'm' else 'de'} {para}"
        frase = _sms_frase(numero, f'{nome}, ' if nome else '', musica, relacao == quiz.PARA_MIM)
        return f"{f'{marca}: ' if marca else ''}{frase} {link}"

    texto = montar(nome, para)
    # Não cabe: quem recebe vira só o primeiro nome (grupo "Ana, Bia e Carla" → "Ana"); depois sai o nome de quem
    # fez; depois a marca longa (nome do remetente do produto + domínio comprido); por último, corta quem recebe.
    if len(texto) > LIMITE:
        para = para.split(',')[0].split(' e ')[0].split(' ')[0].strip()
        texto = montar(nome, para)
    if len(texto) > LIMITE:
        nome = ''
        texto = montar(nome, para)
    if len(texto) > LIMITE:
        marca = ''
        texto = montar(nome, para)
    if len(texto) > LIMITE:
        para = para[:max(0, len(para) - (len(texto) - LIMITE))]
        texto = montar(nome, para)
    return texto


def presente_whatsapp_nao_chegou(nome_quem_recebe, link, idioma=None):
    """Para quem comprou: o WhatsApp do presente não chegou (número errado, sem WhatsApp, bloqueio da Meta)."""
    e = html.escape
    if not _brasil(idioma):
        corpo = _p(_txt(idioma, 'wa_nao_chegou_texto', nome=nome_quem_recebe)) + _p(_txt(idioma, 'wa_nao_chegou_texto2'))
        corpo += _botao(_txt(idioma, 'wa_nao_chegou_botao', escapar=False, nome=nome_quem_recebe), link)
        return _txt(idioma, 'wa_nao_chegou_assunto', escapar=False, nome=nome_quem_recebe), corpo
    corpo = _p(f'Não conseguimos entregar a música no WhatsApp de <b>{e(nome_quem_recebe)}</b>. Pode ser o número '
               'ou alguma configuração do WhatsApp da pessoa.')
    corpo += _p('Para a surpresa não se perder, toque no botão e mande pelo seu WhatsApp — a mensagem e o link já vão '
                'prontos:')
    corpo += _botao(f'Enviar para {nome_quem_recebe}', link)
    return f'Envie a música para {nome_quem_recebe} pelo seu WhatsApp 🎁', corpo


def presente_chegou(nome_quem_comprou, nome_quem_recebe, idioma=None):
    """Para quem comprou e não deu WhatsApp: a música chegou no WhatsApp de quem ganhou."""
    e = html.escape
    if not _brasil(idioma):
        corpo = _p(_txt(idioma, 'chegou_texto', nome=nome_quem_comprou)) + _p(_txt(idioma, 'chegou_texto2', para=nome_quem_recebe))
        return _txt(idioma, 'chegou_assunto', escapar=False, para=nome_quem_recebe), corpo
    corpo = _p(f'Pronto, {e(nome_quem_comprou)}! 🎁') + _p(f'A música chegou no WhatsApp de <b>{e(nome_quem_recebe)}</b> '
                                                             'agora há pouco. Agora é só esperar a reação ❤️')
    return f'A música chegou para {nome_quem_recebe} 🎁', corpo


def link_do_presente(nome_quem_recebe, de, link, idioma=None):
    """Texto livre (WhatsApp) quando quem ganhou toca em "Ouvir minha música"."""
    if not _brasil(idioma):
        linhas = [_txt(idioma, 'link_presente_play', escapar=False, nome=nome_quem_recebe), link]
        if de:
            linhas += ['', _txt(idioma, 'link_presente_de', escapar=False, de=de)]
        return '\n'.join(linhas)
    linhas = [f'Aperte o play, {nome_quem_recebe} 🎵', link]
    if de:
        linhas += ['', f'Com carinho, {de}.']
    return '\n'.join(linhas)




def musica_atualizada(de, para, link, video_refeito, idioma=None):
    """Para quem comprou: o admin refez a música (a pedido dela). O link da área da compra é o mesmo de sempre."""
    e = html.escape
    if not _brasil(idioma):
        corpo = _p(_txt(idioma, 'atualizada_oi', de=de) if de else _txt(idioma, 'atualizada_oi_sem_nome'))
        corpo += _p(_txt(idioma, 'atualizada_texto', para=para))
        if video_refeito:
            corpo += _p(_txt(idioma, 'atualizada_video'))
        corpo += _p(_txt(idioma, 'atualizada_links'))
        corpo += _botao(_txt(idioma, 'atualizada_botao'), link)
        return _txt(idioma, 'atualizada_assunto', escapar=False, para=para), corpo
    corpo = _p(f'Oi, {e(de)}!' if de else 'Oi!')
    corpo += _p(f'A música de <b>{e(para)}</b> foi atualizada com o que você pediu. Ela já está no mesmo lugar de '
                'sempre, pronta para ouvir e baixar 🎶')
    if video_refeito:
        corpo += _p('O videoclipe está sendo refeito com as mesmas fotos e fica pronto em alguns minutos.')
    corpo += _p('O link da página do presente e o QR code continuam os mesmos.')
    corpo += _botao('Ouvir a música atualizada', link)
    return f'A música de {para} foi atualizada 🎶', corpo


def entrega(nome_cliente, titulo, para, link, pedido_num, idioma):
    """O e-mail de entrega da compra fora do Brasil (o do Brasil é o do sistema, fluxos/entrega_pedido_email.py, igual
    ao dos e-books): o link da área da compra. Devolve (assunto, corpo); a moldura é a do produto."""
    corpo = _p(_txt(idioma, 'entrega_oi', nome=nome_cliente) if nome_cliente else _txt(idioma, 'entrega_oi_sem_nome'))
    corpo += _p(_txt(idioma, 'entrega_texto', titulo=titulo, para=para))
    corpo += _botao(_txt(idioma, 'entrega_botao'), link)
    corpo += _p(f'<span style="font-size:15px; color:#555;">{_txt(idioma, "entrega_link")}</span>')
    return _txt(idioma, 'entrega_assunto', escapar=False, pedido=pedido_num, para=para), corpo
