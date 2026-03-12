from flask import Blueprint, jsonify, request, send_file, render_template

web_bp = Blueprint('web', __name__)


@web_bp.get('/guia-paes')
def guia_paes():
    return render_template('guia-paes-sem-gluten.html')


@web_bp.get('/pay/<int:produto_id>')
def checkout(produto_id):
    from database import get_produto_disponivel_web
    produto = get_produto_disponivel_web(produto_id)
    if not produto:
        return 'Produto não encontrado', 404
    return render_template('checkout.html', produto=produto)


@web_bp.post('/api/v1/pix/gerar')
def pix_gerar():
    from web.checkout import gerar_pix
    url_base = request.url_root.rstrip('/')
    return jsonify(gerar_pix(
        request.get_json(force=True, silent=True) or {},
        url_base=url_base,
    ))


@web_bp.get('/api/v1/pix/pedido/<int:pedido_id>')
def pix_pedido(pedido_id):
    from database import get_pedido
    pedido = get_pedido(pedido_id)
    if not pedido:
        return jsonify({'error': 'não encontrado'}), 404
    return jsonify({'txid': pedido.get('numero_solicitacao_bb'), 'estado': pedido.get('estado_id')})


@web_bp.get('/api/v1/pix/status/<txid>')
def pix_status(txid):
    from web.checkout import verificar_pagamento
    return jsonify(verificar_pagamento(txid))


@web_bp.get('/api/v1/produto/pdf/<int:pedido_id>')
def servir_pdf(pedido_id):
    from web.checkout import entregar_pdf
    caminho, arquivo = entregar_pdf(pedido_id)
    if caminho is None:
        return jsonify({'error': 'Pagamento não confirmado'}), arquivo
    return send_file(caminho, as_attachment=True, download_name=arquivo)


@web_bp.get('/api/v1/produto/pdf/<int:pedido_id>/bonus')
def servir_pdf_bonus(pedido_id):
    from web.checkout import entregar_pdf
    caminho, arquivo = entregar_pdf(pedido_id, bonus=True)
    if caminho is None:
        return jsonify({'error': 'Pagamento não confirmado ou bônus não disponível'}), arquivo
    return send_file(caminho, as_attachment=True, download_name=arquivo)
