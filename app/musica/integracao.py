"""O que o resto do sistema (checkout, tasks, e-mail de entrega, Estante 2) usa da Música.
Fachada fina sobre os casos de uso: quem está fora do módulo não conhece portas nem adaptadores."""

from musica import casos_de_uso
from musica.casos_de_uso import Recusa
from musica.dominio import regras
from musica.dominio.recursos import plano_vende_musica
from musica.fabrica import servicos

__all__ = ['Recusa', 'plano_vende_musica', 'conferir_para_checkout', 'vincular_ao_pedido', 'liberar_do_pedido',
           'musica_do_pedido_pago', 'email_de_entrega', 'presente_devolvido', 'token_do_pedido', 'dados_para_checkout',
           'webhook_whatsapp']


def conferir_para_checkout(token: str, produto_id: int) -> None:
    """Recusa (com a mensagem para a tela) se a música do link não pode ser comprada neste produto. O nosso
    checkout (/pay, em reais) só vende música do Brasil: a de outro idioma é vendida pela Hotmart (um link montado à
    mão não pode cobrar em reais quem está no México)."""
    musica = casos_de_uso.musica_para_checkout(servicos(), token, produto_id)
    from musica import idiomas
    if idiomas.valido(musica.get('idioma')) != idiomas.IDIOMA_PADRAO:
        raise Recusa('Esta música não é vendida neste checkout. Volte para a página da prévia.')


def caminho_da_previa(token: str) -> str:
    """/<prefixo do idioma da música>/p/<token> (Brasil: /musica/p/...; México: /mx/cancion/p/...)."""
    from musica import idiomas
    try:
        musica = servicos().repositorio.por_token(token)
    except Exception:   # é o caminho de erro do checkout: nunca vira 500 (cai no do Brasil, como antes)
        musica = None
    return f"{idiomas.cfg((musica or {}).get('idioma'))['prefixo']}/p/{token}"


def vincular_ao_pedido(token: str, pedido_id: int, produto_id: int, whatsapp: str | None = None, ddi: str = '55') -> None:
    casos_de_uso.vincular_ao_pedido(servicos(), token, pedido_id, produto_id, whatsapp, ddi)


def liberar_do_pedido(pedido_id: int) -> bool:
    return casos_de_uso.liberar_do_pedido(servicos(), pedido_id)


def musica_do_pedido_pago(pedido: dict, exigir_liberada: bool = True) -> dict | None:
    """Para o e-mail de entrega e a Estante 2: {titulo, para, caminho} da música liberada por este pedido
    (caminho relativo da área da compra; quem chama põe o endereço do site na frente, se precisar).
    `exigir_liberada=False` (e-mail de entrega, que só sai uma vez): devolve a música do pedido mesmo que a
    liberação ainda não tenha rodado — a área da compra libera na hora ou mostra "sendo liberada"."""
    s = servicos()
    musica = s.repositorio.do_pedido(pedido['id'])
    if not musica or (exigir_liberada and not musica['liberada_em']):
        return None
    from musica import idiomas
    from musica.dominio.regras import para_quem
    idioma = idiomas.valido(musica.get('idioma'))
    if idioma == idiomas.IDIOMA_PADRAO:
        return {'titulo': musica['titulo'] or 'Sua música', 'para': para_quem(musica['respostas']),
                'caminho': f"/musica/compra/{pedido['guid']}", 'idioma': idioma}
    # Fora do Brasil: o caminho no prefixo do idioma e os textos dele (o e-mail de entrega é o de email_de_entrega)
    return {'titulo': musica['titulo'] or idiomas.texto(idioma, 'emails.sua_musica'),
            'para': para_quem(musica['respostas'], idiomas.texto(idioma, 'geral.sem_nome')),
            'caminho': f"{idiomas.cfg(idioma)['prefixo']}/compra/{pedido['guid']}", 'idioma': idioma}


def email_de_entrega(pedido: dict, musica: dict, link: str, pedido_num: str, nome_remetente: str, cor_primaria: str,
                     cor_secundaria: str) -> tuple[str, str]:
    """O e-mail de entrega de uma música de FORA do Brasil (assunto, HTML completo), no idioma dela, com a moldura
    do produto. `musica` = o de musica_do_pedido_pago. O do Brasil continua o do sistema (entrega_pedido_email)."""
    import html
    from fluxos._email_gmail import wrapper_html
    from musica import idiomas, mensagens
    idioma = musica['idioma']
    nome = (pedido.get('contact_name') or '').split()[0] if (pedido.get('contact_name') or '').strip() else ''
    assunto, corpo = mensagens.entrega(nome, musica['titulo'], musica['para'], link, pedido_num, idioma)
    pagina = wrapper_html(titulo_header=html.escape(nome_remetente), corpo_interno_html=corpo,
                          nome_remetente=nome_remetente, cor_primaria=cor_primaria, cor_secundaria=cor_secundaria,
                          rodape=idiomas.texto(idioma, 'email.rodape', marca=html.escape(nome_remetente)),
                          lang=idiomas.cfg(idioma)['html_lang'])
    return assunto, pagina


def presente_devolvido(thread_id: str, recusados: list[str]) -> bool:
    """Para a leitura da caixa do admin@: uma devolução (mailer-daemon) que é de um presente da Música.
    `recusados` = endereços que a devolução diz que recusaram (vazio se ela não disser)."""
    return casos_de_uso.presente_devolvido(servicos(), thread_id, recusados)


def token_do_pedido(pedido_id: int) -> str | None:
    """A música já gravada neste pedido. Só para contextos em que o pedido é comprovadamente da cliente (cookie do
    próprio navegador, e-mail enviado a ela): o token dá acesso à música — nunca a partir de um id vindo da requisição."""
    musica = servicos().repositorio.do_pedido(pedido_id)
    return musica['token'] if musica else None


def checkout_aberto(token: str) -> None:
    """O checkout desta música abriu: conta para os lembretes (etapa checkout)."""
    casos_de_uso.checkout_aberto(servicos(), token)


def dados_para_checkout(token: str) -> dict:
    """O e-mail e o WhatsApp do quiz, para o checkout já abrir preenchido (quem tem o token é quem fez o quiz;
    o JS do checkout tira o 55 e põe a máscara). O nome não: o quiz pede só o primeiro nome, e o checkout precisa
    do nome completo de quem paga."""
    musica = servicos().repositorio.por_token(token)
    return {'email': musica['email'] or '', 'whatsapp': regras.celular_br(musica.get('whatsapp'))} if musica else {}


def webhook_whatsapp(valor: dict) -> None:
    """Para o orquestrador: o `value` de um webhook da Meta vindo do número só de avisos da Música (status de
    entrega, toque no botão, mensagens — que são ignoradas)."""
    casos_de_uso.webhook_whatsapp(servicos(), valor)
