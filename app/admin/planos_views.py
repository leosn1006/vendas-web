"""Admin do que se vende: catálogo de entregáveis (e-book ou app) e planos de cada produto.

Produto (campanha, ISBN, NF-e) → planos (Básico, Completo, Renovação...: nome, preço, desconto de
oferta) → itens do plano (entregável + papel principal/bônus/order bump). Ver docs/PLANOS.md.
"""
import logging
import math
import re

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from admin import admin_bp
from admin.auth import requer_admin, requer_login
from database import db

logger = logging.getLogger(__name__)

PAPEIS = ('principal', 'bonus', 'bump')
_SLUG_PLANO = re.compile(r'[a-z0-9-]{1,30}')


def _apps():
    from apps import APPS
    return APPS


def _recursos_musica():
    from musica.dominio.recursos import RECURSOS
    return RECURSOS


def _so_no_site(item):
    """Item que não vai no plano padrão de produto com WhatsApp (que entrega antes de pagar): app e música
    (a música nasce no quiz do site)."""
    return item['tipo'] in ('app', 'musica')


def _numero(valor, padrao=0.0):
    """Número digitado no admin (aceita vírgula); ValueError se não for um número finito."""
    texto = str(valor if valor not in (None, '') else padrao).replace(',', '.')
    numero = float(texto)
    if not math.isfinite(numero):
        raise ValueError(texto)
    return round(numero, 2)


def _imagem(valor):
    from admin.views import _nome_arquivo_imagem
    return _nome_arquivo_imagem(valor)


def _arquivos(subdir):
    from admin.views import _listar_arquivos
    return _listar_arquivos(subdir)


def _produto_ou_none(produto_id):
    from admin.views import _get_produto_or_redirect
    return _get_produto_or_redirect(produto_id)


# ============================================================ catálogo de entregáveis

@admin_bp.route('/entregaveis')
@requer_login
def listar_entregaveis_view():
    from database import listar_entregaveis
    return render_template('admin/entregaveis.html', entregaveis=listar_entregaveis(), apps=_apps(),
                           recursos=_recursos_musica(),
                           pdfs=_arquivos('arquivos'), imagens=_arquivos('images'))


def _dados_entregavel(form):
    """(dados, erro) do formulário de entregável."""
    tipo = form.get('tipo') if form.get('tipo') in ('ebook', 'app', 'musica') else 'ebook'
    dados = {
        'tipo': tipo,
        'nome_venda': (form.get('nome_venda') or '').strip(),
        'descricao': (form.get('descricao') or '').strip(),
        'imagem_grande': _imagem(form.get('imagem_grande')),
        'imagem_pequena': _imagem(form.get('imagem_pequena')),
        'path_arquivo': None, 'nome_arquivo': None, 'app_slug': None, 'recurso': None,
    }
    if not dados['nome_venda']:
        return dados, 'Informe o nome de venda.'
    if tipo == 'ebook':
        dados['path_arquivo'] = (form.get('path_arquivo') or '').strip()
        if not dados['path_arquivo']:
            return dados, 'Escolha o arquivo do e-book.'
        dados['nome_arquivo'] = (form.get('nome_arquivo') or '').strip() or dados['path_arquivo']
    elif tipo == 'musica':
        dados['recurso'] = form.get('recurso') or ''
        if dados['recurso'] not in _recursos_musica():
            return dados, 'Escolha o que o item de música libera.'
    else:
        dados['app_slug'] = form.get('app_slug') or ''
        dados['imagem_grande'] = dados['imagem_pequena'] = None  # app: a capa vem do plano
        if dados['app_slug'] not in _apps():
            return dados, 'Escolha o app.'
    return dados, None


