"""Conciliação da Hotmart: o que a API de vendas diz × o que recebemos pelo webhook. Ver docs/HOTMART.md.

De hora em hora (beat) e pelo botão do admin:
1. Busca na API as vendas do período (history + price/details + commissions), juntando pela transação.
2. Venda que o webhook nunca trouxe, ou paga na Hotmart com o nosso pedido ainda aberto (o webhook se perdeu):
   vira um aviso no formato do webhook e passa pelo MESMO servico.processar() — conferência de oferta, câmbio,
   confirmação, entrega e idempotência iguais (evento_id 'conciliacao:<transação>:<status>').
3. Grava o que a API diz (colunas api_*) e a divergência que sobrar (status, valor, líquido, xcod, sem pedido,
   paga sem pedido pago). Divergência não é corrigida sozinha: aparece na tela.
"""
import datetime
import logging
import time
from decimal import Decimal

from hotmart import api, config, repositorio, servico

logger = logging.getLogger(__name__)

# Sem transaction_status a API só devolve APPROVED e COMPLETE.
STATUS_API = ('APPROVED', 'COMPLETE', 'REFUNDED', 'PARTIALLY_REFUNDED', 'CHARGEBACK', 'PROTESTED', 'CANCELLED',
              'EXPIRED', 'PRINTED_BILLET', 'WAITING_PAYMENT')
STATUS_PAGO = {'APPROVED', 'COMPLETE'}
EVENTO_DO_STATUS = {
    'APPROVED': 'PURCHASE_APPROVED', 'COMPLETE': 'PURCHASE_COMPLETE', 'REFUNDED': 'PURCHASE_REFUNDED',
    'PARTIALLY_REFUNDED': 'PURCHASE_REFUNDED', 'CHARGEBACK': 'PURCHASE_CHARGEBACK', 'PROTESTED': 'PURCHASE_PROTEST',
    'CANCELLED': 'PURCHASE_CANCELED', 'EXPIRED': 'PURCHASE_EXPIRED', 'PRINTED_BILLET': 'PURCHASE_BILLET_PRINTED',
    'WAITING_PAYMENT': 'PURCHASE_BILLET_PRINTED',
}
_PEDIDO_PAGO = (0, 1000)


def _d(obj, *caminho):
    for chave in caminho:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(chave)
    return obj


def _dec(valor) -> Decimal | None:
    try:
        return Decimal(str(valor)) if valor is not None else None
    except Exception:
        return None


def _de_ms(ms) -> datetime.datetime | None:
    from hotmart.leitura import _de_milissegundos
    return _de_milissegundos(ms)


# ── busca na API ───────────────────────────────────────────────────────────────────────────────────────────────────

def buscar_vendas(inicio_ms: int, fim_ms: int) -> dict[str, dict]:
    """{transação: {'history': item, 'price': item|None, 'commissions': item|None}} do período, todos os status."""
    vendas: dict[str, dict] = {}
    for caminho, chave in (('sales/history', 'history'), ('sales/price/details', 'price'),
                           ('sales/commissions', 'commissions')):
        for status in STATUS_API:
            for item in api.listar(caminho, start_date=inicio_ms, end_date=fim_ms, transaction_status=status):
                transacao = _d(item, 'purchase', 'transaction') or item.get('transaction')
                if not transacao:
                    continue
                if chave == 'history' or transacao in vendas:
                    vendas.setdefault(transacao, {'history': None, 'price': None, 'commissions': None})[chave] = item
    return {t: v for t, v in vendas.items() if v['history']}


def resumo_api(venda: dict) -> dict:
    """O que a API diz da venda, nas colunas api_* de pagamento_hotmart."""
    h, p, c = venda['history'], venda.get('price') or {}, venda.get('commissions') or {}
    compra = h.get('purchase') or {}
    nosso = next((x for x in c.get('commissions') or [] if (x.get('source') or '').upper() == 'PRODUCER'), {})
    taxa = compra.get('hotmart_fee') or {}
    total = p.get('total') or compra.get('price') or {}
    return {
        'api_status': (compra.get('status') or '').upper() or None,
        'api_total': _dec(total.get('value')), 'api_moeda': total.get('currency_code'),
        'api_iva': _dec(_d(p, 'vat', 'value')), 'api_moeda_iva': _d(p, 'vat', 'currency_code'),
        'api_taxa': _dec(taxa.get('total')), 'api_moeda_taxa': taxa.get('currency_code'),
        'api_taxa_percentual': _dec(taxa.get('percentage')), 'api_taxa_fixa': _dec(taxa.get('fixed')),
        'api_liquido': _dec(_d(nosso, 'commission', 'value')),
        'api_moeda_liquido': _d(nosso, 'commission', 'currency_code'),
        'api_garantia_ate': _de_ms(compra.get('warranty_expire_date')),
        'api_xcod': (_d(compra, 'tracking', 'external_code') or '').strip()[:64] or None,
        'api_oferta': (_d(compra, 'offer', 'code') or '')[:40] or None,
    } | _moedas_curtas(total, p, taxa, nosso, compra)


