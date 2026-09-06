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

    # Um único token pra PIX e devoluções (mesmo tenant/janela) — evita 2 OAuth por rodada.
    token = bb_pix._get_token(tenant_slug)
    pix_list = bb_pix.consultar_todos_pix(inicio, fim, tenant_slug=tenant_slug, token=token)

    # Dict {chave_pix: produto_id} — buscado uma vez, reaproveitado pro PIX e pra devolução.
    chaves = database.busca_chaves_pix_produtos()

    # Roda mesmo se não houver PIX novo hoje — devoluções são filtradas pela própria
    # data da devolução, que pode não coincidir com o dia de um PIX recebido agora.
    try:
        buscar_devolucoes(inicio, fim, tenant_slug=tenant_slug, token=token, chaves=chaves)
    except Exception as exc:
        logger.error(f'[FLUXO-PIX-BB][{tenant_slug}] ❌ Erro ao buscar devoluções: {exc}')

    if not pix_list:
        logger.info(f'[FLUXO-PIX-BB][{tenant_slug}] Nenhuma transação PIX no período.')
        return

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


def executar_periodo(inicio_str: str, fim_str: str, tenant_slug: str = 'lsn-livros'):
    """
    Roda executar() dia a dia, de inicio_str até fim_str (inclusive) — backfill de um
    período, pra não precisar rodar `make buscar-pix` um dia de cada vez. Cada dia já
    busca PIX e devoluções (mesma lógica de executar()), e é idempotente.

    Args:
        inicio_str, fim_str: datas no formato 'dd/mm/yyyy'.
    """
    inicio = datetime.strptime(inicio_str, '%d/%m/%Y').replace(tzinfo=_SP_TZ)
    fim = datetime.strptime(fim_str, '%d/%m/%Y').replace(tzinfo=_SP_TZ)
    if fim < inicio:
        raise ValueError(f'fim ({fim_str}) é anterior a inicio ({inicio_str})')

    dia = inicio
    while dia <= fim:
        data_str = dia.strftime('%d/%m/%Y')
        logger.info(f'[FLUXO-PIX-BB][{tenant_slug}] === Backfill: {data_str} ===')
        executar(data_str, tenant_slug=tenant_slug)
        dia += timedelta(days=1)

    logger.info(f'[FLUXO-PIX-BB][{tenant_slug}] ✅ Backfill concluído: {inicio_str} a {fim_str}')


def buscar_devolucoes(inicio: datetime, fim: datetime, tenant_slug: str = 'lsn-livros',
                       token: str = None, chaves: dict = None):
    """
    Busca devoluções de PIX no período (filtradas pela data da própria devolução)
    e persiste no banco. Idempotente por rtr_id — pode ser chamado várias vezes
    no mesmo dia sem duplicar (ver database.salvar_devolucao_pix).

    Args:
        token: access_token já obtido (opcional) — evita novo OAuth quando o
            caller (executar()) já tem um token válido pra esse tenant.
        chaves: dict {chave_pix: produto_id} pré-carregado (opcional) — evita
            reconsultar chaves_pix_produto por devolução; ver salvar_devolucao_pix.
    """
    import bb_pix
    import database

    devolucoes = bb_pix.consultar_devolucoes_pix(inicio, fim, tenant_slug=tenant_slug, token=token)
    if not devolucoes:
        logger.info(f'[FLUXO-PIX-BB][{tenant_slug}] Nenhuma devolução no período.')
        return

    if chaves is None:
        chaves = database.busca_chaves_pix_produtos()

    novas = atualizadas = 0
    for dev in devolucoes:
        rc = database.salvar_devolucao_pix(dev, tenant_slug=tenant_slug, chaves=chaves)
        if rc == 1:
            novas += 1
        elif rc == 2:
            atualizadas += 1

    logger.info(f'[FLUXO-PIX-BB][{tenant_slug}] ✅ devoluções: {novas} nova(s), {atualizadas} atualizada(s)')