@admin_bp.route('/entregaveis/adicionar', methods=['POST'])
@requer_admin
def adicionar_entregavel_view():
    from database import salvar_entregavel
    dados, erro = _dados_entregavel(request.form)
    if erro:
        flash(erro, 'warning')
        return redirect(url_for('admin.listar_entregaveis_view'))
    try:
        salvar_entregavel(None, **dados)
        flash('Item adicionado ao catálogo!', 'success')
        logger.info(f"[ADMIN] ✅ Entregável '{dados['nome_venda']}' ({dados['tipo']}) adicionado por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao adicionar entregável: {e}")
        flash(f'Erro ao adicionar: {e}', 'danger')
    return redirect(url_for('admin.listar_entregaveis_view'))


@admin_bp.route('/entregaveis/<int:entregavel_id>/editar', methods=['GET', 'POST'])
@requer_admin
def editar_entregavel(entregavel_id):
    from database import get_entregavel, salvar_entregavel
    entregavel = get_entregavel(entregavel_id)
    if not entregavel:
        flash('Item não encontrado no catálogo.', 'danger')
        return redirect(url_for('admin.listar_entregaveis_view'))
    if request.method == 'POST':
        form = request.form.to_dict()
        form['tipo'] = entregavel['tipo']  # o tipo não muda: e-book vendido não vira app
        if entregavel['tipo'] == 'musica':
            form['recurso'] = entregavel['recurso']  # nem o recurso: é por ele que o pedido pago é liberado
        dados, erro = _dados_entregavel(form)
        if erro:
            flash(erro, 'warning')
        else:
            try:
                salvar_entregavel(entregavel_id, **dados)
                flash('Item atualizado!', 'success')
                logger.info(f"[ADMIN] ✅ Entregável #{entregavel_id} atualizado por {current_user.email}")
                return redirect(url_for('admin.listar_entregaveis_view'))
            except Exception as e:
                logger.error(f"[ADMIN] ❌ Erro ao atualizar entregável: {e}")
                flash(f'Erro ao salvar: {e}', 'danger')
    return render_template('admin/entregavel_editar.html', entregavel=entregavel, apps=_apps(),
                           recursos=_recursos_musica(),
                           pdfs=_arquivos('arquivos'), imagens=_arquivos('images'))


@admin_bp.route('/entregaveis/<int:entregavel_id>/remover', methods=['POST'])
@requer_admin
def remover_entregavel_view(entregavel_id):
    from database import remover_entregavel
    try:
        if remover_entregavel(entregavel_id):
            flash('Item removido do catálogo.', 'success')
            logger.info(f"[ADMIN] ✅ Entregável #{entregavel_id} removido por {current_user.email}")
        else:
            flash('Este item já não existia mais no catálogo.', 'warning')
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover entregável: {e}")
        flash('Não foi possível remover: o item ainda está em algum plano. Tire-o dos planos antes.', 'danger')
    return redirect(url_for('admin.listar_entregaveis_view'))


# ============================================================ planos do produto

def _pendencias_venda_web(produto_id):
    """Avisos do que falta para o site vender e medir: chave PIX e planilha do Google Ads (a clonagem não
    copia nenhuma das duas — sem elas o checkout não gera PIX / as conversões não chegam no Ads)."""
    from database import buscar_chave_pix_venda_web
    pendencias = []
    if not buscar_chave_pix_venda_web(produto_id):
        pendencias.append('Sem chave PIX de venda web — o checkout não gera o PIX (tela "Chaves Pix").')
    if not db.execute_query("SELECT 1 FROM google_ads_planilha_dns WHERE produto_id = %s AND ativo = 1 LIMIT 1",
                            (produto_id,), fetch_one=True):
        pendencias.append('Sem planilha do Google Ads — as vendas deste produto NÃO vão como conversão para o Ads '
                          '(tela "Planilhas Google").')
    return pendencias


def _tem_whatsapp(produto_id):
    """O produto vende pelo WhatsApp? Número só de avisos (responde_mensagens = 0, ex.: Música) não conta."""
    return bool(db.execute_query("SELECT 1 FROM telefones_produto WHERE produto_id = %s AND responde_mensagens = 1 "
                                 "LIMIT 1", (produto_id,), fetch_one=True))


