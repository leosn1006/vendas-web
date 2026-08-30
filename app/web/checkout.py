"""
Serviço de Web Checkout — orquestra BB Pay e banco de dados.

Isolado de app.py para manter as rotas Flask como roteadores puros.
"""
import base64
import io
import logging
import os
import re
import shutil
from datetime import datetime, timedelta

import qrcode as qrcode_lib

logger = logging.getLogger(__name__)

COOKIE_MAX_AGE_FUNIL = 86400  # 24h — alinhado à validade do PIX do BB Pay (gerar_pix: expiracao = now + 24h)


def rastrear_visita_funil(request_obj, produto_id: int, estado_novo: int) -> int:
    """
    Cria ou reaproveita um pedido "não finalizado" (estado 1004 = chegou na página de vendas,
    1003 = chegou no checkout) pra essa visita, usando um cookie por produto
    (`pedido_web_<produto_id>`). Mesma ideia do fluxo WhatsApp (`criar_pedido`), que já cria um
    pedido no clique do botão, antes de qualquer identidade do cliente.

    - Se o cookie aponta pra um pedido desse produto ainda em 1004/1003: reaproveita a mesma
      linha (evita criar um pedido novo a cada F5), avançando pra `estado_novo` se for o caso
      (nunca regride de 1003 de volta pra 1004).
    - Senão: cria um pedido novo em `estado_novo`, só com dados de campanha da querystring
      (sem nome/e-mail — isso só é preenchido em `finalizar_pedido_web`, no Finalizar Compra).

    Retorna o pedido_id. Quem chamar deve gravar/renovar o cookie na resposta com esse valor.
    """
    from database import get_pedido_nao_finalizado, avancar_pedido_web, criar_pedido_web_inicial

    cookie_nome = f'pedido_web_{produto_id}'
    pedido_id_cookie = request_obj.cookies.get(cookie_nome, '')

    if pedido_id_cookie.isdigit():
        pedido = get_pedido_nao_finalizado(int(pedido_id_cookie), produto_id)
        if pedido:
            if pedido['estado_id'] == 1004 and estado_novo == 1003:
                avancar_pedido_web(pedido['id'], 1003)
            return pedido['id']

    args = request_obj.args
    dns_origem = (request_obj.headers.get('X-Forwarded-Host') or request_obj.host or '').split(':')[0].lower()
    return criar_pedido_web_inicial(
        produto_id, estado_novo, dns_origem=dns_origem,
        gclid=args.get('gclid', ''),
        campaignid=args.get('gad_campaignid', ''),
        adgroupid=args.get('adgroupid', ''),
        creative=args.get('creative', ''),
        matchtype=args.get('matchtype', ''),
        device=args.get('device', ''),
        placement=args.get('placement', ''),
        video_id=args.get('video_id', ''),
    )


def get_pedido_finalizado_via_cookie(request_obj, produto_id: int):
    """
    Verifica se o cookie pedido_web_<produto_id> aponta pra um pedido que já saiu da
    pré-identificação (1000 pago, 1001 identidade preenchida, 1002 aguardando pix,
    1005 aguardando autorização de cartão, 1006 cartão negado nesta tentativa).
    Usado por /pay/<produto_id> pra decidir se redireciona pro fluxo de retomada
    (?pedido=<id>, já tratado pelo JS de checkout.html) em vez de criar um pedido
    1003 novo via rastrear_visita_funil.

    Retorna o pedido_id nesse caso, ou None (cookie ausente/expirado, pedido de
    outro produto, ou ainda em 1004/1003 — segue fluxo normal).
    """
    from database import get_pedido

    cookie_nome = f'pedido_web_{produto_id}'
    pedido_id_cookie = request_obj.cookies.get(cookie_nome, '')
    if not pedido_id_cookie.isdigit():
        return None

    pedido = get_pedido(int(pedido_id_cookie))
    if pedido and pedido['produto_id'] == produto_id and pedido['estado_id'] in (1000, 1001, 1002, 1005, 1006):
        return pedido['id']
    return None


def _formatar_documento(numero: str, tipo: int) -> str:
    """Formata CPF ou CNPJ. Suporta CNPJ alfanumérico (Receita Federal jun/2026)."""
    d = re.sub(r'[^A-Za-z0-9]', '', str(numero))
    if tipo == 1 and len(d) == 11:   # CPF
        return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}'
    if tipo == 2 and len(d) == 14:   # CNPJ
        return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'
    return d


