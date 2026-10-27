import re

from flask import Blueprint, jsonify, request, send_file, render_template, make_response, redirect

web_bp = Blueprint('web', __name__)


@web_bp.get('/guia-paes')
def guia_paes():
    return render_template('guia-paes-sem-gluten.html')


def _redirecionar_produto_antigo(produto_id, v2=False):
    """Link antigo de um produto que virou plano de outro (ex.: /pay/16?pedido=X → /pay/12?pedido=X&plano=completo).
    Mantém pedido, ref e oferta. None = não há redirecionamento (a rota responde 404 como antes)."""
    from database import get_redirecionamento_produto
    from web.links import link_checkout
    destino = get_redirecionamento_produto(produto_id)
    if not destino:
        return None
    plano = {'slug': destino['plano_slug'], 'padrao': destino['plano_padrao']}
    a = request.args
    return redirect(link_checkout(destino['produto_destino_id'], plano, v2=v2, pedido=a.get('pedido'),
                                  ref=a.get('ref'), oferta=a.get('oferta')))


def _plano_da_pagina(produto_id):
    """O plano que esta página vende: ?plano=<slug> ou, sem ele, o padrão do produto (None = não está à
    venda: plano inexistente, inativo ou sem item principal)."""
    from database import get_plano_venda
    return get_plano_venda(produto_id, request.args.get('plano') or None)


def _oferta_do_link(produto_id, plano):
    """(token, desconto) do link de oferta (?oferta=, popup/Estante — ver web/oferta.py), ou (None, 0).
    O desconto aqui é só para MOSTRAR no checkout; quem aplica no valor cobrado é gerar_pix/gerar_cartao,
    que validam o token de novo."""
    from web.oferta import desconto_da_oferta
    from database import preco_cobrado_plano
    token = request.args.get('oferta') or None
    if not token:
        return None, 0.0
    desconto = desconto_da_oferta(token, plano, preco_cobrado_plano(produto_id, plano))
    return (token, desconto) if desconto > 0 else (None, 0.0)


def _sem_musica_volta_para_previa(produto_id, plano):
    """Plano do produto Música: o checkout só abre com a música do link (?musica=<token>, vindo da prévia).
    Sem ela (ou já comprada, ou não pronta), volta para a prévia/landing. None = pode seguir. O retorno do
    BB Pay (?pedido=) segue: aquele pedido já tem a música gravada."""
    from musica.dominio.recursos import plano_vende_musica   # sem dependências: não derruba o checkout dos e-books
    if not plano_vende_musica(plano) or request.args.get('pedido'):
        return None
    from musica.integracao import Recusa, conferir_para_checkout
    token = request.args.get('musica') or ''
    try:
        conferir_para_checkout(token, produto_id)
    except Recusa:
        return redirect(f'/musica/p/{token}' if re.fullmatch(r'[0-9a-f]{32}', token) else '/musica/')
    return None


def _retomar_sem_perder_oferta(pedido_id, oferta, plano):
    """O cookie aponta para um pedido já iniciado deste produto; retomar reabre o PIX/cartão dele.
    Não retoma (segue para um pedido novo) quando aquele pedido é de OUTRO plano (ex.: comprou o Básico
    e agora abriu o Completo), quando a cliente chegou agora por uma OFERTA (popup/Estante) e aquele
    pedido não tem desconto (e não foi pago), ou — plano de Música — quando aquele pedido é de OUTRA música
    (a do link é outra): só retoma o PIX da mesma música, para ela não ficar com dois QR válidos."""
    if pedido_id is None:
        return None
    from musica.dominio.recursos import plano_vende_musica
    if plano_vende_musica(plano):
        # O pedido vem do cookie deste navegador (é dela): pode olhar a música dele.
        from musica.integracao import token_do_pedido
        if not request.args.get('musica') or token_do_pedido(pedido_id) != request.args.get('musica'):
            return None
    from database import get_pedido
    from web.checkout import pedido_do_plano
    pedido = get_pedido(pedido_id) or {}
    if not pedido or not pedido_do_plano(pedido, plano):
        return None
    if not oferta:
        return pedido_id
    # Só abandona pedido sem cobrança em andamento: 1001 (só identidade), 1002 (PIX gerado e não pago —
    # o novo leva o desconto), 1006/1007 (cartão negado / não processado). Nunca 1005 (autorização de
    # cartão em curso ou em timeout: pode já ter sido cobrado) nem 1000 (pago).
    if pedido.get('estado_id') in (1001, 1002, 1006, 1007) and float(pedido.get('desconto') or 0) <= 0:
        return None
    return pedido_id


