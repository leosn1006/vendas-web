"""As regras do webhook da Hotmart: o aviso → a compra gravada → o que muda no pedido. Ver docs/HOTMART.md.

O pedido é o nosso (xcod = guid). Pago → o mesmo 1000 do PIX/cartão, com valor_pago, valor_liquido_pagamento e
data_repasse em REAIS, e a mesma tarefa de entrega (libera a Música/apps e manda o e-mail). Tudo o que é da Hotmart
(moeda original, comissão, situação, previsão de repasse) fica em pagamento_hotmart.
"""
import datetime
import hashlib
import json
import logging

from hotmart import cambio, config, leitura, repositorio

logger = logging.getLogger(__name__)

EVENTOS_PAGO = {'PURCHASE_APPROVED', 'PURCHASE_COMPLETE'}
EVENTOS_CANCELADO = {'PURCHASE_CANCELED', 'PURCHASE_EXPIRED'}
EVENTOS_DEVOLUCAO = {'PURCHASE_REFUNDED', 'PURCHASE_CHARGEBACK', 'PURCHASE_PROTEST'}
# OXXO/SPEI (e boleto) gerado e ainda não pago. Também pelo status, seja qual for o evento que a Hotmart usar.
EVENTOS_AGUARDANDO = {'PURCHASE_BILLET_PRINTED'}
STATUS_AGUARDANDO = {'WAITING_PAYMENT', 'PRINTED_BILLET'}
# Usado só pela conciliação: grava a compra (pagamento_hotmart) sem mudar o estado do pedido — ex.: um cartão recusado
# antigo que o webhook não trouxe não pode cancelar o pedido que hoje está esperando o OXXO.
EVENTO_SO_REGISTRO = 'CONCILIACAO_REGISTRO'


def _ptax(moeda):
    """Cotação de referência em reais (PTAX do BCB ou, para MXN/INR, a referência do BCE)."""
    from cotacao import cotacao_em_reais
    return cotacao_em_reais(moeda, timeout=3)   # dentro da requisição da Hotmart: não segurar o worker


def enfileirar_entrega(pedido_id: int) -> None:
    import celery_app  # noqa: F401 — configura o broker (Redis) também fora do app/worker (ex.: conciliação num script)
    import tasks
    tasks.enviar_email_entrega.delay(pedido_id)


def previsao_repasse(aprovado_em: datetime.datetime | None, garantia_ate: datetime.datetime | None
                     ) -> datetime.date | None:
    """Estimativa (o webhook não traz a data do saque): aprovação + HOTMART_DIAS_REPASSE, ou o fim da garantia, se
    for mais tarde."""
    if not aprovado_em:
        return None
    previsao = (aprovado_em + datetime.timedelta(days=config.DIAS_REPASSE)).date()
    if garantia_ate and garantia_ate.date() > previsao:
        previsao = garantia_ate.date()
    return previsao


def _oferta_confere(dados: dict, pedido: dict) -> tuple[bool, str]:
    """A oferta paga tem que ser do plano do pedido: senão alguém paga a oferta barata com o xcod do pedido caro."""
    oferta = repositorio.oferta(dados['oferta'])
    if not oferta:
        return False, f"oferta {dados['oferta']!r} não cadastrada em hotmart_ofertas"
    if oferta['produto_id'] != pedido.get('produto_id'):
        return False, f"oferta {dados['oferta']} é do produto {oferta['produto_id']}, pedido é do {pedido.get('produto_id')}"
    # Pedido sem plano não passa: todo pedido da Hotmart nasce com plano, e aceitar "qualquer oferta do produto"
    # deixaria pagar a oferta barata com o xcod de um pedido antigo. (O 'ativo' da oferta só vale para montar links:
    # quem já pagou uma oferta desativada recebe.)
    if oferta['plano_id'] != pedido.get('plano_id'):
        return False, f"oferta {dados['oferta']} é do plano {oferta['plano_id']}, pedido é do {pedido.get('plano_id')}"
    return True, ''