def _gerar_qrcode_base64(texto: str) -> str:
    img = qrcode_lib.make(texto)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def gerar_pix(body: dict, url_base: str = '', dns_origem: str = '') -> dict:
    """
    Cria um pedido em `pedidos` (estado 1001) e gera uma solicitação PIX no BB Pay.

    Retorna dict pronto para jsonify com:
      txid, qrcode_texto, qrcode_base64, url_bbpay, valor, pedido_id
      (ou fallback=True em caso de falha no BB Pay)
    """
    from web.bb_pay import criar_solicitacao
    from database import (get_produto_disponivel_web, resolver_valor_principal_produto,
                          criar_pedido_web_unificado, atualizar_pedido_solicitacao_bb,
                          get_phone_number_id_produto, criar_itens_pedido_web,
                          listar_bumps_validos, get_pedido_nao_finalizado, finalizar_pedido_web)

    produto_id = int(body.get('produto_id', 1))
    produto = get_produto_disponivel_web(produto_id)
    ebook_principal, valor_principal = resolver_valor_principal_produto(produto_id)
    if not produto or not ebook_principal:
        # Defesa: a página de checkout já bloqueia produto sem e-book principal vinculado antes
        # de chegar aqui — isso só acontece numa corrida rara (ex: admin desvincula entre o
        # carregamento da página e o envio do form).
        logger.error(f'[WEB-CHECKOUT] Produto #{produto_id} sem e-book principal vinculado ao gerar Pix.')
        return {'fallback': True}
    numero_convenio = int(produto.get('numero_convenio_bb', 0)) if produto else 0

    # Bumps: nunca confiar em preço vindo do cliente — releitura pelos ids escolhidos.
    bump_rows = listar_bumps_validos(produto_id, body.get('bump_ids'))
    valor = valor_principal + sum(float(b['preco_promocional']) for b in bump_rows)
    phone_number_id = get_phone_number_id_produto(produto_id) or os.getenv('WHATSAPP_PHONE_NUMBER_ID', '')

    # Normaliza telefone para formato WhatsApp: DDI vem do frontend, fallback 55
    _ddi   = re.sub(r'\D', '', body.get('ddi', '55')) or '55'
    _phone = re.sub(r'\D', '', body.get('whatsapp', ''))
    if _phone and not _phone.startswith(_ddi):
        _phone = _ddi + _phone
    # Remove o 9º dígito de celular BR para compatibilidade com formato do webhook WhatsApp
    if len(_phone) == 13 and _phone[4] == '9':  # ex: 5561981163324 → 556181163324
        _phone = _phone[:4] + _phone[5:]

    # Se a visita já tinha um pedido "não finalizado" (1004/1003, criado ao carregar a
    # landing/checkout), reaproveita essa linha em vez de criar uma nova — mantém o funil
    # inteiro (landing → checkout → finalizado → pago) num único registro. Se não houver (ou
    # já tiver sido finalizado antes, ex: cliente trocando de order bump), cria um pedido novo.
    pedido_id_body = body.get('pedido_id')
    pedido_existente = get_pedido_nao_finalizado(int(pedido_id_body), produto_id) if pedido_id_body else None

    if pedido_existente:
        pedido_id = pedido_existente['id']
        finalizar_pedido_web(
            pedido_id,
            phone_number_id=phone_number_id,
            contact_phone=_phone,
            contact_name=body.get('nome', ''),
            email=body.get('email', ''),
        )
    else:
        pedido_id = criar_pedido_web_unificado(
            produto_id=produto_id,
            phone_number_id=phone_number_id,
            contact_phone=_phone,
            contact_name=body.get('nome', ''),
            dns_origem=dns_origem,
            email=body.get('email', ''),
            gclid=body.get('gclid', ''),
            campaignid=body.get('campaignid', ''),
            adgroupid=body.get('adgroupid', ''),
            creative=body.get('creative', ''),
            matchtype=body.get('matchtype', ''),
            device=body.get('device', ''),
            placement=body.get('placement', ''),
            video_id=body.get('video_id', ''),
        )
    try:
        criar_itens_pedido_web(pedido_id, produto_id, ebook_principal, valor_principal, bump_rows)
    except Exception as e:
        # Snapshot informativo — uma falha aqui não pode derrubar o checkout em si.
        logger.error(f'[WEB-CHECKOUT] Erro ao gravar itens do pedido #{pedido_id}: {e}')

    try:
        if not url_base:
            url_base = os.getenv('APP_BASE_URL', 'http://localhost').rstrip('/')
        url_retorno = f'{url_base}/pay/{produto_id}?pedido={pedido_id}'
        _email = body.get('email', '')
        _descricao = f'Pedido #{pedido_id} | {_email}' if _email else f'Pedido #{pedido_id}'
        qr = criar_solicitacao(valor=valor, pedido_web_id=pedido_id,
                               numero_convenio=numero_convenio,
                               descricao=_descricao,
                               url_retorno=url_retorno)
        expiracao = (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        atualizar_pedido_solicitacao_bb(
            pedido_id=pedido_id,
            numero_solicitacao_bb=str(qr['numero_solicitacao']),
            url_bbpay=qr.get('url_solicitacao', ''),
            qr_code_pix=qr.get('qrcode_texto', ''),
            expiracao=expiracao,
        )
        qrcode_b64 = _gerar_qrcode_base64(qr['qrcode_texto']) if qr.get('qrcode_texto') else ''
        return {
            'txid':          str(qr['numero_solicitacao']),
            'qrcode_texto':  qr.get('qrcode_texto', ''),
            'qrcode_base64': qrcode_b64,
            'url_bbpay':     qr.get('url_solicitacao', ''),
            'valor':         qr['valor'],
            'pedido_id':     pedido_id,
        }
    except Exception as e:
        logger.error(f'[WEB-CHECKOUT] Erro BB Pay ao gerar PIX: {e}')
        return {
            'txid': None, 'qrcode_texto': '', 'qrcode_base64': '',
            'url_bbpay': None,
            'valor': valor, 'pedido_id': pedido_id,
            'fallback': True,
        }


def verificar_pagamento(txid: str) -> dict:
    """
    Consulta o BB Pay pelo numeroSolicitacao e confirma o pagamento se aprovado.
    Ao confirmar, dispara a task Celery que envia o e-book por e-mail (único canal de entrega
    do checkout web — WhatsApp não é mais usado aqui).

    Retorna {'pago': bool} (ou {'pago': False, 'erro': True} em caso de falha).
    """
    from web.bb_pay import consultar_pagamentos
    from database import (get_pedido_by_solicitacao_bb, get_produto_disponivel_web,
                          confirmar_pagamento_web, listar_itens_pedido)
    try:
        pedido = get_pedido_by_solicitacao_bb(txid)
        if not pedido:
            return {'pago': False}

        produto = get_produto_disponivel_web(pedido['produto_id'])
        numero_convenio = int(produto['numero_convenio_bb']) if produto else 0

        data = consultar_pagamentos(int(txid), numero_convenio)
        pago = data['pago']
        if pago and pedido['estado_id'] != 1000:
            pag = data['pagamento']
            # confirmar_pagamento_web só retorna True pra quem realmente ganhou a "corrida" —
            # se o polling do cliente e o sweep de resiliência caírem quase juntos pro mesmo
            # pedido, só um deles dispara a entrega (evita e-mail duplicado).
            confirmou_agora = confirmar_pagamento_web(
                pedido_id=pedido['id'],
                valor=pag.get('valorOriginalPagamento', pedido.get('valor_pago', 0)),
                nome_pagador=pag.get('nomePagador', ''),
                cpf_cnpj_pagador=_formatar_documento(
                    pag.get('numeroDocumentoPagador', ''),
                    pag.get('tipoDocumentoPagador', 0),
                ),
                valor_liquido=pag.get('valorLiquidoRecebedor'),
                data_repasse=pag.get('dataRepassePagamento'),
                e2e_id=pag.get('e2eId', ''),
            )
            if confirmou_agora:
                import tasks
                tasks.enviar_email_entrega.delay(pedido['id'])

        if not pago:
            return {'pago': False}

        # Pago agora ou já estava pago numa consulta anterior — devolve os itens pra
        # tela montar os botões de download (mesmo se o cliente reabrir o link depois).
        itens = [
            {'id': item['id'], 'tipo': item['tipo'], 'nome': item['nome'], 'valor': float(item['valor'])}
            for item in listar_itens_pedido(pedido['id'])
        ]
        return {'pago': True, 'pedido_id': pedido['id'], 'itens': itens}
    except Exception as e:
        logger.error(f'[WEB-CHECKOUT] Erro ao verificar pagamento {txid}: {e}')
        return {'pago': False, 'erro': True}


def categorizar_erro_cielo(status, return_code, return_message) -> tuple:
    """
    Mapeia o resultado técnico da Cielo pra uma categoria + mensagem amena. Nunca expor
    ReturnCode/ReturnMessage crus ao cliente — prática de mercado pra recusa de cartão é uma
    explicação objetiva + sempre uma alternativa, sem código técnico.

    Códigos vistos nos cartões de teste do sandbox (scripts/testar_cielo_sandbox.py):
    05=negada, 57=expirado, 78=bloqueado, 77=cancelado, 70=problema, 99=timeout.
    """
    if status is None:
        return 'instabilidade', 'Tivemos uma instabilidade ao confirmar seu pagamento. Tente novamente ou pague com Pix.'
    if str(return_code) == '99':
        return 'instabilidade', 'Tivemos uma instabilidade ao confirmar seu pagamento. Tente novamente ou pague com Pix.'
    if str(return_code) in ('57', '78', '77', '70'):
        return 'cartao_problema', 'Não conseguimos processar esse cartão. Confira os dados e a validade, ou tente outro.'
    return 'recusa_generica', 'Seu banco não autorizou a compra agora. Tente outro cartão ou pague com Pix.'


def gerar_cartao(body: dict, url_base: str = '', dns_origem: str = '') -> dict:
    """
    Cria/reaproveita um pedido (estado 1001, mesmas funções do Pix), avança pra 1005
    (aguardando autorização Cielo) ANTES de chamar a Cielo, autoriza com Capture=True e
    Interest=ByMerchant, e confirma o pagamento reaproveitando confirmar_pagamento_web — mesmo
    caminho do Pix, já método-agnóstico.

    Retorna dict pronto para jsonify:
      aprovado=True: {aprovado, pedido_id, itens}
      aprovado=False: {aprovado, pedido_id, mensagem (amena), permite_retry}
    """
    from web import cielo
    from web.parcelamento_cartao import calcular_total, parcelas_maximas_efetivas
    from database import (get_produto_disponivel_web, get_config_cartao_produto,
                          resolver_valor_principal_produto,
                          criar_pedido_web_unificado, get_pedido_cartao_para_retry, finalizar_pedido_web,
                          criar_itens_pedido_web, listar_bumps_validos, listar_itens_pedido,
                          avancar_pedido_cartao_aguardando, criar_tentativa_pagamento_cartao,
                          atualizar_tentativa_pagamento_cartao, confirmar_pagamento_web,
                          marcar_pedido_cartao_negado)

    produto_id = int(body.get('produto_id', 1))
    produto = get_produto_disponivel_web(produto_id)
    config_cartao = get_config_cartao_produto(produto_id)
    if not produto or not config_cartao:
        # Defesa: o front não deveria nem mostrar a aba Cartão nesse caso.
        return {'aprovado': False, 'mensagem': 'Cartão de crédito não disponível para este produto no momento.'}

    ebook_principal, valor_principal = resolver_valor_principal_produto(produto_id)
    if not ebook_principal:
        # Defesa: a página de checkout já bloqueia produto sem e-book principal vinculado antes
        # de chegar aqui — isso só acontece numa corrida rara (ex: admin desvincula entre o
        # carregamento da página e o envio do form).
        logger.error(f'[WEB-CHECKOUT] Produto #{produto_id} sem e-book principal vinculado ao gerar cartão.')
        return {'aprovado': False, 'mensagem': 'Produto não disponível no momento.'}

    bump_rows = listar_bumps_validos(produto_id, body.get('bump_ids'))
    valor_original = valor_principal + sum(float(b['preco_promocional']) for b in bump_rows)

    max_efetivo = parcelas_maximas_efetivas(valor_original, config_cartao['max_parcelas'])
    parcelas = max(1, min(int(body.get('parcelas', 1) or 1), max_efetivo))  # nunca confiar no client
    valor_total = calcular_total(valor_original, parcelas, config_cartao['parcelas_sem_juros'],
                                 float(config_cartao['taxa_juros_mensal']))
    valor_centavos = round(valor_total * 100)

    # Cria/reaproveita pedido — mesma ideia do Pix, mas também aceita 1006 (negado numa
    # tentativa anterior), pra tentar outro cartão não criar um pedido novo a cada vez.
    pedido_id_body = body.get('pedido_id')
    pedido_existente = get_pedido_cartao_para_retry(int(pedido_id_body), produto_id) if pedido_id_body else None
    eh_retry_de_negado = bool(pedido_existente and pedido_existente['estado_id'] == 1006)
    if pedido_existente:
        pedido_id = pedido_existente['id']
        # No-op se o pedido já passou de 1003/1004 (ex: retry vindo de 1006) — identidade já
        # foi capturada na tentativa anterior, WHERE da própria função protege contra regressão.
        finalizar_pedido_web(pedido_id, phone_number_id='', contact_phone='',
                             contact_name=body.get('nome', ''), email=body.get('email', ''))
    else:
        pedido_id = criar_pedido_web_unificado(
            produto_id=produto_id, phone_number_id='', contact_phone='',
            contact_name=body.get('nome', ''), dns_origem=dns_origem, email=body.get('email', ''),
            gclid=body.get('gclid', ''), campaignid=body.get('campaignid', ''),
            adgroupid=body.get('adgroupid', ''), creative=body.get('creative', ''),
            matchtype=body.get('matchtype', ''), device=body.get('device', ''),
            placement=body.get('placement', ''), video_id=body.get('video_id', ''),
        )

    # Só grava o snapshot de itens na primeira finalização — num retry após negação (1006), os
    # itens já foram gravados na tentativa anterior; gravar de novo duplicaria as linhas em
    # pedido_itens (afeta downloads e qualquer soma de receita sobre essa tabela).
    if not eh_retry_de_negado:
        try:
            criar_itens_pedido_web(pedido_id, produto_id, ebook_principal, valor_principal, bump_rows)
        except Exception as e:
            logger.error(f'[WEB-CHECKOUT] Erro ao gravar itens do pedido cartão #{pedido_id}: {e}')

    numero_cartao = re.sub(r'\D', '', body.get('numero_cartao', ''))
    cpf = re.sub(r'\D', '', body.get('cpf', ''))
    mes = re.sub(r'\D', '', str(body.get('mes', '')))
    ano = re.sub(r'\D', '', str(body.get('ano', '')))
    validade = f'{mes.zfill(2)}/{ano}' if mes and ano else ''
    cvv = re.sub(r'\D', '', body.get('cvv', ''))
    titular = body.get('titular') or body.get('nome', '')
    # Resolve a bandeira real (cache/Consulta BIN Cielo) antes de montar o payload — só cai
    # pro palpite do cliente (ou vazio) se a resolução falhar; nunca bloqueia a autorização.
    from web.bandeira_bin import resolver_bandeira
    bandeira = resolver_bandeira(numero_cartao) or body.get('bandeira', '')
    merchant_order_id = str(pedido_id)
    cartao_mascarado = f'{numero_cartao[:6]}{"*" * 6}{numero_cartao[-4:]}' if len(numero_cartao) >= 10 else ''

    avancar_pedido_cartao_aguardando(pedido_id)

    # Auditoria: NUNCA gravar CardNumber/SecurityCode crus.
    request_para_auditoria = {
        'MerchantOrderId': merchant_order_id, 'Amount': valor_centavos, 'Installments': parcelas,
        'CreditCard': {'CardNumber': cartao_mascarado, 'Holder': titular, 'ExpirationDate': validade, 'Brand': bandeira},
    }
    tentativa_id = criar_tentativa_pagamento_cartao(
        pedido_id=pedido_id, merchant_order_id=merchant_order_id,
        valor_original=valor_original, valor=valor_total, parcelas=parcelas,
        bandeira=bandeira, cartao_mascarado=cartao_mascarado, nome_titular=titular,
        request_json=request_para_auditoria,
    )

    try:
        resposta = cielo.criar_transacao(
            merchant_order_id=merchant_order_id, valor_centavos=valor_centavos, parcelas=parcelas,
            soft_descriptor=config_cartao['soft_descriptor'], nome=body.get('nome', ''), cpf=cpf,
            numero_cartao=numero_cartao, titular=titular, validade=validade, cvv=cvv, bandeira=bandeira,
        )
    except Exception as e:
        # Timeout/erro de rede: pedido fica em 1005 (sinal pro sweep de reconciliação),
        # a tentativa de auditoria fica sem payment_id.
        logger.error(f'[WEB-CHECKOUT] Erro de rede/timeout na autorização Cielo — pedido #{pedido_id}: {e}')
        return {
            'aprovado': False, 'pedido_id': pedido_id, 'permite_retry': True,
            'mensagem': 'Tivemos uma instabilidade ao confirmar seu pagamento. Tente novamente ou pague com Pix.',
        }

    payment = resposta.get('Payment', {})
    status = payment.get('Status')
    # Payment.CreditCard.Brand da resposta: no sandbox, confirmamos que é só eco do que foi
    # enviado (Brand="Undefined" quando omitido, ou o valor errado que mandamos de propósito
    # num teste) — não é uma validação independente contra o PAN real, pelo menos aqui. Não
    # temos como confirmar se produção se comporta diferente (validação real contra a rede do
    # cartão), então mantemos essa sobrescrita como uma aposta de custo zero: se em produção
    # for mesmo autoritativa, corrige de graça; se for só eco como no sandbox, é um no-op
    # inofensivo (COALESCE mantém o valor resolvido antes do envio quando não vier nada aqui).
    bandeira_confirmada = (payment.get('CreditCard', {}).get('Brand') or '').lower() or None
    if bandeira_confirmada == 'undefined':
        bandeira_confirmada = None

    if status == 2:
        atualizar_tentativa_pagamento_cartao(
            tentativa_id, payment_id=payment.get('PaymentId'), tid=payment.get('Tid'),
            authorization_code=payment.get('AuthorizationCode'), status_cielo=status,
            return_code=payment.get('ReturnCode'), return_message=payment.get('ReturnMessage'),
            response_json=resposta, bandeira=bandeira_confirmada,
        )
        confirmou_agora = confirmar_pagamento_web(
            pedido_id=pedido_id, valor=valor_total, nome_pagador=body.get('nome', ''),
            cpf_cnpj_pagador=_formatar_documento(cpf, 1),
        )
        if confirmou_agora:
            import tasks
            tasks.enviar_email_entrega.delay(pedido_id)
        itens = [
            {'id': item['id'], 'tipo': item['tipo'], 'nome': item['nome'], 'valor': float(item['valor'])}
            for item in listar_itens_pedido(pedido_id)
        ]
        return {'aprovado': True, 'pedido_id': pedido_id, 'itens': itens}

    # Negado — resposta HTTP ok (201), mas Status diferente de aprovado.
    categoria, mensagem = categorizar_erro_cielo(status, payment.get('ReturnCode'), payment.get('ReturnMessage'))
    atualizar_tentativa_pagamento_cartao(
        tentativa_id, payment_id=payment.get('PaymentId'), tid=payment.get('Tid'),
        authorization_code=payment.get('AuthorizationCode'), status_cielo=status,
        return_code=payment.get('ReturnCode'), return_message=payment.get('ReturnMessage'),
        categoria_erro=categoria, response_json=resposta, bandeira=bandeira_confirmada,
    )
    marcar_pedido_cartao_negado(pedido_id)
    return {'aprovado': False, 'pedido_id': pedido_id, 'mensagem': mensagem, 'permite_retry': True}


def reconciliar_cartao(pedido_id: int) -> dict:
    """
    Rechecagem de um pedido preso em 1005 (chamado pelo sweep do Celery Beat a cada 15 min,
    só para pedidos há mais de 5 min nesse estado). Busca a tentativa mais recente: se já tem
    payment_id, consulta direto por ele; senão (timeout puro, a chamada original nunca
    respondeu), consulta por MerchantOrderId (=pedido_id em texto, reaproveitado em cada
    retry de propósito) — que devolve só uma lista de PaymentIds, então cada um precisa ser
    consultado individualmente para saber o Status. Aprovado → confirmar_pagamento_web (mesmo
    caminho do Pix). Nenhuma resposta conclusiva → não mexe, próxima rodada tenta de novo.
    """
    from web import cielo
    from database import (get_ultima_tentativa_pagamento_cartao, confirmar_pagamento_web,
                          marcar_pedido_cartao_negado, atualizar_tentativa_pagamento_cartao)

    tentativa = get_ultima_tentativa_pagamento_cartao(pedido_id)
    if not tentativa:
        return {'pago': False}

    if tentativa.get('payment_id'):
        payment_ids = [tentativa['payment_id']]
    else:
        try:
            resultado = cielo.consultar_por_merchant_order_id(str(pedido_id))
        except Exception as e:
            logger.error(f'[WEB-CHECKOUT] Erro ao consultar MerchantOrderId #{pedido_id} na Cielo: {e}')
            return {'pago': False}
        payment_ids = [p['PaymentId'] for p in resultado.get('Payments', []) if p.get('PaymentId')]
        if not payment_ids:
            # Cielo nunca recebeu a chamada original — segue em 1005, próxima rodada tenta de novo.
            return {'pago': False}

    aprovado = None
    teve_resposta = False
    for payment_id in payment_ids:
        try:
            resposta = cielo.consultar_por_payment_id(payment_id)
        except Exception as e:
            logger.error(f'[WEB-CHECKOUT] Erro ao consultar PaymentId {payment_id}: {e}')
            continue
        payment = resposta.get('Payment', {})
        teve_resposta = True
        if payment.get('Status') == 2:
            aprovado = payment
            break

    if aprovado:
        atualizar_tentativa_pagamento_cartao(
            tentativa['id'], payment_id=aprovado.get('PaymentId'), tid=aprovado.get('Tid'),
            authorization_code=aprovado.get('AuthorizationCode'), status_cielo=2,
            return_code=aprovado.get('ReturnCode'), return_message=aprovado.get('ReturnMessage'),
        )
        confirmou_agora = confirmar_pagamento_web(pedido_id=pedido_id, valor=float(tentativa['valor']))
        if confirmou_agora:
            import tasks
            tasks.enviar_email_entrega.delay(pedido_id)
        return {'pago': True, 'pedido_id': pedido_id}

    if teve_resposta:
        # Teve resposta conclusiva da Cielo (Status != 2) e não é aprovado — negado.
        marcar_pedido_cartao_negado(pedido_id)
    return {'pago': False}


def _resolver_caminho_entregavel(nome_arquivo_fisico: str):
    """
    Resolve o caminho físico em `storage/entregaveis/` para um nome de arquivo — pasta própria
    do checkout web, não exposta publicamente pelo nginx (diferente de `static/arquivos/`, que
    continua pública de propósito para o fluxo WhatsApp, que entrega antes do pagamento).

    Auto-cura: se ninguém copiou o arquivo pra cá ainda (ex: bônus/bump cadastrado recentemente
    no admin), busca em static/arquivos/ (onde o admin de fato salva o arquivo) e copia na hora,
    pra não depender de um passo manual que é fácil esquecer. Nunca deixa um erro de I/O
    (permissão, disco cheio, corrida entre duas requisições copiando ao mesmo tempo) derrubar a
    requisição — na pior hipótese, cai no (None, 500) abaixo.

    Retorna (caminho, None) em caso de sucesso, ou (None, 404/500) em caso de falha.
    """
    caminho = os.path.join(os.path.dirname(__file__), '..', 'storage', 'entregaveis',
                            nome_arquivo_fisico)

    if os.path.exists(caminho):
        return caminho, None

    origem = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'arquivos',
                          nome_arquivo_fisico)
    try:
        if os.path.exists(origem):
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            tmp = f'{caminho}.tmp-{os.getpid()}'
            shutil.copyfile(origem, tmp)
            os.replace(tmp, caminho)  # atômico — evita servir arquivo parcialmente copiado
            logger.info(f'[WEB-CHECKOUT] Copiado automaticamente para storage/entregaveis: {nome_arquivo_fisico}')
            return caminho, None
        else:
            logger.error(f'[WEB-CHECKOUT] Arquivo não encontrado em static/arquivos/: {nome_arquivo_fisico}')
            return None, 404
    except OSError as e:
        logger.error(f'[WEB-CHECKOUT] Falha ao copiar {nome_arquivo_fisico} para storage/entregaveis: {e}')
        return None, 500


