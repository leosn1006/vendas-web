import logging
from flask import render_template, redirect, url_for, request, flash, session
from flask_login import current_user
from admin import admin_bp
from admin.auth import requer_login, requer_admin
from database import (db,
    listar_telefones_produto, adicionar_telefone_produto, remover_telefone_produto,
    listar_mensagens_sugeridas, adicionar_mensagem_sugerida, remover_mensagem_sugerida,
    listar_acoes_fluxo, get_acao_fluxo,
    adicionar_acao_fluxo, atualizar_acao_fluxo, remover_acao_fluxo)

_FLUXOS = ['introducao', 'pedido', 'comprovante', 'responder', 'followup']
_FLUXOS_READONLY = {'responder'}
_FLUXOS_LABELS = {
    'introducao':  '👋 Introdução',
    'pedido':      '📦 Pedido',
    'comprovante': '🧾 Comprovante',
    'responder':   '💬 Responder',
    'followup':    '🔔 Follow-up',
}

logger = logging.getLogger(__name__)

# ============================================================
# Dashboard
# ============================================================
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@requer_login
def dashboard():
    try:
        # Resumo para o dashboard
        total_pedidos = db.execute_query(
            "SELECT COUNT(*) as total FROM pedidos",
            fetch_one=True
        )['total']

        total_pagos = db.execute_query(
            "SELECT COUNT(*) as total FROM pedidos WHERE estado_id = 0",
            fetch_one=True
        )['total']

        total_aguardando = db.execute_query(
            "SELECT COUNT(*) as total FROM pedidos WHERE estado_id = 3",
            fetch_one=True
        )['total']

        total_produtos = db.execute_query(
            "SELECT COUNT(*) as total FROM produtos WHERE ativo = TRUE",
            fetch_one=True
        )['total']

        return render_template('admin/dashboard.html',
            total_pedidos   = total_pedidos,
            total_pagos     = total_pagos,
            total_aguardando= total_aguardando,
            total_produtos  = total_produtos,
        )
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro no dashboard: {e}")
        flash('Erro ao carregar dashboard.', 'danger')
        return render_template('admin/dashboard.html')

