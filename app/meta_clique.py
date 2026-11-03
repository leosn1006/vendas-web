"""Clique de anúncio da Meta: o que a URL traz vira campanha e `fbc` no pedido, como o gclid do Google."""
import logging
import re
import time

logger = logging.getLogger(__name__)

_CAMPANHA_VALIDA = re.compile(r'[0-9]{1,30}')
_FBCLID_VALIDO = re.compile(r'[A-Za-z0-9_.-]{1,500}')


def _valido(padrao, valor) -> bool:
    return isinstance(valor, str) and padrao.fullmatch(valor) is not None


def clique_meta(params, chave_campanha: str = 'gad_campaignid') -> dict | None:
    """O clique de anúncio da Meta em `params` (query da URL ou corpo do checkout, que chama a campanha de
    `campaignid`), ou None se não for anúncio da Meta.

    Retorna {'campaignid', 'fbclid', 'fbc'}. O fbclid é opcional: sem ele, ou inválido, `fbclid` e `fbc` ficam None
    e o anúncio continua valendo. Ele nunca é alterado, porque a Meta diferencia maiúsculas de minúsculas.
    """
    if params.get('utm_source') != 'meta' or any(params.get(c) for c in ('gclid', 'wbraid', 'gbraid')):
        return None
    campaignid = params.get(chave_campanha)
    if not _valido(_CAMPANHA_VALIDA, campaignid):
        return None
    fbclid = params.get('fbclid')
    if not _valido(_FBCLID_VALIDO, fbclid):
        return {'campaignid': campaignid, 'fbclid': None, 'fbc': None}
    return {'campaignid': campaignid, 'fbclid': fbclid, 'fbc': f'fb.1.{int(time.time() * 1000)}.{fbclid}'}


def fbclid_do_fbc(fbc) -> str:
    """O fbclid gravado em `fb.1.<timestamp>.<fbclid>`. O timestamp muda a cada clique; o F5 se reconhece por aqui."""
    partes = (fbc or '').split('.', 3)
    return partes[3] if len(partes) == 4 else ''


def registrar_campanha_meta(produto_id: int, campaignid: str, venda_web: bool) -> None:
    """Cria a campanha no primeiro clique de anúncio. Uma falha aqui nunca atrapalha a visita ou o lead."""
    try:
        from database import criar_campanha_meta
        criar_campanha_meta(produto_id, campaignid, venda_web)
    except Exception as e:
        logger.error(f'[META-CLIQUE] Erro ao criar a campanha {campaignid} do produto #{produto_id}: {e}')


def ip_e_navegador(request_obj) -> tuple:
    """IP (o nginx manda em X-Real-IP) e User-Agent da cliente."""
    return (request_obj.headers.get('X-Real-IP') or request_obj.remote_addr,
            request_obj.headers.get('User-Agent'))