@admin_bp.route('/produto/<int:produto_id>/planos')
@requer_login
def produto_planos(produto_id):
    from database import listar_planos_produto, listar_entregaveis_plano, listar_entregaveis
    session['produto_ativo_id'] = produto_id
    produto = _produto_ou_none(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))
    planos = listar_planos_produto(produto_id)
    for plano in planos:
        plano['itens'] = listar_entregaveis_plano(plano['id'])
    web = db.execute_query("SELECT disponivel_web FROM produtos WHERE id = %s", (produto_id,), fetch_one=True)
    pendencias = _pendencias_venda_web(produto_id) if (web or {}).get('disponivel_web') else []
    return render_template('admin/produto_planos.html', produto=produto, planos=planos,
                           catalogo=listar_entregaveis(), pendencias=pendencias,
                           tem_whatsapp=_tem_whatsapp(produto_id))


def _dados_plano(form, plano_atual=None):
    """(dados, erro) do formulário de plano."""
    try:
        preco_original = _numero(form.get('preco_original'))
        preco = _numero(form.get('preco_promocional'))
        desconto = _numero(form.get('desconto_oferta'))
        ordem = int(form.get('ordem') or 1)
    except ValueError:
        return None, 'Preços, desconto e ordem precisam ser números.'
    renovacao = bool(form.get('renovacao'))
    dados = {
        'slug': (form.get('slug') or '').strip().lower(),
        'nome': (form.get('nome') or '').strip(),
        'descricao': (form.get('descricao') or '').strip() or None,
        'imagem_grande': _imagem(form.get('imagem_grande')),
        'imagem_pequena': _imagem(form.get('imagem_pequena')),
        'preco_original': max(preco_original, preco),
        'preco_promocional': preco,
        'desconto_oferta': desconto,
        'renovacao': 1 if renovacao else 0,
        # Renovação nunca vai para a landing nem para o cross-sell: aparece só em "Meu acesso" do app.
        'vitrine': 0 if renovacao else (1 if form.get('vitrine') else 0),
        'ordem': max(1, min(ordem, 99)),
        'ativo': 1 if form.get('ativo') else 0,
        # Checkout (migration 093): o que ela recebe (uma linha por item) e o texto do botão de finalizar.
        'checkout_destaques': '\n'.join(l.strip() for l in (form.get('checkout_destaques') or '').splitlines()
                                        if l.strip()) or None,
        'checkout_texto_botao': (form.get('checkout_texto_botao') or '').strip()[:60] or None,
    }
    if not _SLUG_PLANO.fullmatch(dados['slug']):
        return dados, 'Identificador do plano: só letras minúsculas, números e hífen (ex.: basico, completo).'
    if not dados['nome']:
        return dados, 'Informe o nome do plano.'
    if preco <= 0:
        return dados, 'O preço cobrado precisa ser maior que zero.'
    if desconto < 0 or (desconto > 0 and desconto >= preco):
        return dados, f'O desconto de oferta precisa ser zero ou menor que o preço (R$ {preco:.2f}).'
    if plano_atual and plano_atual['padrao'] and not dados['ativo']:
        return dados, 'O plano padrão não pode ser desativado — defina outro como padrão antes.'
    return dados, None