# ============================================================
# Produtos
# ============================================================
@admin_bp.route('/produtos')
@requer_login
def listar_produtos():
    try:
        produtos = db.execute_query(
            "SELECT * FROM produtos ORDER BY created_at DESC",
            fetch_all=True
        )
        return render_template('admin/produtos.html', produtos=produtos)
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao listar produtos: {e}")
        flash('Erro ao carregar produtos.', 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/produtos/novo', methods=['GET', 'POST'])
@requer_admin
def novo_produto():
    if request.method == 'POST':
        try:
            db.execute_query("""
                INSERT INTO produtos (
                    nome, preco, descricao, prompt_vendas,
                    url_faq_produto, url_audio_introducao, url_audio_explicativo,
                    url_audio_pedido_entregue, url_imagem_complementar,
                    url_arquivo_produto, caption_arquivo_produto, nome_arquivo_produto,
                    mensagem_introducao, mensagem_pedido_enviado_sem_interesse,
                    mensagem_para_pagamento, chave_pix, pix_destinatario_esperado,
                    valor_minimo_pagamento, mensagem_pagamento_confirmado,
                    mensagem_comprovante_invalido, url_arquivo_surpresa,
                    caption_arquivo_surpresa, nome_arquivo_surpresa, ativo
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                request.form.get('nome'),
                request.form.get('preco'),
                request.form.get('descricao'),
                request.form.get('prompt_vendas'),
                request.form.get('url_faq_produto'),
                request.form.get('url_audio_introducao'),
                request.form.get('url_audio_explicativo'),
                request.form.get('url_audio_pedido_entregue'),
                request.form.get('url_imagem_complementar'),
                request.form.get('url_arquivo_produto'),
                request.form.get('caption_arquivo_produto'),
                request.form.get('nome_arquivo_produto'),
                request.form.get('mensagem_introducao'),
                request.form.get('mensagem_pedido_enviado_sem_interesse'),
                request.form.get('mensagem_para_pagamento'),
                request.form.get('chave_pix'),
                request.form.get('pix_destinatario_esperado'),
                request.form.get('valor_minimo_pagamento'),
                request.form.get('mensagem_pagamento_confirmado'),
                request.form.get('mensagem_comprovante_invalido'),
                request.form.get('url_arquivo_surpresa'),
                request.form.get('caption_arquivo_surpresa'),
                request.form.get('nome_arquivo_surpresa'),
                1  # ativo por padrão
            ))
            flash('Produto criado com sucesso!', 'success')
            logger.info(f"[ADMIN] ✅ Produto criado por {current_user.email}")
            return redirect(url_for('admin.listar_produtos'))

        except Exception as e:
            logger.error(f"[ADMIN] ❌ Erro ao criar produto: {e}")
            flash(f'Erro ao criar produto: {e}', 'danger')

    return render_template('admin/produto_form.html', produto=None, acao='novo')

@admin_bp.route('/produtos/<int:produto_id>', methods=['GET', 'POST'])
@requer_login
def editar_produto(produto_id):
    produto = db.execute_query(
        "SELECT * FROM produtos WHERE id = %s",
        (produto_id,), fetch_one=True
    )

    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))

    # perfil consulta só visualiza
    if request.method == 'POST' and not current_user.is_admin():
        flash('Você não tem permissão para editar produtos.', 'danger')
        return redirect(url_for('admin.listar_produtos'))

    if request.method == 'POST':
        try:
            db.execute_query("""
                UPDATE produtos SET
                    nome                                = %s,
                    preco                               = %s,
                    descricao                           = %s,
                    prompt_vendas                       = %s,
                    url_faq_produto                     = %s,
                    url_audio_introducao                = %s,
                    url_audio_explicativo               = %s,
                    url_audio_pedido_entregue           = %s,
                    url_imagem_complementar             = %s,
                    url_arquivo_produto                 = %s,
                    caption_arquivo_produto             = %s,
                    nome_arquivo_produto                = %s,
                    mensagem_introducao                 = %s,
                    mensagem_pedido_enviado_sem_interesse = %s,
                    mensagem_para_pagamento             = %s,
                    chave_pix                           = %s,
                    pix_destinatario_esperado           = %s,
                    valor_minimo_pagamento              = %s,
                    mensagem_pagamento_confirmado       = %s,
                    mensagem_comprovante_invalido       = %s,
                    url_arquivo_surpresa                = %s,
                    caption_arquivo_surpresa            = %s,
                    nome_arquivo_surpresa               = %s,
                    ativo                               = %s
                WHERE id = %s
            """, (
                request.form.get('nome'),
                request.form.get('preco'),
                request.form.get('descricao'),
                request.form.get('prompt_vendas'),
                request.form.get('url_faq_produto'),
                request.form.get('url_audio_introducao'),
                request.form.get('url_audio_explicativo'),
                request.form.get('url_audio_pedido_entregue'),
                request.form.get('url_imagem_complementar'),
                request.form.get('url_arquivo_produto'),
                request.form.get('caption_arquivo_produto'),
                request.form.get('nome_arquivo_produto'),
                request.form.get('mensagem_introducao'),
                request.form.get('mensagem_pedido_enviado_sem_interesse'),
                request.form.get('mensagem_para_pagamento'),
                request.form.get('chave_pix'),
                request.form.get('pix_destinatario_esperado'),
                request.form.get('valor_minimo_pagamento'),
                request.form.get('mensagem_pagamento_confirmado'),
                request.form.get('mensagem_comprovante_invalido'),
                request.form.get('url_arquivo_surpresa'),
                request.form.get('caption_arquivo_surpresa'),
                request.form.get('nome_arquivo_surpresa'),
                1 if request.form.get('ativo') else 0,
                produto_id
            ))
            flash('Produto atualizado com sucesso!', 'success')
            logger.info(f"[ADMIN] ✅ Produto #{produto_id} atualizado por {current_user.email}")
            return redirect(url_for('admin.listar_produtos'))

        except Exception as e:
            logger.error(f"[ADMIN] ❌ Erro ao atualizar produto: {e}")
            flash(f'Erro ao atualizar produto: {e}', 'danger')

    return render_template('admin/produto_form.html', produto=produto, acao='editar')

@admin_bp.route('/produtos/<int:produto_id>/desativar', methods=['POST'])
@requer_admin
def desativar_produto(produto_id):
    try:
        db.execute_query(
            "UPDATE produtos SET ativo = FALSE WHERE id = %s",
            (produto_id,)
        )
        flash('Produto desativado com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ Produto #{produto_id} desativado por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao desativar produto: {e}")
        flash(f'Erro ao desativar produto: {e}', 'danger')
    return redirect(url_for('admin.listar_produtos'))

# ============================================================
# Usuários — só admin
# ============================================================
@admin_bp.route('/usuarios')
@requer_admin
def listar_usuarios():
    try:
        usuarios = db.execute_query(
            "SELECT id, email, nome, perfil, ativo, created_at FROM usuarios ORDER BY created_at DESC",
            fetch_all=True
        )
        return render_template('admin/usuarios.html', usuarios=usuarios)
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao listar usuários: {e}")
        flash('Erro ao carregar usuários.', 'danger')
        return redirect(url_for('admin.dashboard'))

#criar produto a partir de um outro produto, para facilitar a criação de variações
@admin_bp.route('/produtos/<int:produto_id>/clonar', methods=['POST'])
@requer_admin
def clonar_produto(produto_id):
    try:
        # Busca o produto original
        produto = db.execute_query(
            "SELECT * FROM produtos WHERE id = %s",
            (produto_id,), fetch_one=True
        )

        if produto is None:
            flash('Produto não encontrado.', 'danger')
            return redirect(url_for('admin.listar_produtos'))

        # Insere uma cópia com nome diferente
        db.execute_query("""
            INSERT INTO produtos (
                nome, preco, descricao, prompt_vendas,
                url_faq_produto, url_audio_introducao, url_audio_explicativo,
                url_audio_pedido_entregue, url_imagem_complementar,
                url_arquivo_produto, caption_arquivo_produto, nome_arquivo_produto,
                mensagem_introducao, mensagem_pedido_enviado_sem_interesse,
                mensagem_para_pagamento, chave_pix, pix_destinatario_esperado,
                valor_minimo_pagamento, mensagem_pagamento_confirmado,
                mensagem_comprovante_invalido, url_arquivo_surpresa,
                caption_arquivo_surpresa, nome_arquivo_surpresa, ativo
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            f"Cópia de {produto['nome']}",  # nome diferente para identificar
            produto['preco'],
            produto['descricao'],
            produto['prompt_vendas'],
            produto['url_faq_produto'],
            produto['url_audio_introducao'],
            produto['url_audio_explicativo'],
            produto['url_audio_pedido_entregue'],
            produto['url_imagem_complementar'],
            produto['url_arquivo_produto'],
            produto['caption_arquivo_produto'],
            produto['nome_arquivo_produto'],
            produto['mensagem_introducao'],
            produto['mensagem_pedido_enviado_sem_interesse'],
            produto['mensagem_para_pagamento'],
            produto['chave_pix'],
            produto['pix_destinatario_esperado'],
            produto['valor_minimo_pagamento'],
            produto['mensagem_pagamento_confirmado'],
            produto['mensagem_comprovante_invalido'],
            produto['url_arquivo_surpresa'],
            produto['caption_arquivo_surpresa'],
            produto['nome_arquivo_surpresa'],
            0  # inativo por padrão — força o admin a revisar antes de ativar
        ))

        # Busca o ID do produto recém criado
        novo = db.execute_query(
            "SELECT id FROM produtos WHERE nome = %s ORDER BY created_at DESC LIMIT 1",
            (f"Cópia de {produto['nome']}",), fetch_one=True
        )

        flash(f'Produto clonado com sucesso! Revise e ative quando estiver pronto.', 'success')
        logger.info(f"[ADMIN] ✅ Produto #{produto_id} clonado por {current_user.email}")

        # Redireciona direto para edição do clone
        return redirect(url_for('admin.editar_produto', produto_id=novo['id']))

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao clonar produto: {e}")
        flash(f'Erro ao clonar produto: {e}', 'danger')
        return redirect(url_for('admin.listar_produtos'))


# ============================================================
# Seletor de produto ativo (sessão)
# ============================================================
@admin_bp.route('/selecionar-produto', methods=['POST'])
@requer_login
def selecionar_produto():
    produto_id = request.form.get('produto_id', type=int)
    if produto_id:
        session['produto_ativo_id'] = produto_id
        return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))
    session.pop('produto_ativo_id', None)
    return redirect(url_for('admin.dashboard'))