def processar(payload: dict) -> str:
    """Aplica um aviso. Devolve o resultado (gravado em pagamento_hotmart_eventos). Exceção = erro inesperado: a rota
    responde 500, a Hotmart reenvia e o aviso é processado de novo (nada aqui repete efeito)."""
    dados = leitura.ler(payload)
    # Sem o id do aviso (não deveria acontecer): o próprio conteúdo vira a chave, para avisos diferentes nunca
    # caírem na mesma chave e um repetido idêntico continuar sendo reconhecido.
    evento_id = dados['evento_id'] or 'sem-id:' + hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:40]
    if not repositorio.registrar_evento(evento_id, dados['transacao'], dados['evento'], payload):
        logger.info(f'[HOTMART] Aviso {evento_id} repetido — já processado')
        return 'repetido'
    try:
        resultado, detalhe = _aplicar(dados)
    except Exception as e:
        repositorio.marcar_resultado_evento(evento_id, 'erro', f'{type(e).__name__}: {e}')
        raise
    repositorio.marcar_resultado_evento(evento_id, resultado, detalhe)
    return resultado


def reprocessar(evento_db_id: int) -> str:
    """Aplica de novo um aviso gravado (ex.: oferta cadastrada depois de um 'oferta_divergente'). Usado pelo botão
    "Reprocessar" do admin; o resultado novo substitui o antigo."""
    evento = repositorio.evento_por_id(evento_db_id)
    if not evento:
        raise ValueError(f'aviso {evento_db_id} não existe')
    payload = evento['payload']
    payload = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    if not repositorio.liberar_para_reprocessar(evento['evento_id']):
        raise ValueError(f"o aviso não está para conferir (resultado: {evento.get('resultado')})")
    return processar(payload)