def _moedas_curtas(total, p, taxa, nosso, compra) -> dict:
    """Moedas (CHAR(3)) e status (VARCHAR(30)) cortados no tamanho das colunas: um valor fora do esperado vindo da
    API nunca derruba o UPDATE (o MySQL em modo estrito recusa)."""
    corta = lambda v, n: (str(v)[:n] or None) if v else None   # noqa: E731
    return {'api_status': corta((compra.get('status') or '').upper(), 30),
            'api_moeda': corta(total.get('currency_code'), 3), 'api_moeda_iva': corta(_d(p, 'vat', 'currency_code'), 3),
            'api_moeda_taxa': corta(taxa.get('currency_code'), 3),
            'api_moeda_liquido': corta(_d(nosso, 'commission', 'currency_code'), 3)}


def aviso_da_api(venda: dict, status: str, so_registro: bool = False, bump_de: str | None = None) -> dict:
    """A venda da API no formato do webhook 2.0 (o que leitura.ler() entende). Preço sem IVA = price/details.base;
    sem o price/details, cai no preço do history (com IVA) — melhor um valor um pouco maior que nenhum."""
    h, p, c = venda['history'], venda.get('price') or {}, venda.get('commissions') or {}
    compra = h.get('purchase') or {}
    base = p.get('base') or compra.get('price') or {}
    total = p.get('total') or compra.get('price') or {}
    garantia = _de_ms(compra.get('warranty_expire_date'))
    comissoes = [{'value': _d(x, 'commission', 'value'), 'currency_value': _d(x, 'commission', 'currency_code'),
                  'source': x.get('source')} for x in c.get('commissions') or []]
    transacao = compra.get('transaction')
    return {
        'id': f"conciliacao:{transacao}:{status}{':registro' if so_registro else ''}",
        'event': servico.EVENTO_SO_REGISTRO if so_registro else EVENTO_DO_STATUS[status], 'version': '2.0.0',
        'creation_date': int(time.time() * 1000),
        'data': {
            'product': {'id': _d(h, 'product', 'id'), 'name': _d(h, 'product', 'name'),
                        'warranty_date': garantia.isoformat() if garantia else None},
            'buyer': {'email': _d(h, 'buyer', 'email'), 'name': _d(h, 'buyer', 'name')},
            'commissions': comissoes,
            'purchase': {
                'transaction': transacao, 'status': status, 'approved_date': compra.get('approved_date'),
                'price': {'value': base.get('value'), 'currency_value': base.get('currency_code')},
                'full_price': {'value': total.get('value'), 'currency_value': total.get('currency_code')},
                'offer': {'code': _d(compra, 'offer', 'code')},
                'origin': {'xcod': _d(compra, 'tracking', 'external_code')},
                'payment': {'type': _d(compra, 'payment', 'type')},
                # bump_de = a transação principal (a conciliação deduz o bump; ver _contexto_do_lote)
                'order_bump': {'is_order_bump': bool(bump_de), 'parent_purchase_transaction': bump_de},
            },
        },
    }


# ── comparação ─────────────────────────────────────────────────────────────────────────────────────────────────────

def divergencias(api_: dict, gravado: dict | None) -> list[str]:
    """O que não bate entre a API e o que temos (pagamento_hotmart + pedido)."""
    if not gravado:
        return ['venda não registrada pelo webhook']
    achados = []
    if not gravado.get('pedido_id'):
        achados.append(f"sem pedido nosso (xcod={api_['api_xcod']!r})")
    else:
        if api_['api_status'] in STATUS_PAGO and gravado.get('pedido_estado') not in _PEDIDO_PAGO:
            achados.append(f"paga na Hotmart, pedido #{gravado['pedido_id']} não pago (estado {gravado.get('pedido_estado')})")
        if api_['api_xcod'] and gravado.get('pedido_guid') and api_['api_xcod'] != gravado['pedido_guid']:
            achados.append(f"xcod {api_['api_xcod']} ≠ guid do pedido {gravado['pedido_guid']}")
    if api_['api_status'] and gravado.get('status') and api_['api_status'] != gravado['status']:
        achados.append(f"status: API {api_['api_status']} × webhook {gravado['status']}")
    if (api_['api_total'] is not None and gravado.get('valor_cheio') is not None
            and api_['api_moeda'] == gravado.get('moeda')
            and abs(api_['api_total'] - Decimal(str(gravado['valor_cheio']))) > Decimal('0.01')):
        achados.append(f"valor: API {api_['api_total']} × webhook {gravado['valor_cheio']} {api_['api_moeda']}")
    if (api_['api_liquido'] is not None and gravado.get('liquido') is not None
            and api_['api_moeda_liquido'] == gravado.get('moeda_liquido')
            and abs(api_['api_liquido'] - Decimal(str(gravado['liquido']))) > Decimal('0.01')):
        achados.append(f"líquido: API {api_['api_liquido']} × webhook {gravado['liquido']} {api_['api_moeda_liquido']}")
    return achados


