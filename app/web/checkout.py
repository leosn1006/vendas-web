"""
Serviço de Web Checkout — orquestra BB Pay e banco de dados.

Isolado de app.py para manter as rotas Flask como roteadores puros.
"""
import base64
import io
import logging
import os
import re
from datetime import datetime, timedelta

import qrcode as qrcode_lib

logger = logging.getLogger(__name__)


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
                          get_phone_number_id_produto)

    produto_id = int(body.get('produto_id', 1))
    produto = get_produto_disponivel_web(produto_id)
    _teste_produto = os.getenv(f'CHECKOUT_VALOR_TESTE_PRODUTO_{produto_id}')
    valor = float(_teste_produto or (produto.get('preco', 19.90) if produto else 19.90))
    numero_convenio = int(produto.get('numero_convenio_bb', 0)) if produto else 0
    phone_number_id = get_phone_number_id_produto(produto_id) or os.getenv('WHATSAPP_PHONE_NUMBER_ID', '')

    # Normaliza telefone para formato WhatsApp: DDI vem do frontend, fallback 55
    _ddi   = re.sub(r'\D', '', body.get('ddi', '55')) or '55'
    _phone = re.sub(r'\D', '', body.get('whatsapp', ''))
    if _phone and not _phone.startswith(_ddi):
        _phone = _ddi + _phone
    # Remove o 9º dígito de celular BR para compatibilidade com formato do webhook WhatsApp
    if len(_phone) == 13 and _phone[4] == '9':  # ex: 5561981163324 → 556181163324
        _phone = _phone[:4] + _phone[5:]

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
    Ao confirmar, dispara a task Celery que envia o ebook via WhatsApp.

    Retorna {'pago': bool} (ou {'pago': False, 'erro': True} em caso de falha).
    """
    from web.bb_pay import consultar_pagamentos
    from database import (get_pedido_by_solicitacao_bb, get_produto_disponivel_web,
                          confirmar_pagamento_web)
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
            confirmar_pagamento_web(
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
            import tasks
            tasks.enviar_email_entrega.delay(pedido['id'])
            if pedido.get('contact_phone'):
                tasks.fluxo_enviar_confirmacao_web.delay(pedido['id'])
        return {'pago': pago}
    except Exception as e:
        logger.error(f'[WEB-CHECKOUT] Erro ao verificar pagamento {txid}: {e}')
        return {'pago': False, 'erro': True}


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