@web_bp.get('/pay/<int:produto_id>')
def checkout(produto_id):
    from database import get_produto_disponivel_web, itens_do_plano, get_config_cartao_produto
    from web.checkout import (rastrear_visita_funil, get_pedido_finalizado_via_cookie,
                               COOKIE_MAX_AGE_FUNIL)
    produto = get_produto_disponivel_web(produto_id)
    if not produto:
        return _redirecionar_produto_antigo(produto_id) or ('Produto não encontrado', 404)

    plano = _plano_da_pagina(produto_id)
    if not plano:
        return 'Produto não encontrado', 404
    voltar = _sem_musica_volta_para_previa(produto_id, plano)
    if voltar:
        return voltar

    config_cartao = get_config_cartao_produto(produto_id)  # None = aba Cartão não aparece
    oferta, desconto = _oferta_do_link(produto_id, plano)

    # Retorno do BB Pay / link salvo (?pedido=) é um caso à parte, já tratado no JS da própria
    # página (resume o pedido existente) — não faz sentido criar/reaproveitar um pedido 1003
    # novo nesse caso.
    pedido_id_inicial = None
    if not request.args.get('pedido'):
        pedido_id_retomar = _retomar_sem_perder_oferta(get_pedido_finalizado_via_cookie(request, produto_id), oferta, plano)
        if pedido_id_retomar is not None:
            # Cliente já saiu de 1003/1004 nessa visita (pago, aguardando identidade, ou
            # aguardando pix) — reaproveita o fluxo já existente do link de retorno do BB Pay
            # (?pedido=<id>) em vez de duplicar em Python a lógica pago→downloads /
            # pendente→retomar pix, que o JS de checkout.html já sabe fazer.
            from web.links import link_checkout
            resp = redirect(link_checkout(produto_id, plano, pedido=pedido_id_retomar, oferta=oferta,
                                          musica=request.args.get('musica')))
            resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id_retomar), max_age=COOKIE_MAX_AGE_FUNIL)
            return resp
        pedido_id_inicial = rastrear_visita_funil(request, produto_id, estado_novo=1003)

    prefill = _prefill_musica(plano)
    resp = make_response(render_template(
        'checkout.html',
        produto=produto,
        plano=plano,
        bonus=itens_do_plano(plano, 'bonus'),
        bumps=itens_do_plano(plano, 'bump'),
        pedido_id_inicial=pedido_id_inicial,
        config_cartao=config_cartao,
        oferta=oferta,
        desconto=desconto,
        prefill=prefill,
        **_aparencia_checkout(produto, plano, email_do_quiz=prefill.get('email') or ''),
    ))
    if pedido_id_inicial is not None:
        resp.set_cookie(f'pedido_web_{produto_id}', str(pedido_id_inicial), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp


def _prefill_musica(plano):
    """Produto Música: o e-mail e o WhatsApp que ela já deu no quiz (a música do link ?musica=), para não digitar
    de novo.
    Outros produtos não são afetados."""
    from musica.dominio.recursos import plano_vende_musica
    token = request.args.get('musica') or ''
    if not plano_vende_musica(plano) or not re.fullmatch(r'[0-9a-f]{32}', token):
        return {}
    import logging
    try:   # lembretes: esta música chegou no checkout (uma falha aqui não pode tirar o preenchimento)
        from musica.integracao import checkout_aberto
        checkout_aberto(token)
    except Exception as e:
        logging.getLogger(__name__).error(f"[WEB-CHECKOUT] Erro ao marcar o checkout aberto da música: {e}")
    try:
        from musica.integracao import dados_para_checkout
        return dados_para_checkout(token)
    except Exception as e:
        logging.getLogger(__name__).error(f"[WEB-CHECKOUT] Erro ao preencher o checkout da música: {e}")
        return {}


def _aparencia_checkout(produto, plano, email_do_quiz=''):
    """O que muda a cara do checkout por produto/plano (migration 093): o tema (cores da landing), o texto do
    botão, a empresa do rodapé e se o e-mail veio do quiz da Música (aí sem "Confirme seu e-mail" — ele já foi
    digitado lá; se ela trocar, a confirmação volta no JS)."""
    from web.checkout import formatar_cnpj
    from web.tema_checkout import tema_checkout
    try:
        from database import get_empresa_produto
        empresa = get_empresa_produto(produto)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[WEB-CHECKOUT] Erro ao buscar a empresa do produto {produto.get('id')}: {e}")
        empresa = {}
    return {
        'tema': tema_checkout(produto),
        'texto_botao': plano.get('checkout_texto_botao') or 'FINALIZAR COMPRA',
        'email_do_quiz': bool(email_do_quiz),
        'empresa': {'razao_social': empresa.get('razao_social') or '', 'cnpj': formatar_cnpj(empresa.get('cnpj'))},
    }


@web_bp.get('/pay2/<int:produto_id>')
def checkout_v2(produto_id):
    """Variante v2 do checkout (piloto de cross-sell), ver plano peaceful-seeking-pizza.md.
    Espelha /pay/<produto_id>, com três diferenças: (1) pré-preenche nome/e-mail/whatsapp a
    partir do pedido de origem (?ref=<guid>, a estante de onde veio o clique em "Comprar"),
    editável no formulário; (2) marca o pedido rascunho com variante_checkout='v2'; (3) quando
    vem da estante (ref conhecido), tira dos bônus/bumps os e-books que esse cliente já possui
    — não faz sentido oferecer de bônus/order bump algo que ele já tem. Sem ref (cliente
    chegando pelo funil de anúncio, ainda sem identidade conhecida), bônus/bumps aparecem
    completos como no checkout v1 — não tem como filtrar o que não se sabe de quem é. Usa um
    prefixo de cookie próprio (pedido_web_v2_<produto_id>) pra não colidir com o rascunho do
    checkout v1 do mesmo produto."""
    from database import (get_produto_disponivel_web, itens_do_plano,
                          get_config_cartao_produto, marcar_variante_pedido,
                          gravar_vinculo_pedido)
    from web.checkout import (rastrear_visita_funil, get_pedido_finalizado_via_cookie,
                               COOKIE_MAX_AGE_FUNIL, listar_itens_ebook_do_cliente,
                               resolver_pedido_por_guid)
    produto = get_produto_disponivel_web(produto_id)
    if not produto:
        return _redirecionar_produto_antigo(produto_id, v2=True) or ('Produto não encontrado', 404)

    plano = _plano_da_pagina(produto_id)
    if not plano:
        return 'Produto não encontrado', 404
    voltar = _sem_musica_volta_para_previa(produto_id, plano)
    if voltar:
        return voltar

    config_cartao = get_config_cartao_produto(produto_id)
    oferta, desconto = _oferta_do_link(produto_id, plano)

    prefill = {}
    bonus = itens_do_plano(plano, 'bonus')
    bumps = itens_do_plano(plano, 'bump')
    pedido_origem_id = None
    ref_guid = request.args.get('ref')
    if ref_guid:
        # resolver_pedido_por_guid (não get_pedido_by_guid puro) — mesmo gate de acesso usado
        # por /pedido/<guid> e /pedido2/<guid>: só segue se o pedido de origem já pode
        # legitimamente ser visto (pago/entregue). Sem isso, um guid que já circulou antes do
        # pagamento (ex: link da Estante mandado ainda na introdução do WhatsApp) exporia
        # nome/e-mail/telefone de terceiro pré-preenchidos neste formulário.
        pedido_origem, _, erro_origem = resolver_pedido_por_guid(ref_guid)
        if pedido_origem and not erro_origem:
            pedido_origem_id = pedido_origem['id']
            prefill = {
                'nome': pedido_origem.get('contact_name') or '',
                'email': pedido_origem.get('email') or '',
                'whatsapp': pedido_origem.get('contact_phone') or '',
            }
            itens_possuidos = listar_itens_ebook_do_cliente(pedido_origem)
            # not item.get('bloqueado'): um bônus do WhatsApp ainda não pago não conta como
            # "já possuído" — senão um item legítimo de bônus/bump em outro produto some do
            # cross-sell por engano (ver achado de code review).
            possuidos = {
                item['entregavel_id'] for item in itens_possuidos
                if item.get('entregavel_id') and not item.get('bloqueado')
            }
            bonus = [b for b in bonus if b['entregavel_id'] not in possuidos]
            bumps = [b for b in bumps if b['entregavel_id'] not in possuidos]

    pedido_id_inicial = None
    if not request.args.get('pedido'):
        pedido_id_retomar = _retomar_sem_perder_oferta(
            get_pedido_finalizado_via_cookie(request, produto_id, cookie_prefixo='pedido_web_v2'), oferta, plano)
        if pedido_id_retomar is not None:
            from web.links import link_checkout
            resp = redirect(link_checkout(produto_id, plano, v2=True, pedido=pedido_id_retomar, ref=ref_guid,
                                          oferta=oferta, musica=request.args.get('musica')))
            resp.set_cookie(f'pedido_web_v2_{produto_id}', str(pedido_id_retomar), max_age=COOKIE_MAX_AGE_FUNIL)
            return resp
        pedido_id_inicial = rastrear_visita_funil(request, produto_id, estado_novo=1003, cookie_prefixo='pedido_web_v2')
        marcar_variante_pedido(pedido_id_inicial, 'v2')
        if pedido_origem_id is not None:
            try:
                gravar_vinculo_pedido(pedido_origem_id, pedido_id_inicial)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    f"[ESTANTE] Erro ao gravar vínculo pedido {pedido_origem_id}→{pedido_id_inicial}: {e}"
                )

    prefill_musica = _prefill_musica(plano)
    prefill = {**prefill_musica, **{k: v for k, v in prefill.items() if v}}
    resp = make_response(render_template(
        'checkout-2.html',
        produto=produto,
        plano=plano,
        bonus=bonus,
        bumps=bumps,
        pedido_id_inicial=pedido_id_inicial,
        config_cartao=config_cartao,
        prefill=prefill,
        oferta=oferta,
        desconto=desconto,
        # O e-mail do quiz só dispensa a confirmação se continuou o do formulário (a Estante não o sobrescreveu).
        **_aparencia_checkout(produto, plano, email_do_quiz=(
            prefill_musica.get('email') if prefill.get('email') == prefill_musica.get('email') else '')),
    ))
    if pedido_id_inicial is not None:
        resp.set_cookie(f'pedido_web_v2_{produto_id}', str(pedido_id_inicial), max_age=COOKIE_MAX_AGE_FUNIL)
    return resp


