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
    pré-identificação (1000 pago, 1001 identidade preenchida, 1002 aguardando pix).
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
    if pedido and pedido['produto_id'] == produto_id and pedido['estado_id'] in (1000, 1001, 1002):
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
    from database import (get_produto_disponivel_web,
                          criar_pedido_web_unificado, atualizar_pedido_solicitacao_bb,
                          get_phone_number_id_produto, criar_itens_pedido_web,
                          listar_bumps_validos, get_pedido_nao_finalizado, finalizar_pedido_web)

    produto_id = int(body.get('produto_id', 1))
    produto = get_produto_disponivel_web(produto_id)
    _teste_produto = os.getenv(f'CHECKOUT_VALOR_TESTE_PRODUTO_{produto_id}')
    valor_principal = float(_teste_produto or (produto.get('preco', 19.90) if produto else 19.90))
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
        criar_itens_pedido_web(pedido_id, produto, valor_principal, bump_rows)
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


def baixar_item_pedido(pedido_id: int, item_id: int):
    """
    Retorna (caminho, nome_arquivo) de um item de `pedido_itens` (principal, bônus ou bump),
    desde que o pedido esteja confirmado como pago (estado_id = 1000).

    Serve a partir de `storage/entregaveis/` — pasta própria do checkout web, não exposta
    publicamente pelo nginx (diferente de `static/arquivos/`, que continua pública de propósito
    para o fluxo WhatsApp, que entrega antes do pagamento). Os arquivos usados pelo checkout web
    são cópias colocadas lá, não os originais.

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

    caminho = os.path.join(os.path.dirname(__file__), '..', 'storage', 'entregaveis',
                            nome_arquivo_fisico)

    if not os.path.exists(caminho):
        # Auto-cura: se ninguém copiou o arquivo pra cá ainda (ex: bônus/bump cadastrado
        # recentemente no admin), busca em static/arquivos/ (onde o admin de fato salva o
        # arquivo) e copia na hora, pra não depender de um passo manual que é fácil esquecer.
        # Nunca deixa um erro de I/O (permissão, disco cheio, corrida entre duas requisições
        # copiando ao mesmo tempo) derrubar a requisição — na pior hipótese, cai no 404 abaixo.
        origem = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'arquivos',
                              nome_arquivo_fisico)
        try:
            if os.path.exists(origem):
                os.makedirs(os.path.dirname(caminho), exist_ok=True)
                tmp = f'{caminho}.tmp-{os.getpid()}'
                shutil.copyfile(origem, tmp)
                os.replace(tmp, caminho)  # atômico — evita servir arquivo parcialmente copiado
                logger.info(f'[WEB-CHECKOUT] Copiado automaticamente para storage/entregaveis: {nome_arquivo_fisico}')
            else:
                logger.error(f'[WEB-CHECKOUT] Arquivo não encontrado em static/arquivos/: {nome_arquivo_fisico}')
                return None, 404
        except OSError as e:
            logger.error(f'[WEB-CHECKOUT] Falha ao copiar {nome_arquivo_fisico} para storage/entregaveis: {e}')
            return None, 500

    return caminho, item['nome_arquivo']


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