# ── execução ───────────────────────────────────────────────────────────────────────────────────────────────────────

def conciliar(origem: str = 'beat', dias: int | None = None) -> dict:
    """Concilia os últimos `dias` (padrão HOTMART_DIAS_CONCILIACAO). Nunca levanta exceção: o erro fica gravado na
    execução (hotmart_conciliacoes) e no resumo devolvido."""
    dias = dias or config.DIAS_CONCILIACAO
    agora = datetime.datetime.now()
    de = agora - datetime.timedelta(days=dias)
    resumo = {'vendas_api': 0, 'novas': 0, 'confirmadas': 0, 'divergentes': 0, 'reentregas': 0, 'erro': None}
    if not api.configurada():
        resumo['erro'] = 'API da Hotmart não configurada (HOTMART_CLIENT_ID/_SECRET/_TOKEN)'
        return resumo
    if not _pegar_trava():
        resumo['erro'] = 'outra conciliação já está rodando'
        logger.warning(f'[HOTMART-CONCILIACAO] {origem}: {resumo["erro"]} — não iniciada')
        return resumo
    try:
        execucao_id = repositorio.iniciar_conciliacao(origem, de, agora)
        try:
            vendas = buscar_vendas(int(de.timestamp() * 1000), int(agora.timestamp() * 1000))
            resumo['vendas_api'] = len(vendas)
            contexto = _contexto_do_lote(vendas)
            # Ofertas cadastradas primeiro: num pedido com order bump, a compra principal é aplicada antes do bump.
            for transacao in sorted(vendas, key=lambda t: not contexto['oferta_ok'][t]):
                try:   # uma venda com problema nunca impede as outras (nem trava as próximas execuções)
                    _conciliar_venda(transacao, vendas[transacao], resumo, contexto)
                except Exception as e:
                    resumo['divergentes'] += 1
                    logger.error(f'[HOTMART-CONCILIACAO] ❌ {transacao}: {type(e).__name__}: {e}')
        except Exception as e:
            resumo['erro'] = f'{type(e).__name__}: {e}'
            logger.error(f'[HOTMART-CONCILIACAO] ❌ {resumo["erro"]}')
        repositorio.finalizar_conciliacao(execucao_id, resumo['vendas_api'], resumo['novas'], resumo['confirmadas'],
                                          resumo['divergentes'], resumo['reentregas'], resumo['erro'])
    finally:
        _soltar_trava()
    logger.info(f'[HOTMART-CONCILIACAO] {origem}: {resumo}')
    return resumo


_TRAVA = 'hotmart:conciliacao:rodando'


def _pegar_trava() -> bool:
    """Uma conciliação por vez (o beat e o botão caem no mesmo worker): duas ao mesmo tempo poderiam reagendar a
    mesma entrega. Vence sozinha em 30 min (processo morto no meio). Sem Redis, segue (melhor conciliar)."""
    try:
        from redis_cliente import cliente
        return bool(cliente().set(_TRAVA, '1', nx=True, ex=1800))
    except Exception as e:
        logger.warning(f'[HOTMART-CONCILIACAO] ⚠️ Sem a trava do Redis ({type(e).__name__}): seguindo')
        return True


def _soltar_trava() -> None:
    try:
        from redis_cliente import cliente
        cliente().delete(_TRAVA)
    except Exception:
        pass


def _contexto_do_lote(vendas: dict) -> dict:
    """Para cada transação: a oferta está cadastrada? é a mais recente do mesmo xcod (pedido)? tem outra do mesmo
    pedido com oferta cadastrada (então esta, de oferta desconhecida, é um order bump)?"""
    oferta_ok, por_xcod = {}, {}
    for t, venda in vendas.items():
        api_ = resumo_api(venda)
        oferta_ok[t] = bool(api_['api_oferta'] and repositorio.oferta(api_['api_oferta']))
        if api_['api_xcod']:
            compra = venda['history'].get('purchase') or {}
            por_xcod.setdefault(api_['api_xcod'], []).append((compra.get('order_date') or 0, t))
    mais_recente = {max(lista)[1] for lista in por_xcod.values()}
    # transação de oferta desconhecida → a irmã (mesmo pedido) de oferta cadastrada, que é a compra principal
    mae_do_bump = {t: next(o for _, o in lista if o != t and oferta_ok[o])
                   for lista in por_xcod.values() for _, t in lista
                   if not oferta_ok[t] and any(oferta_ok[o] for _, o in lista if o != t)}
    return {'oferta_ok': oferta_ok, 'mais_recente': mais_recente, 'mae_do_bump': mae_do_bump}