@admin_bp.route('/produto/<int:produto_id>/planos/novo', methods=['POST'])
@requer_admin
def novo_plano(produto_id):
    from database import salvar_plano, listar_planos_produto, definir_plano_padrao
    destino = redirect(url_for('admin.produto_planos', produto_id=produto_id))
    if not _produto_ou_none(produto_id):
        return redirect(url_for('admin.dashboard'))
    form = request.form.to_dict()
    form.setdefault('ativo', '1')
    dados, erro = _dados_plano(form)
    if erro:
        flash(erro, 'warning')
        return destino
    primeiro = not listar_planos_produto(produto_id)
    try:
        plano_id = salvar_plano(produto_id, None, dados)
    except ValueError as e:
        flash(str(e), 'warning')
        return destino
    if primeiro:  # o primeiro plano do produto já nasce padrão (WhatsApp e link sem ?plano=)
        definir_plano_padrao(produto_id, plano_id)
    logger.info(f"[ADMIN-PLANOS] Produto #{produto_id}: plano '{dados['slug']}' criado por {current_user.email}")
    flash(f"Plano \"{dados['nome']}\" criado. Agora inclua os itens dele (principal, bônus, order bumps).", 'success')
    return redirect(url_for('admin.produto_planos', produto_id=produto_id, _anchor=f'plano-{plano_id}'))


@admin_bp.route('/produto/<int:produto_id>/planos/<int:plano_id>/editar', methods=['GET', 'POST'])
@requer_admin
def editar_plano(produto_id, plano_id):
    from database import get_plano, salvar_plano
    produto = _produto_ou_none(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))
    plano = get_plano(plano_id, produto_id)
    if not plano:
        flash('Plano não encontrado.', 'danger')
        return redirect(url_for('admin.produto_planos', produto_id=produto_id))
    if request.method == 'POST':
        dados, erro = _dados_plano(request.form, plano)
        if erro:
            flash(erro, 'warning')
        else:
            try:
                salvar_plano(produto_id, plano_id, dados)
                logger.info(f"[ADMIN-PLANOS] Plano #{plano_id} do produto #{produto_id} atualizado por {current_user.email}")
                flash('Plano atualizado!', 'success')
                return redirect(url_for('admin.produto_planos', produto_id=produto_id, _anchor=f'plano-{plano_id}'))
            except ValueError as e:
                flash(str(e), 'warning')
        plano = {**plano, **{k: v for k, v in (dados or {}).items()}}
    return render_template('admin/plano_editar.html', produto=produto, plano=plano, imagens=_arquivos('images'))


@admin_bp.route('/produto/<int:produto_id>/planos/<int:plano_id>/padrao', methods=['POST'])
@requer_admin
def definir_plano_padrao_view(produto_id, plano_id):
    from database import get_plano, definir_plano_padrao, listar_entregaveis_plano
    plano = get_plano(plano_id, produto_id)
    destino = redirect(url_for('admin.produto_planos', produto_id=produto_id))
    if not plano:
        flash('Plano não encontrado.', 'danger')
        return destino
    if not plano['ativo']:
        flash('Ative o plano antes de torná-lo padrão.', 'warning')
        return destino
    itens = listar_entregaveis_plano(plano_id)
    if not any(i['papel'] == 'principal' for i in itens):
        flash('O plano padrão precisa ter ao menos um item principal.', 'warning')
        return destino
    if _tem_whatsapp(produto_id) and any(_so_no_site(i) for i in itens):
        flash('Este produto vende pelo WhatsApp, que usa o plano padrão e entrega antes do pagamento: '
              'o plano padrão não pode ter app nem música.', 'warning')
        return destino
    definir_plano_padrao(produto_id, plano_id)
    logger.info(f"[ADMIN-PLANOS] Produto #{produto_id}: plano #{plano_id} agora é o padrão ({current_user.email})")
    flash(f"\"{plano['nome']}\" agora é o plano padrão (WhatsApp e link sem ?plano=).", 'success')
    return destino