# ============================================================
# Números WhatsApp por produto
# ============================================================
@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp')
@requer_login
def numeros_whatsapp(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query(
        "SELECT id, nome FROM produtos WHERE id = %s", (produto_id,), fetch_one=True
    )
    if not produto:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.dashboard'))
    telefones = listar_telefones_produto(produto_id)
    return render_template('admin/numeros_whatsapp.html', produto=produto, telefones=telefones)


@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp/adicionar', methods=['POST'])
@requer_admin
def adicionar_numero_whatsapp(produto_id):
    telefone = request.form.get('telefone', '').strip()
    if not telefone:
        flash('Informe o número.', 'warning')
        return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))
    try:
        adicionar_telefone_produto(telefone, produto_id)
        flash(f'Número {telefone} adicionado com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ Telefone '{telefone}' associado ao produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao adicionar telefone: {e}")
        flash(f'Erro ao adicionar número: {e}', 'danger')
    return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp/<int:telefone_id>/remover', methods=['POST'])
@requer_admin
def remover_numero_whatsapp(produto_id, telefone_id):
    try:
        remover_telefone_produto(telefone_id)
        flash('Número removido.', 'success')
        logger.info(f"[ADMIN] ✅ Telefone #{telefone_id} removido do produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover telefone: {e}")
        flash(f'Erro ao remover número: {e}', 'danger')
    return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))