def baixar_item_pedido(pedido_id: int, item_id: int):
    """
    Retorna (caminho, nome_arquivo) de um item de `pedido_itens` (principal, bônus ou bump),
    desde que o pedido esteja confirmado como pago (estado_id = 1000).

    Os arquivos usados pelo checkout web são cópias colocadas em `storage/entregaveis/`, não os
    originais (ver `_resolver_caminho_entregavel`).

    Retorna (None, 403) se o pedido não existe, não pertence ao item, ou não está pago.
    """
    from database import get_pedido, get_item_pedido

    item = get_item_pedido(item_id, pedido_id)
    if not item:
        return None, 403

    pedido = get_pedido(pedido_id)
    if not pedido or pedido.get('estado_id') != 1000:
        return None, 403

    # produto_bonus/produto_bump.path_arquivo é preenchido no admin como URL pública completa
    # (convenção do fluxo WhatsApp, que precisa de link pra enviar como mídia) — aqui só
    # interessa o nome do arquivo em si, pra juntar com as pastas locais. os.path.basename
    # funciona tanto pra URL completa quanto pra nome puro (caso do produto principal).
    nome_arquivo_fisico = os.path.basename(item['path_arquivo'])

    caminho, erro = _resolver_caminho_entregavel(nome_arquivo_fisico)
    if erro:
        return None, erro

    return caminho, item['nome_arquivo']


