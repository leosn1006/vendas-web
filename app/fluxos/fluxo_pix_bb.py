import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_SP_TZ = timezone(timedelta(hours=-3))


def executar(data_str: str = None, tenant_slug: str = 'lsn-livros'):
    """
    Busca todos os PIX recebidos no dia inteiro (fuso SP) e persiste no banco,
    para a conta BB (tenant_slug) informada.
    Usa INSERT IGNORE no e2e_id para não duplicar registros entre execuções.

    Args:
        data_str: data no formato 'dd/mm/yyyy'. Se omitido, usa hoje.
        tenant_slug: 'lsn-livros' (default) ou 'lbe-livros' — cada conta BB só
            retorna PIX das próprias chaves, então a origem já é conhecida
            aqui, sem precisar inferir pela chave_pix.
    """
    import bb_pix
    import database

    if data_str:
        base = datetime.strptime(data_str, '%d/%m/%Y').replace(tzinfo=_SP_TZ)
    else:
        base = datetime.now(_SP_TZ)

    inicio = base.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    fim    = base.replace(hour=23, minute=59, second=59, microsecond=0)

    logger.info(f'[FLUXO-PIX-BB][{tenant_slug}] Consultando PIX de {inicio.isoformat()} a {fim.isoformat()}')

    pix_list = bb_pix.consultar_todos_pix(inicio, fim, tenant_slug=tenant_slug)

    if not pix_list:
        logger.info(f'[FLUXO-PIX-BB][{tenant_slug}] Nenhuma transação PIX no período.')
        return

    # Dict {chave_pix: produto_id} para lookup rápido
    chaves = database.busca_chaves_pix_produtos()

    novos = ignorados = 0
    novos_ids: list[int] = []
    por_produto: dict[int | None, int] = {}
    for pix in pix_list:
        chave = pix.get('chave', '')
        produto_id = chaves.get(chave)
        pix_id = database.salvar_pagamento_pix(pix, produto_id, tenant_slug=tenant_slug)
        if pix_id:
            novos += 1
            novos_ids.append(pix_id)
            por_produto[produto_id] = por_produto.get(produto_id, 0) + 1
        else:
            ignorados += 1

    logger.info(f'[FLUXO-PIX-BB][{tenant_slug}] ✅ Concluído — {novos} novo(s), {ignorados} já existia(m)')
    for pid, qtd in sorted(por_produto.items(), key=lambda x: -(x[1])):
        label = f'produto_id={pid}' if pid else 'sem produto'
        logger.info(f'[FLUXO-PIX-BB][{tenant_slug}]   {label}: {qtd} pagamento(s)')

    # NF-e desabilitada temporariamente — reabilitar após configurar IE no banco.
    # Condição futura: só emitir NF-e para PIX vindos de tenant_slug == 'lbe-livros'
    # (única entidade com isenção fiscal hoje); PIX de 'lsn-livros' devem continuar
    # sem emissão automática. IMPORTANTE: ao reativar, resolver e passar o
    # config_id do tenant explicitamente em emitir_nfe() (via
    # database.buscar_nfe_configuracao_por_slug(tenant_slug)['id']) — sem isso a
    # task cai em buscar_nfe_configuracao_ativa() (primeira config ativo=1),
    # podendo emitir com o CNPJ errado quando lsn-livros e lbe-livros estiverem
    # ativas ao mesmo tempo.
    # if novos_ids and tenant_slug == 'lbe-livros':
    #     from celery import current_app
    #     config_id = database.buscar_nfe_configuracao_por_slug(tenant_slug)['id']
    #     for pix_id in novos_ids:
    #         current_app.send_task('tasks.emitir_nfe', args=[pix_id], kwargs={'config_id': config_id}, countdown=5)
    #     logger.info(f'[FLUXO-PIX-BB][{tenant_slug}] {len(novos_ids)} task(s) NF-e agendada(s)')