@admin_bp.route('/produto/<int:produto_id>/planos/<int:plano_id>/remover', methods=['POST'])
@requer_admin
def remover_plano_view(produto_id, plano_id):
    from database import remover_plano
    motivo = remover_plano(produto_id, plano_id)
    if motivo:
        flash(motivo, 'warning')
    else:
        logger.info(f"[ADMIN-PLANOS] Plano #{plano_id} do produto #{produto_id} removido por {current_user.email}")
        flash('Plano removido.', 'success')
    return redirect(url_for('admin.produto_planos', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/planos/<int:plano_id>/copiar', methods=['POST'])
@requer_admin
def copiar_itens_plano_view(produto_id, plano_id):
    from database import copiar_itens_plano, get_plano, listar_entregaveis_plano
    origem_id = request.form.get('origem_id', type=int)
    destino = get_plano(plano_id, produto_id)
    if (destino and destino['padrao'] and origem_id and _tem_whatsapp(produto_id)
            and any(_so_no_site(i) for i in listar_entregaveis_plano(origem_id))):
        flash('Este produto vende pelo WhatsApp, que usa o plano padrão e entrega antes do pagamento: '
              'não dá para copiar um plano com app ou música para o padrão.', 'warning')
        return redirect(url_for('admin.produto_planos', produto_id=produto_id, _anchor=f'plano-{plano_id}'))
    try:
        copiados = copiar_itens_plano(produto_id, origem_id, plano_id) if origem_id else 0
        flash(f'{copiados} item(ns) copiado(s). Itens que o plano já tinha não foram duplicados.', 'success')
        logger.info(f"[ADMIN-PLANOS] {copiados} itens do plano #{origem_id} → #{plano_id} por {current_user.email}")
    except ValueError as e:
        flash(str(e), 'warning')
    return redirect(url_for('admin.produto_planos', produto_id=produto_id, _anchor=f'plano-{plano_id}'))


# ------------------------------------------------------------ itens do plano

@admin_bp.route('/produto/<int:produto_id>/planos/<int:plano_id>/itens', methods=['POST'])
@requer_admin
def incluir_item_plano(produto_id, plano_id):
    from database import get_plano, get_entregavel, vincular_entregavel_plano
    destino = redirect(url_for('admin.produto_planos', produto_id=produto_id, _anchor=f'plano-{plano_id}'))
    f = request.form
    entregavel_id = f.get('entregavel_id', type=int)
    papel = f.get('papel')
    if not entregavel_id or papel not in PAPEIS:
        flash('Escolha um item do catálogo e um papel válido.', 'warning')
        return destino
    plano = get_plano(plano_id, produto_id)
    entregavel = get_entregavel(entregavel_id)
    if plano and entregavel and entregavel['tipo'] == 'app':
        if papel == 'bump':
            flash('App como order bump ainda não é vendido — inclua o app como principal ou bônus.', 'warning')
            return destino
        if plano['padrao'] and _tem_whatsapp(produto_id):
            flash('Este produto vende pelo WhatsApp, que usa o plano padrão e entrega antes do pagamento: '
                  'o app vai num plano que não é o padrão (ex.: Completo).', 'warning')
            return destino
    if plano and entregavel and entregavel['tipo'] == 'musica':
        from musica.dominio.recursos import papel_permitido
        if not papel_permitido(entregavel['recurso'], papel):
            flash('Música e videoclipe entram como principal; QR code e entregas, como order bump.', 'warning')
            return destino
        if plano['padrao'] and _tem_whatsapp(produto_id):
            flash('Este produto vende pelo WhatsApp, que usa o plano padrão e entrega antes do pagamento: '
                  'itens de música não vão no plano padrão dele.', 'warning')
            return destino
    try:
        preco_original = _numero(f.get('preco_original')) if papel == 'bump' else 0
        preco = _numero(f.get('preco_promocional')) if papel == 'bump' else 0
        ordem = int(f.get('ordem') or 1)
    except ValueError:
        flash('Preços e ordem precisam ser números.', 'warning')
        return destino
    try:
        vincular_entregavel_plano(produto_id, plano_id, entregavel_id, papel, preco_original=max(preco_original, preco),
                                  preco_promocional=preco, ordem=ordem, dias=f.get('dias', type=int))
        flash('Item incluído no plano!', 'success')
        logger.info(f"[ADMIN-PLANOS] Entregável #{entregavel_id} ({papel}) no plano #{plano_id} por {current_user.email}")
    except ValueError as e:
        flash(str(e), 'warning')
    except Exception as e:
        logger.error(f"[ADMIN-PLANOS] ❌ Erro ao incluir item no plano: {e}")
        flash(f'Erro ao incluir item: {e}', 'danger')
    return destino


@admin_bp.route('/produto/<int:produto_id>/planos/itens/<int:vinculo_id>/editar', methods=['GET', 'POST'])
@requer_admin
def editar_item_plano(produto_id, vinculo_id):
    from database import get_vinculo_plano, atualizar_vinculo_plano
    produto = _produto_ou_none(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))
    vinculo = get_vinculo_plano(vinculo_id, produto_id)
    if not vinculo:
        flash('Item não encontrado.', 'danger')
        return redirect(url_for('admin.produto_planos', produto_id=produto_id))
    if request.method == 'POST':
        f = request.form
        dias = f.get('dias', type=int) if vinculo['tipo'] == 'app' else None
        eh_bump = vinculo['papel'] == 'bump'
        try:
            preco_original = _numero(f.get('preco_original')) if eh_bump else 0
            preco = _numero(f.get('preco_promocional')) if eh_bump else 0
            ordem = int(f.get('ordem') or 1)
        except ValueError:
            preco = None
        if preco is None:
            flash('Preços e ordem precisam ser números.', 'warning')
        elif vinculo['tipo'] == 'app' and (not dias or dias <= 0):
            flash('Informe os dias de acesso do app.', 'warning')
        else:
            atualizar_vinculo_plano(vinculo_id, produto_id, preco_original=max(preco_original, preco),
                                    preco_promocional=preco, ordem=ordem, dias=dias)
            flash('Item atualizado!', 'success')
            logger.info(f"[ADMIN-PLANOS] Item #{vinculo_id} atualizado por {current_user.email}")
            return redirect(url_for('admin.produto_planos', produto_id=produto_id, _anchor=f"plano-{vinculo['plano_id']}"))
    return render_template('admin/plano_item_editar.html', produto=produto, vinculo=vinculo)


@admin_bp.route('/produto/<int:produto_id>/planos/itens/<int:vinculo_id>/remover', methods=['POST'])
@requer_admin
def remover_item_plano(produto_id, vinculo_id):
    from database import get_vinculo_plano, remover_vinculo_plano, get_plano, listar_entregaveis_plano
    vinculo = get_vinculo_plano(vinculo_id, produto_id)
    destino = redirect(url_for('admin.produto_planos', produto_id=produto_id,
                               _anchor=f"plano-{vinculo['plano_id']}" if vinculo else None))
    if vinculo and vinculo['papel'] == 'principal':
        plano = get_plano(vinculo['plano_id'], produto_id)
        if plano and plano['padrao'] and len(listar_entregaveis_plano(plano['id'], 'principal')) <= 1:
            # Sem principal, o plano padrão sai de venda: o checkout dá 404 e o WhatsApp cria pedidos sem itens.
            flash('Este é o único item principal do plano padrão — inclua outro principal antes de tirar este.',
                  'warning')
            return destino
    try:
        if remover_vinculo_plano(vinculo_id, produto_id):
            flash('Item tirado do plano.', 'success')
            logger.info(f"[ADMIN-PLANOS] Item #{vinculo_id} removido do produto #{produto_id} por {current_user.email}")
        else:
            flash('Este item já não estava mais no plano.', 'warning')
    except Exception as e:
        # pedido_itens aponta para o item (FK): item já vendido não pode sair — os pedidos dependem dele.
        logger.warning(f"[ADMIN-PLANOS] Item #{vinculo_id} não removido: {e}")
        flash('Este item já foi vendido neste plano e não pode ser tirado (os pedidos apontam para ele). '
              'Para parar de vender, crie um plano novo sem ele e desative este.', 'warning')
    return destino
