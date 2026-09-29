"""
Decisão e respostas prontas do atendimento por e-mail.

decidir() cruza a triagem (tipo/categoria) com o vínculo ao pedido e devolve o próximo estado e
o tipo de resposta. As respostas são textos fixos (sem IA): público 35+, texto simples, um botão
grande, a mesma assinatura por produto — e a chave PIX nunca sai de conta pessoal.

Tipos de resposta:
  estante_pago            pedido pago → link da Estante 2 (/pedido2/<guid>, com cross-sell)
  estante_nao_pago_wpp    WhatsApp, livro entregue, não pago → Estante 2 (livro + bônus bloqueado)
  pagina_vendas_nao_pago  site, não pago → página de vendas (a Estante de pedido web não pago só
                          mostra "Aguardando confirmação…", sem opção de pagar)
  chave_pix               escreveu para a chave PIX e não achamos pedido pago
  pedir_dados             não achamos o pedido → pede comprovante/e-mail/telefone/nome/CPF
  ia                      dúvida de uso com pedido vinculado → sugestão do agente do produto
"""

import html
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

import database as db
from fluxos.email_vinculo import Vinculo

CATEGORIAS_ESTANTE = {'acesso_estante', 'pagou_e_cobrado', 'chave_pix'}
CATEGORIAS_HUMANO = {'pagamento', 'reclamacao'}
CATEGORIAS_IA = {'duvida_uso', 'quer_comprar', 'outros'}

# Depois de enviada, estas respostas esperam a cliente mandar dados; as outras encerram.
TIPOS_AGUARDAM_CLIENTE = {'pedir_dados', 'chave_pix'}


def _entregue_whatsapp(pedido: dict) -> bool:
    """Mesma regra de acesso da Estante para pedido do WhatsApp (livro já entregue)."""
    from web.checkout import _produto_ja_entregue_whatsapp
    return _produto_ja_entregue_whatsapp(pedido)


@dataclass
class Decisao:
    estado: str
    resposta_tipo: str | None = None


def decidir(tipo: str, categoria: str, vinculo: Vinculo, produto: dict | None,
            escreveu_para_chave_pix: bool) -> Decisao:
    if tipo == 'ruido' or categoria in ('ruido', 'agradecimento'):
        return Decisao('sem_acao')
    if tipo == 'administrativo' or categoria in CATEGORIAS_HUMANO:
        return Decisao('a_responder')
    if not vinculo.pedido and vinculo.candidatos:
        return Decisao('a_responder')  # nome ambíguo: humano escolhe entre os candidatos

    if categoria in CATEGORIAS_ESTANTE:
        pedido = vinculo.pedido
        if not pedido:
            if categoria == 'chave_pix' or escreveu_para_chave_pix:
                return Decisao('aguardando_aprovacao', 'chave_pix')
            return Decisao('aguardando_aprovacao', 'pedir_dados')
        if vinculo.pago:
            return Decisao('aguardando_aprovacao', 'estante_pago')
        if pedido['estado_id'] < 1000:
            if _entregue_whatsapp(pedido):
                return Decisao('aguardando_aprovacao', 'estante_nao_pago_wpp')
            return Decisao('a_responder')
        if (produto or {}).get('url_pagina_vendas'):
            return Decisao('aguardando_aprovacao', 'pagina_vendas_nao_pago')
        return Decisao('a_responder')

    if categoria in CATEGORIAS_IA and vinculo.pedido and produto:
        return Decisao('aguardando_aprovacao', 'ia')
    return Decisao('a_responder')


# ─── Links ───────────────────────────────────────────────────────────────────

def _dominio(pedido: dict | None) -> str:
    """Domínio de onde a cliente veio (dns_origem), senão o de APP_BASE_URL — o mesmo critério do
    link da Estante no WhatsApp (whatsapp.montar_link_estante), sem depender do número."""
    from whatsapp import _HOSTNAME_RE, _host_da_base_url
    dominio = ((pedido or {}).get('dns_origem') or '').split(':')[0].strip().lower()
    if not _HOSTNAME_RE.match(dominio):
        dominio = _host_da_base_url(os.getenv('APP_BASE_URL', ''))
    if not _HOSTNAME_RE.match(dominio):
        raise ValueError(f"[EMAIL-RESPOSTAS] Sem domínio válido para o pedido {(pedido or {}).get('id')}")
    return dominio


def link_estante2(pedido: dict) -> str:
    return f"https://{_dominio(pedido)}/pedido2/{db.garantir_guid_pedido(pedido['id'])}"


def link_pagina_vendas(pedido: dict, produto: dict) -> str:
    url = (produto.get('url_pagina_vendas') or '').strip()
    return url if url.startswith('http') else f"https://{_dominio(pedido)}/{url.lstrip('/')}"


# ─── Textos ──────────────────────────────────────────────────────────────────

def assinatura(produto: dict | None) -> str:
    return (produto or {}).get('email_nome_remetente') or 'Equipe LBE Livros'


def primeiro_nome(*nomes: str) -> str:
    for nome in nomes:
        palavra = (nome or '').strip().split(' ')[0]
        if palavra and '@' not in palavra and not any(c.isdigit() for c in palavra):
            return palavra.capitalize()
    return ''


def _botao(link: str, texto: str, cor: str = '#2d6a1f') -> str:
    return (f'<p style="text-align:center; margin:28px 0;"><a href="{html.escape(link)}" '
            f'style="background:{cor}; color:#ffffff; text-decoration:none; font-size:20px; '
            f'font-weight:bold; padding:16px 32px; border-radius:10px; display:inline-block;">{texto}</a></p>')


