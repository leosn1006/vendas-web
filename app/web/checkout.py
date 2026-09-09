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


def _erro_validacao_email(body: dict):
    """
    Checagem de e-mail compartilhada por gerar_pix e gerar_cartao — defesa contra bypass
    do client (o form já bloqueia isso antes de chamar a API). Retorna o dict de erro pronto
    pra jsonify, ou None se o e-mail passou.
    """
    from web.email_validacao import validar_email

    checagem = validar_email(body.get('email', ''))
    if not checagem['valido']:
        return {'erro_validacao': True, 'campo': 'email', 'motivo': checagem['motivo']}
    return None


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

    erro = _erro_validacao_email(body)
    if erro:
        return erro

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
        from web.pix_estatico import gerar_payload_pix, gerar_qrcode_base64 as _gerar_qr_estatico
        from database import buscar_chave_pix_venda_web
        from database import db as _db

        chave_pix = buscar_chave_pix_venda_web(produto_id)
        if not chave_pix:
            raise RuntimeError(f'Produto #{produto_id} sem chave PIX para venda web (para_venda_web=1)')

        # Ler nome_recebedor e cidade da config NF-e do produto
        cfg_nfe = _db.execute_query(
            """SELECT nc.razao_social, nc.x_mun
               FROM produtos p
               LEFT JOIN nfe_configuracao nc ON nc.id = p.nfe_config_id
               WHERE p.id = %s""",
            (produto_id,), fetch_one=True,
        )
        nome_recebedor = (cfg_nfe or {}).get('razao_social') or 'LBE LIVROS LTDA'
        cidade         = (cfg_nfe or {}).get('x_mun') or 'Brasilia'

        qrcode_texto = gerar_payload_pix(
            chave_pix=chave_pix,
            valor=valor,
            nome_recebedor=nome_recebedor,
            cidade=cidade,
            txid=str(pedido_id),
        )
        qrcode_b64 = _gerar_qr_estatico(qrcode_texto)
        expiracao = (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        atualizar_pedido_solicitacao_bb(
            pedido_id=pedido_id,
            numero_solicitacao_bb=None,   # QR estático — sem solicitação BB Pay
            url_bbpay=None,
            qr_code_pix=qrcode_texto,
            expiracao=expiracao,
        )
        return {
            'txid':          str(pedido_id),
            'qrcode_texto':  qrcode_texto,
            'qrcode_base64': qrcode_b64,
            'url_bbpay':     None,
            'valor':         valor,
            'pedido_id':     pedido_id,
        }

        # --- FLUXO BB PAY DINÂMICO (mantido para rollback) ---
        # if not url_base:
        #     url_base = os.getenv('APP_BASE_URL', 'http://localhost').rstrip('/')
        # url_retorno = f'{url_base}/pay/{produto_id}?pedido={pedido_id}'
        # _email = body.get('email', '')
        # _descricao = f'Pedido #{pedido_id} | {_email}' if _email else f'Pedido #{pedido_id}'
        # qr = criar_solicitacao(valor=valor, pedido_web_id=pedido_id,
        #                        numero_convenio=numero_convenio,
        #                        descricao=_descricao,
        #                        url_retorno=url_retorno)
        # expiracao = (datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        # atualizar_pedido_solicitacao_bb(
        #     pedido_id=pedido_id,
        #     numero_solicitacao_bb=str(qr['numero_solicitacao']),
        #     url_bbpay=qr.get('url_solicitacao', ''),
        #     qr_code_pix=qr.get('qrcode_texto', ''),
        #     expiracao=expiracao,
        # )
        # qrcode_b64 = _gerar_qrcode_base64(qr['qrcode_texto']) if qr.get('qrcode_texto') else ''
        # return {
        #     'txid':          str(qr['numero_solicitacao']),
        #     'qrcode_texto':  qr.get('qrcode_texto', ''),
        #     'qrcode_base64': qrcode_b64,
        #     'url_bbpay':     qr.get('url_solicitacao', ''),
        #     'valor':         qr['valor'],
        #     'pedido_id':     pedido_id,
        # }
    except Exception as e:
        logger.error(f'[WEB-CHECKOUT] Erro ao gerar PIX estático: {e}')
        return {
            'txid': None, 'qrcode_texto': '', 'qrcode_base64': '',
            'url_bbpay': None,
            'valor': valor, 'pedido_id': pedido_id,
            'fallback': True,
        }


def verificar_pagamento(txid: str) -> dict:
    """
    Verifica se o pedido foi pago e confirma se positivo.

    txid = str(pedido_id) para pedidos com QR estático (novo fluxo).
    txid = numero_solicitacao_bb para pedidos BB Pay dinâmico (fallback de transição).

    Retorna {'pago': bool} (ou {'pago': False, 'erro': True} em caso de falha).
    """
    from database import (get_pedido, get_pedido_by_solicitacao_bb,
                          get_produto_disponivel_web, confirmar_pagamento_web,
                          listar_itens_pedido, garantir_guid_pedido,
                          buscar_pagamento_pix_por_txid)
    try:
        # Tenta interpretar txid como pedido_id numérico (QR estático)
        pedido = None
        _usa_bb_pay = False
        if txid.isdigit():
            pedido = get_pedido(int(txid))
            # Se pedido existe mas foi criado com BB Pay dinâmico, usar fallback
            if pedido and pedido.get('numero_solicitacao_bb'):
                _usa_bb_pay = True

        if pedido is None and not txid.isdigit():
            # txid não numérico → é numero_solicitacao_bb (pedido legado BB Pay)
            pedido = get_pedido_by_solicitacao_bb(txid)
            _usa_bb_pay = True

        if not pedido:
            return {'pago': False}

        # --- FALLBACK BB PAY (pedidos legados com numero_solicitacao_bb) ---
        if _usa_bb_pay:
            from web.bb_pay import consultar_pagamentos
            produto = get_produto_disponivel_web(pedido['produto_id'])
            numero_convenio = int(produto['numero_convenio_bb']) if produto else 0
            solicitacao_id = pedido.get('numero_solicitacao_bb') or txid
            data = consultar_pagamentos(int(solicitacao_id), numero_convenio)
            pago = data['pago']
            if pago and pedido['estado_id'] != 1000:
                pag = data['pagamento']
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

        # --- FLUXO PIX ESTÁTICO (txid numérico sem numero_solicitacao_bb) ---
        else:
            if pedido['estado_id'] != 1000:
                # Consulta pagamento_pix pelo txid = str(pedido_id)
                pix = buscar_pagamento_pix_por_txid(str(pedido['id']))
                if not pix:
                    return {'pago': False}
                # confirmar_pagamento_web é idempotente — só o primeiro retorna True
                confirmou_agora = confirmar_pagamento_web(
                    pedido_id=pedido['id'],
                    valor=float(pix.get('valor', pedido.get('valor_pago', 0))),
                    nome_pagador=pix.get('nome_pagador', ''),
                    cpf_cnpj_pagador=pix.get('cpf_cnpj', ''),
                    valor_liquido=None,
                    data_repasse=None,
                    e2e_id=pix.get('e2e_id', ''),
                )
                if confirmou_agora:
                    import tasks
                    tasks.enviar_email_entrega.delay(pedido['id'])

        # Pago (agora ou já estava) — devolve itens para botões de download
        itens = [
            {'id': item['id'], 'tipo': item['tipo'], 'nome': item['nome'], 'valor': float(item['valor'])}
            for item in listar_itens_pedido(pedido['id'])
        ]
        return {'pago': True, 'pedido_id': pedido['id'], 'guid': garantir_guid_pedido(pedido['id']), 'itens': itens}
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
                          resolver_valor_principal_produto, garantir_guid_pedido,
                          criar_pedido_web_unificado, get_pedido_cartao_para_retry, finalizar_pedido_web,
                          criar_itens_pedido_web, listar_bumps_validos, listar_itens_pedido,
                          avancar_pedido_cartao_aguardando, criar_tentativa_pagamento_cartao,
                          atualizar_tentativa_pagamento_cartao, confirmar_pagamento_web,
                          marcar_pedido_cartao_negado)

    erro = _erro_validacao_email(body)
    if erro:
        return erro

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
        guid = garantir_guid_pedido(pedido_id)
        return {'aprovado': True, 'pedido_id': pedido_id, 'guid': guid, 'itens': itens}

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
    com estado_id=3, ver fluxo_pedido_dinamico.py). Antes disso (estado 1='clicou no anúncio'),
    nada foi entregue ainda, mesmo que o pedido já tenha guid/pedido_itens criados desde a hora
    da criação do lead. Pedido pago (estado_id=0) sempre conta como entregue também, como rede
    de segurança.

    A partir de estado_id=2 ('respondeu a introdução' em diante — inclui o lock temporário 12
    durante a execução do fluxo de pedido) o principal já libera como preview/isca, com o bônus
    ainda bloqueado (ver resolver_pedido_por_guid) — usado pelo botão de link da Estante mandado
    logo na introdução, antes da entrega de verdade."""
    estado_id = pedido.get('estado_id') or 0
    return pedido.get('data_envio_pedido') is not None or _pedido_pago(pedido) or estado_id >= 2


def resolver_pedido_por_guid(guid: str, item_id: int = None):
    """
    Resolve o guid público (link /pedido/<guid>) num pedido, com a regra de acesso por canal:

      - Pedido web (estado_id >= 1000): tudo (principal/bônus/bump) só fica acessível com
        estado_id == 1000 (pago) — igual sempre funcionou.
      - Pedido WhatsApp (estado_id < 1000): o principal só fica acessível depois que o produto
        foi de fato entregue por mensagem OU o cliente já respondeu a introdução (estado_id >= 2,
        ver _produto_ja_entregue_whatsapp) — um lead recém-criado (acabou de clicar no anúncio,
        estado 1) ainda não recebeu nada nem interagiu, mesmo já tendo guid/pedido_itens. A
        partir daí o principal fica acessível como preview/isca; só os itens tipo='bonus'
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


