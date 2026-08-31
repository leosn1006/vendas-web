from flask import Blueprint, jsonify, request, send_file, render_template, make_response, redirect

web_bp = Blueprint('web', __name__)


@web_bp.get('/guia-paes')
def guia_paes():
    return render_template('guia-paes-sem-gluten.html')


@web_bp.get('/pay/<int:produto_id>')
def checkout(produto_id):
    from database import (get_produto_disponivel_web, get_ebook_principal_produto,
                          listar_ebooks_bonus_produto, listar_ebooks_bump_produto,
                          get_config_cartao_produto)
    from web.checkout import (rastrear_visita_funil, get_pedido_finalizado_via_cookie,
                               COOKIE_MAX_AGE_FUNIL)
    produto = get_produto_disponivel_web(produto_id)
    if not produto:
        return 'Produto não encontrado', 404

    ebook_principal = get_ebook_principal_produto(produto_id)
    if not ebook_principal:
        return 'Produto não encontrado', 404

    config_cartao = get_config_cartao_produto(produto_id)  # None = aba Cartão não aparece

    # Retorno do BB Pay / link salvo (?pedido=) é um caso à parte, já tratado no JS da própria
    # página (resume o pedido existente) — não faz sentido criar/reaproveitar um pedido 1003
    # novo nesse caso.
    pedido_id_inicial = None
    if not request.args.get('pedido'):
        pedido_id_retomar = get_pedido_finalizado_via_cookie(request, produto_id)
        if pedido_id_retomar is not None:
            # Cliente já saiu de 1003/1004 nessa visita (pago, aguardando identidade, ou
            # aguardando pix) — reaproveita o fluxo já existente do link de retorno do BB Pay
            # (?pedido=<id>) em vez de duplicar em Python a lógica pago→downloads /
            # pendente→retomar pix, que o JS de checkout.html já sabe fazer.
            resp = redirect(f'/pay/{produto_id}?pedido={pedido_id_retomar}')
            resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id_retomar), max_age=COOKIE_MAX_AGE_FUNIL)
            return resp
        pedido_id_inicial = rastrear_visita_funil(request, produto_id, estado_novo=1003)

    resp = make_response(render_template(
        'checkout.html',
        produto=produto,
        ebook_principal=ebook_principal,
        bonus=listar_ebooks_bonus_produto(produto_id),
        bumps=listar_ebooks_bump_produto(produto_id),
        pedido_id_inicial=pedido_id_inicial,
        config_cartao=config_cartao,
    ))
    if pedido_id_inicial is not None:
        resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id_inicial), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp


@web_bp.post('/api/v1/pix/gerar')
def pix_gerar():
    from web.checkout import gerar_pix
    url_base = request.url_root.rstrip('/')
    dns_origem = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return jsonify(gerar_pix(
        request.get_json(force=True, silent=True) or {},
        url_base=url_base,
        dns_origem=dns_origem,
    ))


