"""O começo da compra pela Hotmart: as ofertas que a prévia mostra, o pedido nosso e o link para o checkout dela.
Ver docs/HOTMART.md → "Botão e página de obrigado".

O pedido nasce AQUI (1001, metodo 'hotmart', com o plano e a música), antes de a cliente ir para a Hotmart; o guid
vai no xcod e volta no webhook, que confirma o pagamento (hotmart/servico.py).
"""
import logging
from decimal import Decimal
from urllib.parse import urlencode

from hotmart import config

logger = logging.getLogger(__name__)

USOS_DE_LINK = ('botao', 'popup')
# Reaproveitado num novo clique: só o "criado" (1001). Nunca o 1010 (OXXO/SPEI gerado e não pago: o mesmo xcod em dois
# pagamentos) nem o 1011 (cancelado: um aviso atrasado da transação antiga o cancelaria de novo durante o pagamento
# novo) — nesses casos nasce um pedido novo; se a música acabar paga duas vezes, o webhook marca 'duplicado'.
ESTADOS_ABERTOS = (1001,)


def _db():
    from database import db
    return db


def ofertas_da_previa(produto_id: int) -> dict:
    """{'botao': {plano_id: oferta}, 'popup': oferta | None} — só as ativas, com o ID do produto Hotmart e preço."""
    linhas = _db().execute_query(
        """SELECT codigo, produto_id, plano_id, produto_hotmart, preco, moeda, uso FROM hotmart_ofertas
           WHERE produto_id = %s AND ativo = 1 AND uso IN ('botao', 'popup')
             AND produto_hotmart IS NOT NULL AND preco IS NOT NULL
           ORDER BY codigo""", (produto_id,), fetch_all=True) or []
    botao = {}
    popup = None
    for o in linhas:
        if o['uso'] == 'botao':
            botao.setdefault(o['plano_id'], o)
        elif popup is None:
            popup = o
    return {'botao': botao, 'popup': popup}


def oferta_para_link(codigo: str, produto_id: int, moeda: str | None = None) -> dict | None:
    """A oferta do clique, se ela pode ir para um link (ativa, botão/popup, deste produto, com preço e — se `moeda` —
    na moeda do país, a mesma regra da prévia)."""
    if not codigo or len(codigo) > 40:
        return None
    o = _db().execute_query(
        """SELECT codigo, produto_id, plano_id, produto_hotmart, preco, moeda, uso FROM hotmart_ofertas
           WHERE codigo = %s AND ativo = 1""", (codigo,), fetch_one=True)
    if not o or o['produto_id'] != produto_id or o['uso'] not in USOS_DE_LINK or not o['produto_hotmart']:
        return None
    if o['preco'] is None or (moeda and (o['moeda'] or '').upper() != moeda.upper()):
        return None
    return o


def link_pagamento(oferta: dict, guid: str, nome: str = '', email: str = '') -> str:
    """O checkout da Hotmart já com a oferta, o nosso guid (xcod) e os dados que ela já deu (não digita de novo)."""
    params = {'off': oferta['codigo'], 'xcod': guid}
    if nome:
        params['name'] = nome
    if email:
        params['email'] = email
    return f"{config.URL_PAGAMENTO}/{int(oferta['produto_hotmart'])}?{urlencode(params)}"


def preco_texto(valor, moeda: str) -> str:
    """'MX$ 149' / 'MX$ 49.90' (no México o decimal é ponto; centavos só quando há; a moeda vem do cadastro da
    oferta)."""
    simbolo = {'MXN': 'MX$', 'USD': 'US$', 'EUR': '€', 'BRL': 'R$'}.get((moeda or '').upper(), moeda or '')
    v = Decimal(str(valor or 0))
    numero = f'{v:.0f}' if v == v.to_integral_value() else f'{v:.2f}'
    return f'{simbolo} {numero}'


def pedido_aberto(musica_id: int, plano_id: int) -> dict | None:
    """O pedido da Hotmart desta música e deste plano que ainda não foi pago: um novo clique reaproveita, em vez de
    criar um pedido por clique."""
    return _db().execute_query(
        f"""SELECT p.id, p.guid, p.estado_id FROM pedidos p JOIN musica_pedidos mp ON mp.pedido_id = p.id
            WHERE mp.musica_id = %s AND p.plano_id = %s AND p.metodo_pagamento = 'hotmart'
              AND p.estado_id IN ({', '.join(str(e) for e in ESTADOS_ABERTOS)})
            ORDER BY p.id DESC LIMIT 1""", (musica_id, plano_id), fetch_one=True)


def criar_pedido(produto_id: int, plano: dict, valor_plano, nome: str, email: str, dns_origem: str) -> dict:
    """Pedido web novo (1001) do plano, marcado como Hotmart. O valor dos itens é só registro (o plano em reais);
    o valor_pago, em reais, vem do webhook quando ela pagar."""
    import database
    pedido_id = database.criar_pedido_web_unificado(produto_id=produto_id, phone_number_id='', contact_phone='',
                                                    contact_name=nome or '', dns_origem=dns_origem or '',
                                                    email=email or '')
    database.criar_itens_pedido_web(pedido_id, plano, valor_plano, [])
    _db().execute_query("UPDATE pedidos SET metodo_pagamento = 'hotmart' WHERE id = %s", (pedido_id,))
    return {'id': pedido_id, 'guid': database.garantir_guid_pedido(pedido_id)}


def estado_do_pedido(guid: str) -> dict | None:
    """{'estado': estado_id, 'token': o token da música do pedido} do pedido da Hotmart, ou None."""
    linha = _db().execute_query(
        """SELECT p.estado_id, m.token FROM pedidos p
           LEFT JOIN musica_pedidos mp ON mp.pedido_id = p.id LEFT JOIN musicas m ON m.id = mp.musica_id
           WHERE p.guid = %s AND p.metodo_pagamento = 'hotmart' LIMIT 1""", (guid,), fetch_one=True)
    return {'estado': linha['estado_id'], 'token': linha['token']} if linha else None
