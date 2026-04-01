import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_SP_TZ = timezone(timedelta(hours=-3))


def executar(data_str: str = None):
    """
    Busca todos os PIX recebidos no dia inteiro (fuso SP) e persiste no banco.
    Usa INSERT IGNORE no e2e_id para não duplicar registros entre execuções.

    Args:
        data_str: data no formato 'dd/mm/yyyy'. Se omitido, usa hoje.
    """
    import bb_pix
    import database

    if data_str:
        base = datetime.strptime(data_str, '%d/%m/%Y').replace(tzinfo=_SP_TZ)
    else:
        base = datetime.now(_SP_TZ)

    inicio = base.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    fim    = base.replace(hour=23, minute=59, second=59, microsecond=0)

    logger.info(f'[FLUXO-PIX-BB] Consultando PIX de {inicio.isoformat()} a {fim.isoformat()}')

    pix_list = bb_pix.consultar_todos_pix(inicio, fim)

    if not pix_list:
        logger.info('[FLUXO-PIX-BB] Nenhuma transação PIX no período.')
        return

    # Dict {chave_pix: produto_id} para lookup rápido
    chaves = database.busca_chaves_pix_produtos()

    novos = ignorados = 0
    for pix in pix_list:
        chave = pix.get('chave', '')
        produto_id = chaves.get(chave)
        inserido = database.salvar_pagamento_pix(pix, produto_id)
        if inserido:
            novos += 1
        else:
            ignorados += 1

    logger.info(f'[FLUXO-PIX-BB] ✅ Concluído — {novos} novo(s), {ignorados} já existia(m)')