@web_bp.post('/api/v1/cartao/gerar')
def cartao_gerar():
    from web.checkout import gerar_cartao
    url_base = request.url_root.rstrip('/')
    dns_origem = (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()
    return jsonify(gerar_cartao(
        request.get_json(force=True, silent=True) or {},
        url_base=url_base,
        dns_origem=dns_origem,
    ))


@web_bp.get('/api/v1/cartao/parcelas/<int:produto_id>')
def cartao_parcelas(produto_id):
    from database import get_config_cartao_produto
    from web.parcelamento_cartao import gerar_opcoes_parcelamento
    config_cartao = get_config_cartao_produto(produto_id)
    if not config_cartao:
        return jsonify({'opcoes': []}), 404
    try:
        valor = float(request.args.get('valor', 0))
    except ValueError:
        valor = 0.0
    return jsonify({'opcoes': gerar_opcoes_parcelamento(valor, config_cartao)})


@web_bp.get('/api/v1/cartao/bandeira')
def cartao_bandeira():
    from web.bandeira_bin import resolver_bandeira
    bin_numero = request.args.get('bin', '')
    return jsonify({'bandeira': resolver_bandeira(bin_numero)})


@web_bp.get('/api/v1/pix/pedido/<int:pedido_id>')
def pix_pedido(pedido_id):
    from database import get_pedido, listar_itens_pedido, garantir_guid_pedido
    from web.checkout import _gerar_qrcode_base64
    pedido = get_pedido(pedido_id)
    if not pedido:
        return jsonify({'error': 'não encontrado'}), 404
    # pedido_itens já existe desde a criação do lead (antes do pagamento), então devolvemos
    # a lista sempre — permite mostrar o resumo do que está sendo pago mesmo antes de confirmar.
    # qrcode_texto/qrcode_base64/url_bbpay são reconstruídos a partir do que foi salvo em
    # gerar_pix() — necessário pra tela de retomada (?pedido=<id>) conseguir reexibir o mesmo
    # PIX, e não só o card vazio com "Carregando...".
    qrcode_texto = pedido.get('qr_code_pix') or ''
    pago = pedido.get('estado_id') == 1000
    resposta = {
        'txid': pedido.get('numero_solicitacao_bb'),
        'estado': pedido.get('estado_id'),
        'pago': pago,
        # garantir_guid_pedido cobre pedidos web criados antes da migration 062 (guid NULL) —
        # sem isso, reabrir o link de um pedido antigo já pago mandaria pra "/pedido/null".
        'guid': garantir_guid_pedido(pedido_id) if pago else pedido.get('guid'),
        'qrcode_texto': qrcode_texto,
        'qrcode_base64': _gerar_qrcode_base64(qrcode_texto) if qrcode_texto else '',
        'url_bbpay': pedido.get('url_bbpay') or '',
        'itens': [
            {'id': item['id'], 'tipo': item['tipo'], 'nome': item['nome'], 'valor': float(item['valor'])}
            for item in listar_itens_pedido(pedido_id)
        ],
    }
    return jsonify(resposta)


@web_bp.get('/api/v1/pix/status/<txid>')
def pix_status(txid):
    from web.checkout import verificar_pagamento
    return jsonify(verificar_pagamento(txid))


@web_bp.get('/api/v1/pedido/<int:pedido_id>/itens/<int:item_id>/download')
def baixar_item(pedido_id, item_id):
    from web.checkout import baixar_item_pedido
    caminho, arquivo = baixar_item_pedido(pedido_id, item_id)
    if caminho is None:
        return jsonify({'error': 'Pagamento não confirmado ou item não encontrado'}), arquivo
    return send_file(caminho, as_attachment=True, download_name=arquivo)


@web_bp.get('/pedido/<guid>')
def pedido_publico(guid):
    from web.checkout import resolver_pedido_por_guid, separar_itens_visiveis
    from database import listar_itens_pedido_ebook

    pedido, _, erro = resolver_pedido_por_guid(guid)
    if erro == 'nao_encontrado':
        return render_template('pedido_indisponivel.html', motivo='nao_encontrado'), 404
    if erro == 'aguardando_pagamento':
        return render_template('pedido_indisponivel.html', motivo='aguardando_pagamento', canal='web', pedido=pedido)
    if erro == 'ainda_nao_entregue':
        return render_template('pedido_indisponivel.html', motivo='ainda_nao_entregue', pedido=pedido)

    itens = listar_itens_pedido_ebook(pedido['id'])
    hero, outros = separar_itens_visiveis(pedido, itens)
    primeiro_nome = (pedido.get('contact_name') or '').strip().split(' ')[0] or 'cliente'

    return render_template('pedido.html', guid=guid, pedido=pedido,
                           primeiro_nome=primeiro_nome, hero=hero, outros=outros)


@web_bp.get('/pedido/<guid>/ler/<int:item_id>')
def pedido_leitor(guid, item_id):
    from web.checkout import resolver_pedido_por_guid

    pedido, item, erro = resolver_pedido_por_guid(guid, item_id=item_id)
    if erro in ('nao_encontrado', 'item_invalido'):
        return render_template('pedido_indisponivel.html', motivo='nao_encontrado'), 404
    if erro == 'aguardando_pagamento':
        canal = 'web' if pedido['estado_id'] >= 1000 else 'whatsapp'
        return render_template('pedido_indisponivel.html', motivo='aguardando_pagamento', canal=canal, pedido=pedido)
    if erro == 'ainda_nao_entregue':
        return render_template('pedido_indisponivel.html', motivo='ainda_nao_entregue', pedido=pedido)

    return render_template('pedido_leitor.html', guid=guid, item=item)


@web_bp.get('/pedido/<guid>/arquivo/<int:item_id>')
def pedido_arquivo(guid, item_id):
    import os
    from web.checkout import resolver_pedido_por_guid, _resolver_caminho_entregavel

    pedido, item, erro = resolver_pedido_por_guid(guid, item_id=item_id)
    if erro:
        return jsonify({'error': 'Pedido ou item indisponível'}), 404

    nome_arquivo_fisico = os.path.basename(item['path_arquivo'])
    caminho, erro_arquivo = _resolver_caminho_entregavel(nome_arquivo_fisico)
    if erro_arquivo:
        return jsonify({'error': 'Arquivo indisponível'}), erro_arquivo

    inline = request.args.get('download') != '1'
    return send_file(caminho, mimetype='application/pdf',
                     as_attachment=not inline, download_name=item['nome_arquivo'])


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