@web_bp.post('/api/v1/quiz/progresso')
def quiz_progresso():
    """Recebe (via navigator.sendBeacon) a etapa que a visita alcançou num quiz de página de
    vendas. O pedido vem do cookie pedido_web_<produto_id> gravado pela própria landing — nunca
    do corpo — e só conta enquanto o pedido ainda é rascunho (1004/1003) daquele produto. Falha
    aqui nunca pode atrapalhar a venda: qualquer erro só é logado e a resposta é sempre 204."""
    import re
    import logging
    from database import get_pedido_nao_finalizado, registrar_progresso_quiz

    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return '', 204
    try:
        produto_id = int(body.get('produto_id'))
        etapa = int(body.get('etapa'))
    except (TypeError, ValueError):
        return '', 204
    pagina = str(body.get('pagina') or '')
    etapa_nome = str(body.get('nome') or '')[:60]
    pedido_id_cookie = request.cookies.get(f'pedido_web_{produto_id}', '')
    if not (0 <= etapa <= 99 and re.fullmatch(r'[a-z0-9-]{1,40}', pagina) and pedido_id_cookie.isdigit()):
        return '', 204

    try:
        if get_pedido_nao_finalizado(int(pedido_id_cookie), produto_id):
            registrar_progresso_quiz(int(pedido_id_cookie), pagina, etapa, etapa_nome)
    except Exception as e:
        logging.getLogger(__name__).error(f"[QUIZ] Erro ao registrar progresso do pedido #{pedido_id_cookie}: {e}")
    return '', 204


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
    from web.checkout import resolver_pedido_por_guid, listar_itens_ebook_do_cliente
    from database import registrar_visualizacao_estante

    pedido, _, erro = resolver_pedido_por_guid(guid)
    if erro == 'nao_encontrado':
        return render_template('pedido_indisponivel.html', motivo='nao_encontrado'), 404
    if erro == 'aguardando_pagamento':
        return render_template('pedido_indisponivel.html', motivo='aguardando_pagamento', canal='web', pedido=pedido)
    if erro == 'ainda_nao_entregue':
        return render_template('pedido_indisponivel.html', motivo='ainda_nao_entregue', pedido=pedido)

    itens = listar_itens_ebook_do_cliente(pedido)
    primeiro_nome = (pedido.get('contact_name') or '').strip().split(' ')[0] or 'cliente'

    try:
        registrar_visualizacao_estante(pedido['id'], 'v1')
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[ESTANTE] Erro ao registrar visualização v1 do pedido #{pedido['id']}: {e}")

    return render_template('pedido.html', primeiro_nome=primeiro_nome, itens=itens)