def listar_itens_ebook_do_cliente(pedido):
    """Junta todos os e-books pagos do cliente pra tela /pedido/<guid> — não só os do pedido que
    gerou o guid da URL, mas também os de outros pedidos pagos achados pelo mesmo email e/ou
    contact_phone (ver listar_pedidos_pagos_relacionados). Deduplica por e-book (não por linha
    de pedido_itens): o mesmo e-book pode ter sido vendido como principal num produto e como
    bônus/bump em outro, e o cliente pode ter comprado os dois.

    Regra de 'liberado prevalece': se o mesmo e-book aparecer bloqueado num pedido (bônus do
    WhatsApp ainda não pago) e liberado em outro pedido pago do cliente, mostra liberado — o
    cliente já tem acesso a esse e-book por outra via, não faz sentido escondê-lo.

    Só é chamada depois que resolver_pedido_por_guid já confirmou que o pedido do guid da URL
    está pago (web) ou que o produto já foi entregue (whatsapp) — ver ali as regras de acesso.
    """
    from database import (listar_itens_pedido_ebook, listar_pedidos_pagos_relacionados,
                          listar_itens_pedido_ebook_multiplos, garantir_guid_pedido)

    canal_web = pedido['estado_id'] >= 1000
    pago = _pedido_pago(pedido)

    linhas = []
    for item in listar_itens_pedido_ebook(pedido['id']):
        item = dict(item)
        item['guid_pedido'] = pedido['guid']
        item['bloqueado'] = (not canal_web and item['tipo'] == 'bonus' and not pago)
        linhas.append(item)

    relacionados = listar_pedidos_pagos_relacionados(
        pedido['id'], pedido.get('email'), pedido.get('contact_phone')
    )
    outros_ids = [r['id'] for r in relacionados]
    if outros_ids:
        # Só chama garantir_guid_pedido pra quem realmente não tem guid ainda (a maioria já
        # tem, gerado na criação — ver criar_pedido_web_unificado) — evita um SELECT+UPDATE
        # redundante por pedido relacionado em toda visita à página. Envolto em try/except
        # porque um erro aqui é sobre um pedido OUTRO que não o da URL — não pode derrubar a
        # página inteira por causa de um pedido relacionado que nem é o que o cliente abriu
        # (mesmo espírito do try/except em criar_pedido/gerar_pix pra criar_itens_pedido_web:
        # é um extra que enriquece a página, não algo que pode quebrá-la).
        for relacionado in relacionados:
            if not relacionado.get('guid'):
                try:
                    garantir_guid_pedido(relacionado['id'])
                except Exception as e:
                    logger.error(f"[ESTANTE] Erro ao gerar guid pro pedido relacionado #{relacionado['id']}: {e}")
        # Sempre busca por todos os outros_ids (não só os que já tinham guid) — quem passou
        # pelo garantir_guid_pedido acima com sucesso já está com guid gravado no banco a
        # tempo desta query; se algum tiver falhado (raro, já logado acima), o item aparece
        # com guid_pedido nulo — link de leitura quebrado só pra aquele item, não a página.
        for item in listar_itens_pedido_ebook_multiplos(outros_ids):
            item = dict(item)
            item['bloqueado'] = False  # já filtrado por estado_id IN (0,1000) na query
            linhas.append(item)

    return _consolidar_itens_ebook(linhas)


def _consolidar_itens_ebook(linhas):
    """Deduplica itens pelo e-book real (ebook_id; cai pra path_arquivo nos itens antigos sem
    ebook_produto_id, de antes da migration 061), preservando a ordem de primeira aparição
    (já vem ordenada por data de pagamento mais recente primeiro). Quando a mesma chave aparece
    mais de uma vez, prevalece a versão não-bloqueada — ver regra em listar_itens_ebook_do_cliente."""
    escolhidos = {}
    ordem = []
    for item in linhas:
        chave = item['ebook_id'] if item.get('ebook_id') else f"legacy:{item['path_arquivo']}"
        atual = escolhidos.get(chave)
        if atual is None:
            escolhidos[chave] = item
            ordem.append(chave)
        elif atual['bloqueado'] and not item['bloqueado']:
            escolhidos[chave] = item
    return [escolhidos[chave] for chave in ordem]


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