def _aplicar(dados: dict) -> tuple[str, str]:
    evento, transacao = dados['evento'], dados['transacao']
    if not transacao:
        return 'ignorado', f'{evento} sem transação (não é de compra)'

    pedido = repositorio.pedido_por_guid(dados['xcod']) if dados['xcod'] else None
    pago = evento in EVENTOS_PAGO
    # Aviso sem approved_date (ex.: alguns COMPLETE): vale a data já gravada da transação; "agora" só na 1ª vez. Trocar
    # a data gravada pelo agora faria a compra original parecer mais nova que uma duplicada (outra_compra_paga).
    aprovado_em = dados['aprovado_em'] or repositorio.aprovado_gravado(transacao) or (
        datetime.datetime.now() if pago else None)

    taxa, fonte = cambio.taxa_para_brl(dados['moeda'], dados['liquido'], dados['moeda_liquido'], dados['conversao'],
                                       _ptax, repositorio.ultima_taxa)
    valor_brl = cambio.em_reais(dados['valor'], taxa)
    liquido_brl = cambio.liquido_em_reais(dados['liquido'], dados['moeda_liquido'], dados['moeda'], taxa,
                                          dados['conversao'], _ptax)
    previsao = previsao_repasse(aprovado_em, dados['garantia_ate'])
    fonte_anterior = repositorio.fonte_taxa_gravada(transacao)

    repositorio.salvar_pagamento({
        **dados, 'pedido_id': pedido['id'] if pedido else None, 'ultimo_evento': evento,
        'email_comprador': dados['email'], 'taxa_brl': taxa, 'fonte_taxa': fonte, 'valor_brl': valor_brl,
        'liquido_brl': liquido_brl, 'order_bump': int(dados['order_bump']),
        'aprovado_em': aprovado_em if pago else dados['aprovado_em'], 'previsao_repasse': previsao if pago else None,
    })

    if dados['order_bump']:
        logger.warning(f'[HOTMART] ⚠️ Order bump {transacao} (principal {dados["transacao_principal"]}) — '
                       f'não tratado na 1ª versão')
        return 'ignorado', 'order bump'
    if not pedido:
        logger.error(f'[HOTMART] ❌ {evento} {transacao}: sem pedido (xcod={dados["xcod"]!r}) — conferir à mão')
        return 'sem_pedido', f'xcod={dados["xcod"]!r}'

    pedido_id = pedido['id']
    if evento == EVENTO_SO_REGISTRO:
        return 'ok', f"só registro pela conciliação ({dados['status']})"
    if pago:
        confere, motivo = _oferta_confere(dados, pedido)
        if not confere:
            logger.error(f'[HOTMART] ❌ {transacao} NÃO confirmou o pedido #{pedido_id}: {motivo}')
            return 'oferta_divergente', motivo
        if evento == 'PURCHASE_COMPLETE':
            repositorio.marcar_liberado(transacao)
        if fonte == 'pendente':
            # Sem cotação: confirma (a entrega nunca espera o câmbio) mantendo o valor esperado do pedido em vez de
            # zerar; o próximo aviso com cotação (ex.: o PURCHASE_COMPLETE) corrige.
            logger.error(f'[HOTMART] ❌ Pedido #{pedido_id} confirmado com valor em reais pendente (sem cotação)')
            valor_brl = valor_brl if valor_brl is not None else pedido.get('valor_pago')
        repositorio.preencher_email_se_vazio(pedido_id, dados['email'])
        if repositorio.confirmar_pedido(pedido_id, valor_brl, dados['nome'], liquido_brl, previsao):
            logger.info(f'[HOTMART] ✅ Pedido #{pedido_id} pago ({dados["valor"]} {dados["moeda"]} = '
                        f'R$ {valor_brl}, {fonte}) — entrega enfileirada')
            enfileirar_entrega(pedido_id)
            outro = repositorio.outro_pedido_pago_da_musica(pedido_id)
            if outro:
                logger.error(f'[HOTMART] ❌ A música do pedido #{pedido_id} já foi paga no pedido #{outro}: '
                             f'reembolsar um ({transacao})')
                return 'duplicado', f'a música já foi paga no pedido #{outro} — reembolsar um'
            return 'ok', ''
        if fonte_anterior == 'pendente' and fonte != 'pendente':
            if repositorio.corrigir_valor_pendente(pedido_id, valor_brl, liquido_brl):
                logger.info(f'[HOTMART] ✅ Pedido #{pedido_id}: valor em reais corrigido para R$ {valor_brl} ({fonte})')
        if outra := repositorio.outra_compra_paga(pedido_id, transacao, aprovado_em):
            logger.error(f'[HOTMART] ❌ Pedido #{pedido_id} pago DUAS vezes ({outra} e {transacao}): reembolsar a '
                         f'{transacao} na Hotmart')
            return 'duplicado', f'pagamento duplicado: o pedido já foi pago pela {outra} — reembolsar a {transacao}'
        return 'ok', ''

    # Aguardando/cancelado só mexem no pedido se a oferta for do mesmo produto (o xcod de um pedido de outro fluxo
    # nunca o tira do lugar) e se ele ainda estiver nos estados web antes do pagamento (ver repositorio).
    produto_confere = (repositorio.oferta(dados['oferta']) or {}).get('produto_id') == pedido.get('produto_id')
    if evento in EVENTOS_AGUARDANDO or dados['status'] in STATUS_AGUARDANDO:
        if not produto_confere:
            return 'oferta_divergente', f"oferta {dados['oferta']!r} não é do produto do pedido"
        repositorio.mudar_estado_se_nao_pago(pedido_id, repositorio.ESTADO_AGUARDANDO)
        return 'ok', f'aguardando pagamento ({dados["tipo_pagamento"]})'
    if evento in EVENTOS_CANCELADO:
        if not produto_confere:
            return 'oferta_divergente', f"oferta {dados['oferta']!r} não é do produto do pedido"
        repositorio.mudar_estado_se_nao_pago(pedido_id, repositorio.ESTADO_CANCELADO)
        return 'ok', ''
    if evento in EVENTOS_DEVOLUCAO:
        logger.warning(f'[HOTMART] ⚠️ {evento} no pedido #{pedido_id} ({transacao}) — Estante continua aberta')
        return 'ok', ''
    return 'ignorado', f'evento {evento} sem regra'