def _copiar_link(link: str) -> str:
    return (f'<p style="font-size:14px; color:#666;">Se o botão não funcionar, copie e cole este link '
            f'no navegador:<br>{html.escape(link)}</p>')


_DICAS_ESTANTE = (
    '<p><strong>Duas dicas:</strong></p><ul>'
    '<li>Os livros têm muitas fotos, então podem demorar alguns segundos para abrir. É só aguardar.</li>'
    '<li>Para guardar no celular, abra o livro e toque em <strong>Baixar</strong>, '
    'no canto de cima, à direita.</li></ul>'
)

_PEDIR_DADOS = (
    '<p>Para encontrar rapidinho, responda este e-mail com <strong>uma</strong> destas informações:</p><ul>'
    '<li>a foto (print) do comprovante de pagamento;</li>'
    '<li>o e-mail ou o telefone (WhatsApp) que você usou na compra;</li>'
    '<li>o nome completo ou o CPF de quem fez o pagamento.</li></ul>'
)


# A partir daqui a resposta começa pedindo desculpas pela demora
DIAS_PARA_DESCULPAS = 3


def e_atrasada(recebido_em) -> bool:
    return bool(recebido_em) and datetime.now() - recebido_em > timedelta(days=DIAS_PARA_DESCULPAS)


def montar_resposta(resposta_tipo: str, pedido: dict | None, produto: dict | None,
                    nome_cliente: str, destinatario: str = '', atrasada: bool = False) -> str:
    """Corpo interno (HTML) da resposta — a moldura da marca é aplicada no envio."""
    nome = html.escape(nome_cliente)
    ola = f'<p>Olá{", " + nome if nome else ""}! Tudo bem?</p>'
    if atrasada:
        ola += '<p>Desculpe a demora para responder.</p>'
    fim = f'<p>Com carinho,<br>{html.escape(assinatura(produto))}</p>'
    nome_produto = html.escape((produto or {}).get('nome') or 'seu livro')
    num = f"#{pedido['id']:04d}" if pedido else ''
    cor = (produto or {}).get('email_cor_primaria') or '#2d6a1f'
    duvidas = f'<p>Ficou alguma dúvida? É só responder este e-mail informando o pedido <strong>{num}</strong>.</p>'

    if resposta_tipo == 'estante_pago':
        link = link_estante2(pedido)
        corpo = (f'<p>Encontrei o seu pedido <strong>{num}</strong> ({nome_produto}) e está tudo certo com ele. 💛</p>'
                 '<p>Seus livros ficam guardados na sua <strong>Estante</strong>. É só tocar no botão:</p>'
                 f'{_botao(link, "Abrir minha Estante", cor)}{_DICAS_ESTANTE}{_copiar_link(link)}{duvidas}')
    elif resposta_tipo == 'estante_nao_pago_wpp':
        link = link_estante2(pedido)
        corpo = (f'<p>Encontrei o seu pedido <strong>{num}</strong> ({nome_produto}). O seu livro está na sua '
                 '<strong>Estante</strong>:</p>'
                 f'{_botao(link, "Abrir minha Estante", cor)}'
                 '<p>Para liberar também os <strong>bônus</strong>, falta só confirmar o pagamento: faça o Pix '
                 'pela chave que enviamos no WhatsApp e mande o comprovante na mesma conversa. Se preferir, '
                 'responda este e-mail com a foto do comprovante.</p>'
                 f'{_DICAS_ESTANTE}{_copiar_link(link)}{duvidas}')
    elif resposta_tipo == 'pagina_vendas_nao_pago':
        link = link_pagina_vendas(pedido, produto)
        corpo = (f'<p>Encontrei o seu pedido <strong>{num}</strong> ({nome_produto}), mas o pagamento ainda '
                 'não foi concluído — por isso os livros ainda não aparecem na sua Estante.</p>'
                 '<p>Para finalizar (Pix ou cartão), é só tocar no botão:</p>'
                 f'{_botao(link, "Finalizar minha compra", cor)}'
                 '<p><strong>Já pagou?</strong> Responda este e-mail com a foto do comprovante que a gente '
                 'confere e libera seus livros.</p>'
                 f'{_copiar_link(link)}{duvidas}')
    elif resposta_tipo == 'chave_pix':
        corpo = (f'<p>Recebemos o seu e-mail em <strong>{html.escape(destinatario)}</strong>. Esse endereço é '
                 'a nossa <strong>chave Pix</strong>: ele serve para fazer o pagamento no aplicativo do seu '
                 'banco (opção <strong>Pix → Pagar com chave</strong>). Não precisa mandar e-mail para ele. 😊</p>'
                 '<p><strong>Já fez o pagamento?</strong> Mande o comprovante no WhatsApp onde você recebeu o '
                 'livro, ou responda este e-mail com a foto dele, que a gente confere e libera tudo.</p>'
                 f'{_PEDIR_DADOS}')
    elif resposta_tipo == 'pedir_dados':
        corpo = ('<p>Queremos te ajudar, mas ainda não encontramos o seu pedido com este e-mail.</p>'
                 f'{_PEDIR_DADOS}<p>Assim que encontrarmos, te mandamos o link para acessar seus livros.</p>')
    else:
        raise ValueError(f'Tipo de resposta sem modelo fixo: {resposta_tipo}')
    return f'{ola}{corpo}{fim}'