def _pedido_pago(pedido) -> bool:
    """Pago via web (estado_id == 1000) ou via WhatsApp (estado_id == 0) — mesma convenção
    usada em outras queries de receita do database.py (estado_id IN (0, 1000))."""
    return pedido['estado_id'] in (0, 1000)


def _produto_ja_entregue_whatsapp(pedido) -> bool:
    """No WhatsApp, o e-book principal só foi de fato entregue por mensagem quando o fluxo de
    'pedido' roda e manda o arquivo pro cliente — marcado por `data_envio_pedido` (setado junto
    com estado_id=3, ver fluxo_pedido_dinamico.py). Antes disso (estado 1='clicou no anúncio',
    2='intro enviada'), nada foi entregue ainda, mesmo que o pedido já tenha guid/pedido_itens
    criados desde a hora da criação do lead. Pedido pago (estado_id=0) sempre conta como
    entregue também, como rede de segurança."""
    return pedido.get('data_envio_pedido') is not None or _pedido_pago(pedido)


def resolver_pedido_por_guid(guid: str, item_id: int = None):
    """
    Resolve o guid público (link /pedido/<guid>) num pedido, com a regra de acesso por canal:

      - Pedido web (estado_id >= 1000): tudo (principal/bônus/bump) só fica acessível com
        estado_id == 1000 (pago) — igual sempre funcionou.
      - Pedido WhatsApp (estado_id < 1000): o principal só fica acessível depois que o produto
        foi de fato entregue por mensagem (ver _produto_ja_entregue_whatsapp) — um lead recém-
        criado (acabou de clicar no anúncio) ainda não recebeu nada, mesmo já tendo guid/
        pedido_itens. Uma vez entregue, o principal fica acessível; só os itens tipo='bonus'
        exigem estado_id == 0 (pago) — o bônus aparece na lista mesmo bloqueado, como chamariz
        pro cliente mandar o comprovante.

    Retorna (pedido, item, erro):
      - guid inexistente:                                 (None, None, 'nao_encontrado')
      - pedido web não pago:                               (pedido, None, 'aguardando_pagamento')
      - pedido whatsapp ainda não entregue:                (pedido, None, 'ainda_nao_entregue')
      - item_id informado mas não pertence ao pedido:      (pedido, None, 'item_invalido')
      - item bônus do whatsapp sem pagamento confirmado:   (pedido, item, 'aguardando_pagamento')
      - tudo ok:                                           (pedido, item_ou_None, None)

    Usa get_item_pedido_ebook (não get_item_pedido) para que o item já venha com
    nome/imagens/arquivo resolvidos a partir do catálogo de e-books — o item retornado aqui é
    reaproveitado tanto pela tela do leitor quanto pela rota que serve o PDF.
    """
    from database import get_pedido_by_guid, get_item_pedido_ebook

    pedido = get_pedido_by_guid(guid)
    if not pedido:
        return None, None, 'nao_encontrado'

    canal_web = pedido['estado_id'] >= 1000
    pago = _pedido_pago(pedido)

    if canal_web and not pago:
        return pedido, None, 'aguardando_pagamento'

    if not canal_web and not _produto_ja_entregue_whatsapp(pedido):
        return pedido, None, 'ainda_nao_entregue'

    if item_id is not None:
        item = get_item_pedido_ebook(item_id, pedido['id'])
        if not item:
            return pedido, None, 'item_invalido'
        if not canal_web and item['tipo'] == 'bonus' and not pago:
            return pedido, item, 'aguardando_pagamento'
        return pedido, item, None

    return pedido, None, None