# ============================================================
# Mensagens Sugeridas por produto
# ============================================================
@admin_bp.route('/produto/<int:produto_id>/mensagens-sugeridas')
@requer_login
def mensagens_sugeridas(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query(
        "SELECT id, nome FROM produtos WHERE id = %s", (produto_id,), fetch_one=True
    )
    if not produto:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.dashboard'))
    mensagens = listar_mensagens_sugeridas(produto_id)
    return render_template('admin/mensagens_sugeridas.html', produto=produto, mensagens=mensagens)


@admin_bp.route('/produto/<int:produto_id>/mensagens-sugeridas/adicionar', methods=['POST'])
@requer_admin
def adicionar_mensagem_sugerida_view(produto_id):
    mensagem = request.form.get('mensagem', '').strip()
    if not mensagem:
        flash('Informe a mensagem.', 'warning')
        return redirect(url_for('admin.mensagens_sugeridas', produto_id=produto_id))
    try:
        adicionar_mensagem_sugerida(produto_id, mensagem)
        flash('Mensagem adicionada com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ Mensagem sugerida adicionada ao produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao adicionar mensagem: {e}")
        flash(f'Erro ao adicionar mensagem: {e}', 'danger')
    return redirect(url_for('admin.mensagens_sugeridas', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/mensagens-sugeridas/<int:mensagem_id>/remover', methods=['POST'])
@requer_admin
def remover_mensagem_sugerida_view(produto_id, mensagem_id):
    try:
        remover_mensagem_sugerida(mensagem_id)
        flash('Mensagem removida.', 'success')
        logger.info(f"[ADMIN] ✅ Mensagem #{mensagem_id} removida do produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover mensagem: {e}")
        flash(f'Erro ao remover mensagem: {e}', 'danger')
    return redirect(url_for('admin.mensagens_sugeridas', produto_id=produto_id))


# ============================================================
# Fluxos por produto
# ============================================================

def _get_produto_or_redirect(produto_id):
    p = db.execute_query(
        "SELECT id, nome FROM produtos WHERE id = %s", (produto_id,), fetch_one=True
    )
    if not p:
        flash('Produto não encontrado.', 'danger')
    return p


@admin_bp.route('/produto/<int:produto_id>/fluxos')
@requer_login
def fluxos_overview(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    resumo = {}
    for fluxo in _FLUXOS:
        row = db.execute_query(
            "SELECT COUNT(*) as total FROM acoes_fluxo_produto WHERE produto_id=%s AND fluxo=%s",
            (produto_id, fluxo), fetch_one=True
        )
        resumo[fluxo] = row['total'] if row else 0

    return render_template('admin/fluxos_overview.html',
                           produto=produto,
                           fluxos=_FLUXOS,
                           fluxos_labels=_FLUXOS_LABELS,
                           resumo=resumo)


@admin_bp.route('/produto/<int:produto_id>/fluxos/<fluxo>')
@requer_login
def fluxo_acoes(produto_id, fluxo):
    if fluxo not in _FLUXOS:
        flash('Fluxo inválido.', 'danger')
        return redirect(url_for('admin.fluxos_overview', produto_id=produto_id))
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    acoes = listar_acoes_fluxo(produto_id, fluxo)
    return render_template('admin/fluxo_acoes.html',
                           produto=produto,
                           fluxo=fluxo,
                           fluxos=_FLUXOS,
                           fluxos_labels=_FLUXOS_LABELS,
                           acoes=acoes,
                           readonly=fluxo in _FLUXOS_READONLY)


@admin_bp.route('/produto/<int:produto_id>/fluxos/<fluxo>/adicionar', methods=['POST'])
@requer_admin
def adicionar_acao_fluxo_view(produto_id, fluxo):
    if fluxo in _FLUXOS_READONLY:
        flash('Este fluxo é somente leitura.', 'warning')
        return redirect(url_for('admin.fluxo_acoes', produto_id=produto_id, fluxo=fluxo))
    try:
        adicionar_acao_fluxo(
            produto_id, fluxo,
            ordem=int(request.form['ordem']),
            condicao=request.form['condicao'],
            acao=request.form['acao'],
            url=request.form.get('url'),
            mensagem=request.form.get('mensagem'),
            caption=request.form.get('caption'),
            nome_arquivo=request.form.get('nome_arquivo'),
            delay_inicial=float(request.form.get('delay_inicial') or 0),
            delay_final=float(request.form.get('delay_final') or 0),
        )
        flash('Ação adicionada com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ Ação adicionada ao fluxo '{fluxo}' produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao adicionar ação: {e}")
        flash(f'Erro ao adicionar ação: {e}', 'danger')
    return redirect(url_for('admin.fluxo_acoes', produto_id=produto_id, fluxo=fluxo))


@admin_bp.route('/produto/<int:produto_id>/fluxos/<fluxo>/<int:acao_id>/editar', methods=['GET', 'POST'])
@requer_admin
def editar_acao_fluxo(produto_id, fluxo, acao_id):
    if fluxo in _FLUXOS_READONLY:
        flash('Este fluxo é somente leitura.', 'warning')
        return redirect(url_for('admin.fluxo_acoes', produto_id=produto_id, fluxo=fluxo))
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    acao = get_acao_fluxo(acao_id)
    if not acao:
        flash('Ação não encontrada.', 'danger')
        return redirect(url_for('admin.fluxo_acoes', produto_id=produto_id, fluxo=fluxo))

    if request.method == 'POST':
        try:
            atualizar_acao_fluxo(
                acao_id,
                ordem=int(request.form['ordem']),
                condicao=request.form['condicao'],
                acao=request.form['acao'],
                url=request.form.get('url'),
                mensagem=request.form.get('mensagem'),
                caption=request.form.get('caption'),
                nome_arquivo=request.form.get('nome_arquivo'),
                delay_inicial=float(request.form.get('delay_inicial') or 0),
                delay_final=float(request.form.get('delay_final') or 0),
            )
            flash('Ação atualizada com sucesso!', 'success')
            logger.info(f"[ADMIN] ✅ Ação #{acao_id} do fluxo '{fluxo}' atualizada por {current_user.email}")
            return redirect(url_for('admin.fluxo_acoes', produto_id=produto_id, fluxo=fluxo))
        except Exception as e:
            logger.error(f"[ADMIN] ❌ Erro ao atualizar ação: {e}")
            flash(f'Erro ao salvar: {e}', 'danger')

    return render_template('admin/fluxo_acao_editar.html',
                           produto=produto,
                           fluxo=fluxo,
                           fluxos_labels=_FLUXOS_LABELS,
                           acao=acao)


@admin_bp.route('/produto/<int:produto_id>/fluxos/<fluxo>/<int:acao_id>/remover', methods=['POST'])
@requer_admin
def remover_acao_fluxo_view(produto_id, fluxo, acao_id):
    if fluxo in _FLUXOS_READONLY:
        flash('Este fluxo é somente leitura.', 'warning')
        return redirect(url_for('admin.fluxo_acoes', produto_id=produto_id, fluxo=fluxo))
    try:
        remover_acao_fluxo(acao_id)
        flash('Ação removida.', 'success')
        logger.info(f"[ADMIN] ✅ Ação #{acao_id} do fluxo '{fluxo}' removida por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover ação: {e}")
        flash(f'Erro ao remover ação: {e}', 'danger')
    return redirect(url_for('admin.fluxo_acoes', produto_id=produto_id, fluxo=fluxo))