def _conciliar_venda(transacao: str, venda: dict, resumo: dict, contexto: dict) -> None:
    api_ = resumo_api(venda)
    status = api_['api_status']
    gravado = repositorio.pagamento_com_pedido(transacao)
    nao_veio = gravado is None
    if nao_veio:      # o estado do pedido antes de aplicar, pelo xcod (para contar só o que esta venda pagou)
        pedido = repositorio.pedido_por_guid(api_['api_xcod']) if api_['api_xcod'] else None
        pago_antes = bool(pedido and pedido.get('estado_id') in _PEDIDO_PAGO)
    else:
        pago_antes = gravado.get('pedido_estado') in _PEDIDO_PAGO
    mae = contexto['mae_do_bump'].get(transacao)
    provavel_bump = mae is not None

    # Webhook perdido de venda PAGA: aplica pelo mesmo caminho do webhook (confirma e entrega). Nunca num order bump,
    # nem quando o aviso do webhook desta venda já está em "Para conferir" (não cria um segundo aviso igual).
    pagar = (status in STATUS_PAGO and not pago_antes and not provavel_bump
             and not (gravado and (gravado.get('order_bump') or repositorio.tem_aviso_a_conferir(transacao))))
    if nao_veio or pagar:
        # Status que não paga só muda o pedido se for a transação mais recente dele (um cartão recusado antigo não
        # cancela o pedido que está esperando o OXXO); bump e o resto: só registra a compra.
        so_registro = not pagar and not provavel_bump and (status not in EVENTO_DO_STATUS
                                                           or transacao not in contexto['mais_recente'])
        try:   # o bump vai como bump (o webhook grava order_bump = 1 e o ignora)
            resultado = servico.processar(aviso_da_api(venda, status if status in EVENTO_DO_STATUS else 'APPROVED',
                                                       so_registro=so_registro, bump_de=mae))
            logger.info(f'[HOTMART-CONCILIACAO] {transacao} ({status}) aplicada pela API: {resultado}')
            resumo['novas'] += int(nao_veio)
        except Exception as e:
            logger.error(f'[HOTMART-CONCILIACAO] ❌ {transacao}: {type(e).__name__}: {e}')
        gravado = repositorio.pagamento_com_pedido(transacao)
        if not pago_antes and gravado and gravado.get('pedido_estado') in _PEDIDO_PAGO:
            resumo['confirmadas'] += 1
            logger.warning(f'[HOTMART-CONCILIACAO] ⚠️ Pedido #{gravado["pedido_id"]} pago pela conciliação '
                           f'({transacao}) — o webhook não tinha confirmado')

    _reagendar_entrega_perdida(gravado, status, resumo)

    if gravado is None:     # nem o processamento conseguiu gravar
        resumo['divergentes'] += 1
        return
    achados = divergencias(api_, gravado)
    repositorio.salvar_conciliacao(transacao, api_, '; '.join(achados) if achados else None)
    resumo['divergentes'] += int(bool(achados))


def _reagendar_entrega_perdida(gravado: dict | None, status: str | None, resumo: dict) -> None:
    """Pedido pago pela Hotmart (venda paga na API) sem entrega entre 30 min e 6 h depois do pagamento (ex.: o
    agendamento falhou depois da confirmação): agenda de novo. A entrega é idempotente (data_envio_ebook) e a janela
    limita a ~6 tentativas; sem e-mail não há o que entregar."""
    if not gravado or status not in STATUS_PAGO or gravado.get('pedido_estado') not in _PEDIDO_PAGO:
        return
    if gravado.get('pedido_metodo') != 'hotmart' or not gravado.get('pedido_email') or gravado.get('pedido_entregue_em'):
        return
    pago_em = gravado.get('pedido_pago_em')
    agora = datetime.datetime.now()
    if not pago_em or not (agora - datetime.timedelta(hours=6) <= pago_em <= agora - datetime.timedelta(minutes=30)):
        return
    servico.enfileirar_entrega(gravado['pedido_id'])
    resumo['reentregas'] += 1
    logger.warning(f'[HOTMART-CONCILIACAO] ⚠️ Pedido #{gravado["pedido_id"]} pago sem entrega — entrega agendada de novo')