def separar_itens_visiveis(pedido, itens):
    """Separa hero (principal) e outros (bônus/bump) pra tela /pedido/<guid>, marcando cada
    item de 'outros' com um campo extra 'bloqueado'. Bônus do WhatsApp aparecem sempre, mesmo
    bloqueados — funcionam como chamariz pro cliente mandar o comprovante de pagamento e
    liberar. Só é chamada depois que resolver_pedido_por_guid já confirmou que o pedido está
    pago (web) ou que o produto já foi entregue (whatsapp) — ver ali as regras de acesso."""
    hero = next((i for i in itens if i['tipo'] == 'principal'), None)
    canal_web = pedido['estado_id'] >= 1000
    pago = _pedido_pago(pedido)

    outros = []
    for item in itens:
        if item is hero:
            continue
        item = dict(item)
        item['bloqueado'] = (not canal_web and item['tipo'] == 'bonus' and not pago)
        outros.append(item)
    return hero, outros


def entregar_pdf(pedido_id: int, bonus: bool = False):
    """
    Mantido para compatibilidade com pedidos antigos (pedido_web).
    Valida se o pedido_web foi pago e retorna (caminho, nome_arquivo).

    Retorna (None, 403) se o pagamento não foi confirmado.
    Retorna (None, 404) se bonus=True e o produto não tem url_pdf_bonus.
    """
    from database import get_pedido_web, get_produto_web
    pedido = get_pedido_web(pedido_id)
    if not pedido or pedido.get('estado') != 0:
        return None, 403
    produto = get_produto_web(pedido['remetente_id'])
    if bonus:
        arquivo = produto.get('url_pdf_bonus', '') if produto else ''
        if not arquivo:
            return None, 404
    else:
        arquivo = produto.get('url_pdf', 'paes-sem-gluten.pdf') if produto else 'paes-sem-gluten.pdf'
    caminho = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'arquivos', arquivo)
    return caminho, arquivo