@web_bp.get('/pedido2/<guid>')
def pedido_publico_v2(guid):
    """Variante v2 da estante (piloto de cross-sell), ver plano peaceful-seeking-pizza.md.
    Espelha /pedido/<guid> e reaproveita a mesma resolução de acesso — só acrescenta a lista
    de produtos que o cliente ainda não tem e o registro de visualização com variante='v2'."""
    from web.checkout import resolver_pedido_por_guid, listar_itens_ebook_do_cliente
    from database import registrar_visualizacao_estante, listar_produtos_cross_sell_cliente

    pedido, _, erro = resolver_pedido_por_guid(guid)
    if erro == 'nao_encontrado':
        return render_template('pedido_indisponivel.html', motivo='nao_encontrado'), 404
    if erro == 'aguardando_pagamento':
        return render_template('pedido_indisponivel.html', motivo='aguardando_pagamento', canal='web', pedido=pedido)
    if erro == 'ainda_nao_entregue':
        return render_template('pedido_indisponivel.html', motivo='ainda_nao_entregue', pedido=pedido)

    itens = listar_itens_ebook_do_cliente(pedido)
    # not item.get('bloqueado'): um bônus do WhatsApp ainda não pago não conta como "já
    # possuído" pro cross-sell — senão um produto legítimo some da lista por engano (ver
    # mesma correção em checkout_v2).
    possuidos = {
        item['entregavel_id'] for item in itens
        if item.get('entregavel_id') and not item.get('bloqueado')
    }
    cross_sell = listar_produtos_cross_sell_cliente(possuidos)
    # Desconto de oferta do plano também nos e-books do cross-sell: preço com desconto + token no link.
    try:
        from web.oferta import aplicar_na_vitrine
        cross_sell = [aplicar_na_vitrine(dict(c)) for c in cross_sell]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[ESTANTE] Erro ao aplicar ofertas no cross-sell: {e}")
    primeiro_nome = (pedido.get('contact_name') or '').strip().split(' ')[0] or 'cliente'

    try:
        registrar_visualizacao_estante(pedido['id'], 'v2')
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[ESTANTE] Erro ao registrar visualização v2 do pedido #{pedido['id']}: {e}")

    # "Meus apps": apps (ex.: App Fatias) da cliente deste pedido. Extra da página — não pode derrubá-la.
    try:
        from apps._nucleo.estante import apps_da_estante
        meus_apps, apps_ofertas = apps_da_estante(pedido)
        cross_sell = apps_ofertas + cross_sell
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[ESTANTE] Erro ao listar apps do pedido #{pedido['id']}: {e}")
        meus_apps = []

    # "Minha música": compra do produto Música (o card leva à área da música). Também não pode derrubar a página.
    minha_musica = None
    try:
        from musica.integracao import musica_do_pedido_pago
        minha_musica = musica_do_pedido_pago(pedido)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[ESTANTE] Erro ao buscar a música do pedido #{pedido['id']}: {e}")

    # Link de cada card (e-book ou app): o checkout v2 do plano, com a Estante de origem e o token da oferta.
    from web.links import link_checkout
    for c in cross_sell:
        c['href'] = link_checkout(c['produto_id'], {'slug': c['plano_slug'], 'padrao': c['plano_padrao']},
                                  v2=True, ref=guid, oferta=c.get('oferta'))

    return render_template('pedido-2.html', primeiro_nome=primeiro_nome, itens=itens,
                            cross_sell=cross_sell, guid=guid, meus_apps=meus_apps, minha_musica=minha_musica)


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

    # A tela de leitura é uma única rota pras duas versões da estante — o link de origem
    # (pedido-2.html) marca ?estante=v2 pra "← Meus livros" voltar pra /pedido2, não /pedido.
    # Sem o parâmetro (link antigo, favorito salvo, e-mail), volta pra v1 como sempre foi.
    voltar_para = f'/pedido2/{guid}' if request.args.get('estante') == 'v2' else f'/pedido/{guid}'

    return render_template('pedido_leitor.html', guid=guid, item=item, voltar_para=voltar_para)


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
