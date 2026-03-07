"""
Serviço de Web Checkout — orquestra BB Pay e banco de dados.

Isolado de app.py para manter as rotas Flask como roteadores puros.
"""
import base64
import io
import logging
import os

import qrcode as qrcode_lib

logger = logging.getLogger(__name__)


def _gerar_qrcode_base64(texto: str) -> str:
    img = qrcode_lib.make(texto)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def gerar_pix(body: dict) -> dict:
    """
    Cria um pedido_web e gera uma solicitação PIX no BB Pay.

    Retorna dict pronto para jsonify com:
      txid, qrcode_texto, url_solicitacao, valor, pedido_id
      (ou fallback=True com qrcode_texto = chave_pix_fallback)
    """
    from bb_pay import criar_solicitacao
    from database import (get_produto_web, criar_pedido_web,
                          atualizar_numero_solicitacao_pedido_web)

    produto_web_id = 1  # Guia Pães Sem Glúten
    produto = get_produto_web(produto_web_id)
    valor = float(os.getenv('CHECKOUT_VALOR_TESTE') or (produto.get('preco', 19.90) if produto else 19.90))
    numero_convenio = int(produto.get('numero_convenio', 0)) if produto else 0

    pedido_web_id = criar_pedido_web(
        remetente_id=str(produto_web_id),
        valor=valor,
        gclid=body.get('gclid', ''),
        phone_contact=body.get('whatsapp', ''),
        campaignid=body.get('campaignid', ''),
        adgroupid=body.get('adgroupid', ''),
        creative=body.get('creative', ''),
        matchtype=body.get('matchtype', ''),
        device=body.get('device', ''),
        placement=body.get('placement', ''),
        video_id=body.get('video_id', ''),
    )

    try:
        qr = criar_solicitacao(valor=valor, pedido_web_id=pedido_web_id,
                               numero_convenio=numero_convenio)
        atualizar_numero_solicitacao_pedido_web(pedido_web_id, str(qr['numero_solicitacao']))
        qrcode_b64 = _gerar_qrcode_base64(qr['qrcode_texto']) if qr['qrcode_texto'] else ''
        return {
            'txid':            str(qr['numero_solicitacao']),
            'qrcode_texto':    qr['qrcode_texto'],
            'qrcode_base64':   qrcode_b64,
            'url_solicitacao': qr['url_solicitacao'],
            'valor':           qr['valor'],
            'pedido_id':       pedido_web_id,
        }
    except Exception as e:
        logger.error(f'[WEB-CHECKOUT] Erro BB Pay ao gerar PIX: {e}')
        return {
            'txid': None, 'qrcode_texto': '', 'qrcode_base64': '',
            'url_solicitacao': None,
            'valor': valor, 'pedido_id': pedido_web_id,
            'fallback': True,
        }


def verificar_pagamento(txid: str) -> dict:
    """
    Consulta o BB Pay pelo numeroSolicitacao e registra o pagamento se confirmado.

    Retorna {'pago': bool} (ou {'pago': False, 'erro': True} em caso de falha).
    """
    from bb_pay import consultar_pagamentos
    from database import (get_pedido_web_by_numero_solicitacao, get_produto_web,
                          atualizar_estado_pedido_web, criar_pagamento_web)
    try:
        pedido = get_pedido_web_by_numero_solicitacao(txid)
        if not pedido:
            return {'pago': False}

        produto = get_produto_web(pedido['remetente_id'])
        numero_convenio = int(produto['numero_convenio']) if produto else 0

        data = consultar_pagamentos(int(txid), numero_convenio)
        pago = data['pago']
        if pago and pedido['estado'] != 0:
            pag = data['pagamento']
            atualizar_estado_pedido_web(pedido['id'], 0)
            criar_pagamento_web(
                pedido_web_id=pedido['id'],
                valor=pag.get('valorOriginalPagamento', pedido['valor']),
                tipo_pagamento='Pix',
                nome_pagador=pag.get('nomePagador', ''),
                id_pagador=pag.get('numeroDocumentoPagador', ''),
                e2e_pix=pag.get('e2eId', ''),
                valor_tarifa=pag.get('valorTarifaRecebedor'),
            )
        return {'pago': pago}
    except Exception as e:
        logger.error(f'[WEB-CHECKOUT] Erro ao verificar pagamento {txid}: {e}')
        return {'pago': False, 'erro': True}


def entregar_pdf(pedido_id: int, bonus: bool = False):
    """
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
    caminho = os.path.join(os.path.dirname(__file__), '..', 'static', 'arquivos', arquivo)
    return caminho, arquivo
