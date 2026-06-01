import logging
import os
import datetime
import subprocess
import tempfile
from zoneinfo import ZoneInfo
from flask import render_template, redirect, url_for, request, flash, session, current_app, jsonify, send_file
from flask_login import current_user
from werkzeug.utils import secure_filename
from admin import admin_bp
from admin.auth import requer_login, requer_admin, requer_acesso_produto, usuario_tem_acesso_produto
from Whatsapp_config import ativa_whatsapp
from database import (db,
    listar_telefones_produto, adicionar_telefone_produto, remover_telefone_produto, atualizar_telefone_produto,
    listar_mensagens_sugeridas, adicionar_mensagem_sugerida, remover_mensagem_sugerida,
    listar_acoes_fluxo, get_acao_fluxo,
    adicionar_acao_fluxo, atualizar_acao_fluxo, remover_acao_fluxo,
    get_pedido, get_ultimo_pedido_by_phone, salvar_mensagem_pedido,
    buscar_todas_mensagens_pedido,
    buscar_pedido_por_nome, acertar_valor_pedido,
    listar_chaves_pix_produto, adicionar_chave_pix_produto, desativar_chave_pix_produto,
    busca_financeiro_pix,
    listar_planilhas_dns_produto, adicionar_planilha_dns, atualizar_planilha_dns, remover_planilha_dns,
    listar_notificacoes_em_analise, marcar_notificacao_respondida, bloquear_pedido,
    buscar_notificacao_em_analise_pedido, bloquear_followup_pedido)

_FLUXOS = ['introducao', 'pedido', 'comprovante', 'responder', 'followup', 'confirmacao_web', 'followup_interesse_1', 'followup_interesse_2']
_FLUXOS_READONLY = {'responder'}
_FLUXOS_LABELS = {
    'introducao':           '👋 Introdução',
    'pedido':               '📦 Pedido',
    'comprovante':          '🧾 Comprovante',
    'responder':            '💬 Responder',
    'followup':             '🔔 Follow-up',
    'confirmacao_web':      '🌐 Confirmação Web',
    'followup_interesse_1': '⚡ Follow-up Interesse 1 (15 min)',
    'followup_interesse_2': '🔄 Follow-up Interesse 2 (2h)',
}

logger = logging.getLogger(__name__)
SP_TIMEZONE = ZoneInfo('America/Sao_Paulo')


def _hoje_sao_paulo():
    return datetime.datetime.now(SP_TIMEZONE).date()

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
@requer_acesso_produto
def editar_produto(produto_id):
    produto = db.execute_query(
        "SELECT * FROM produtos WHERE id = %s",
        (produto_id,), fetch_one=True
    )

    if produto is None:
        flash('Produto não encontrado.', 'danger')
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
                    ativo                               = %s,
                    numero_convenio_bb                  = %s,
                    disponivel_web                      = %s,
                    url_pagina_vendas                   = %s
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
                request.form.get('numero_convenio_bb') or None,
                1 if request.form.get('disponivel_web') else 0,
                request.form.get('url_pagina_vendas') or None,
                produto_id
            ))
            flash('Produto atualizado com sucesso!', 'success')
            logger.info(f"[ADMIN] ✅ Produto #{produto_id} atualizado por {current_user.email}")
            return redirect(url_for('admin.listar_produtos'))

        except Exception as e:
            logger.error(f"[ADMIN] ❌ Erro ao atualizar produto: {e}")
            flash(f'Erro ao atualizar produto: {e}', 'danger')

    return render_template('admin/produto_form.html', produto=produto, acao='editar')

@admin_bp.route('/produtos/<int:produto_id>/agente-vendas', methods=['GET', 'POST'])
@requer_acesso_produto
def agente_vendas_produto(produto_id):
    produto = db.execute_query(
        "SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True
    )
    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))

    if request.method == 'POST':
        try:
            db.execute_query(
                "UPDATE produtos SET prompt_vendas = %s, faq = %s, url_arquivo_produto = %s WHERE id = %s",
                (request.form.get('prompt_vendas'), request.form.get('faq'),
                 request.form.get('url_arquivo_produto') or None, produto_id)
            )
            flash('Agente de Vendas IA atualizado com sucesso!', 'success')
            logger.info(f"[ADMIN] ✅ prompt_vendas/faq/url_arquivo_produto do produto #{produto_id} atualizado por {current_user.email}")
        except Exception as e:
            logger.error(f"[ADMIN] ❌ Erro ao atualizar prompt: {e}")
            flash(f'Erro ao atualizar: {e}', 'danger')
        return redirect(url_for('admin.agente_vendas_produto', produto_id=produto_id))

    return render_template('admin/produto_agente_vendas.html', produto=produto)

@admin_bp.route('/produtos/<int:produto_id>/dados-basicos', methods=['GET', 'POST'])
@requer_acesso_produto
def dados_basicos_produto(produto_id):
    produto = db.execute_query(
        "SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True
    )
    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))

    if request.method == 'POST':
        try:
            db.execute_query("""
                UPDATE produtos SET
                    nome                          = %s,
                    descricao                     = %s,
                    preco                         = %s,
                    valor_minimo_pagamento        = %s,
                    chave_pix                     = %s,
                    pix_destinatario_esperado     = %s,
                    numero_convenio_bb            = %s,
                    disponivel_web                = %s,
                    url_pagina_vendas             = %s,
                    email_remetente               = %s,
                    email_nome_remetente          = %s,
                    email_cor_primaria            = %s,
                    email_cor_secundaria          = %s,
                    url_pdf                       = %s,
                    url_pdf_bonus                 = %s,
                    google_sheets_spreadsheet_id  = %s,
                    google_sheets_sheet_name      = %s,
                    google_ads_conversion_name    = %s,
                    ativo                         = %s
                WHERE id = %s
            """, (
                request.form.get('nome'),
                request.form.get('descricao'),
                request.form.get('preco'),
                request.form.get('valor_minimo_pagamento'),
                request.form.get('chave_pix') or None,
                request.form.get('pix_destinatario_esperado') or None,
                request.form.get('numero_convenio_bb') or None,
                1 if request.form.get('disponivel_web') else 0,
                request.form.get('url_pagina_vendas') or None,
                request.form.get('email_remetente') or None,
                request.form.get('email_nome_remetente') or None,
                request.form.get('email_cor_primaria') or None,
                request.form.get('email_cor_secundaria') or None,
                request.form.get('url_pdf') or None,
                request.form.get('url_pdf_bonus') or None,
                request.form.get('google_sheets_spreadsheet_id') or None,
                request.form.get('google_sheets_sheet_name') or 'Página1',
                request.form.get('google_ads_conversion_name') or None,
                int(request.form.get('ativo', 1)),
                produto_id
            ))
            flash('Dados básicos atualizados com sucesso!', 'success')
            logger.info(f"[ADMIN] ✅ Dados básicos do produto #{produto_id} atualizados por {current_user.email}")
        except Exception as e:
            logger.error(f"[ADMIN] ❌ Erro ao atualizar dados básicos: {e}")
            flash(f'Erro ao atualizar: {e}', 'danger')
        return redirect(url_for('admin.dados_basicos_produto', produto_id=produto_id))

    return render_template('admin/produto_dados_basicos.html', produto=produto)

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
# Usuários — CRUD (só admin)
# ============================================================
@admin_bp.route('/usuarios')
@requer_admin
def listar_usuarios():
    try:
        usuarios = db.execute_query(
            "SELECT id, email, nome, perfil, ativo, primeiro_acesso, telefone, created_at FROM usuarios ORDER BY nome",
            fetch_all=True
        ) or []
        todos_produtos = db.execute_query(
            "SELECT id, nome FROM produtos WHERE ativo = TRUE ORDER BY nome",
            fetch_all=True
        ) or []
        # Produtos vinculados a cada usuário
        vinculos = db.execute_query(
            "SELECT usuario_id, produto_id FROM usuario_produtos",
            fetch_all=True
        ) or []
        # Mapa: usuario_id -> set(produto_id)
        mapa_vinculos = {}
        for v in vinculos:
            mapa_vinculos.setdefault(v['usuario_id'], set()).add(v['produto_id'])
        return render_template(
            'admin/usuarios.html',
            usuarios        = usuarios,
            todos_produtos  = todos_produtos,
            mapa_vinculos   = mapa_vinculos,
        )
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao listar usuários: {e}")
        flash('Erro ao carregar usuários.', 'danger')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/usuarios/novo', methods=['POST'])
@requer_admin
def criar_usuario():
    from werkzeug.security import generate_password_hash
    nome   = request.form.get('nome', '').strip()
    email  = request.form.get('email', '').strip().lower()
    perfil = request.form.get('perfil', 'consulta')

    if not nome or not email:
        flash('Nome e e-mail são obrigatórios.', 'danger')
        return redirect(url_for('admin.listar_usuarios'))
    if perfil not in ('admin', 'consulta'):
        flash('Perfil inválido.', 'danger')
        return redirect(url_for('admin.listar_usuarios'))

    try:
        db.execute_query(
            """INSERT INTO usuarios (email, senha, nome, perfil, ativo, primeiro_acesso)
               VALUES (%s, %s, %s, %s, TRUE, TRUE)""",
            (email, generate_password_hash('1234'), nome, perfil)
        )
        flash(f'Usuário "{nome}" criado com sucesso. Senha inicial: 1234', 'success')
        logger.info(f"[ADMIN] ✅ Usuário '{email}' criado por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao criar usuário: {e}")
        flash(f'Erro ao criar usuário: {e}', 'danger')
    return redirect(url_for('admin.listar_usuarios'))


@admin_bp.route('/usuarios/<int:usuario_id>/editar', methods=['POST'])
@requer_admin
def editar_usuario(usuario_id):
    nome     = request.form.get('nome', '').strip()
    email    = request.form.get('email', '').strip().lower()
    perfil   = request.form.get('perfil', 'consulta')
    ativo    = request.form.get('ativo') == '1'
    telefone = request.form.get('telefone', '').strip() or None

    if not nome or not email:
        flash('Nome e e-mail são obrigatórios.', 'danger')
        return redirect(url_for('admin.listar_usuarios'))
    if perfil not in ('admin', 'consulta'):
        flash('Perfil inválido.', 'danger')
        return redirect(url_for('admin.listar_usuarios'))
    if telefone and (not telefone.isdigit() or len(telefone) > 20):
        flash('Telefone inválido. Use apenas dígitos (ex: 556181163324).', 'danger')
        return redirect(url_for('admin.listar_usuarios'))
    if telefone:
        telefone_ja_em_uso = db.execute_query(
            "SELECT id FROM usuarios WHERE telefone = %s AND id <> %s LIMIT 1",
            (telefone, usuario_id),
            fetch_one=True
        )
        if telefone_ja_em_uso:
            flash('Telefone já cadastrado para outro usuário.', 'danger')
            return redirect(url_for('admin.listar_usuarios'))

    try:
        db.execute_query(
            "UPDATE usuarios SET nome = %s, email = %s, perfil = %s, ativo = %s, telefone = %s WHERE id = %s",
            (nome, email, perfil, ativo, telefone, usuario_id)
        )
        flash('Usuário atualizado com sucesso.', 'success')
        logger.info(f"[ADMIN] ✅ Usuário #{usuario_id} editado por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao editar usuário: {e}")
        flash(f'Erro ao editar usuário: {e}', 'danger')
    return redirect(url_for('admin.listar_usuarios'))


@admin_bp.route('/usuarios/<int:usuario_id>/resetar-senha', methods=['POST'])
@requer_admin
def resetar_senha_usuario(usuario_id):
    from werkzeug.security import generate_password_hash
    try:
        db.execute_query(
            "UPDATE usuarios SET senha = %s, primeiro_acesso = TRUE WHERE id = %s",
            (generate_password_hash('1234'), usuario_id)
        )
        flash('Senha resetada para 1234. O usuário será obrigado a trocar no próximo acesso.', 'success')
        logger.info(f"[ADMIN] ✅ Senha do usuário #{usuario_id} resetada por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao resetar senha: {e}")
        flash(f'Erro ao resetar senha: {e}', 'danger')
    return redirect(url_for('admin.listar_usuarios'))


@admin_bp.route('/usuarios/<int:usuario_id>/toggle-ativo', methods=['POST'])
@requer_admin
def toggle_ativo_usuario(usuario_id):
    if usuario_id == current_user.id:
        flash('Você não pode desativar sua própria conta.', 'danger')
        return redirect(url_for('admin.listar_usuarios'))
    try:
        db.execute_query(
            "UPDATE usuarios SET ativo = NOT ativo WHERE id = %s",
            (usuario_id,)
        )
        flash('Status do usuário alterado.', 'success')
        logger.info(f"[ADMIN] ✅ Status do usuário #{usuario_id} alterado por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao alterar status: {e}")
        flash(f'Erro: {e}', 'danger')
    return redirect(url_for('admin.listar_usuarios'))


@admin_bp.route('/usuarios/<int:usuario_id>/produtos/adicionar', methods=['POST'])
@requer_admin
def vincular_produto_usuario(usuario_id):
    produto_id = request.form.get('produto_id', type=int)
    if not produto_id:
        flash('Selecione um produto.', 'danger')
        return redirect(url_for('admin.listar_usuarios'))
    try:
        db.execute_query(
            "INSERT IGNORE INTO usuario_produtos (usuario_id, produto_id) VALUES (%s, %s)",
            (usuario_id, produto_id)
        )
        flash('Produto vinculado com sucesso.', 'success')
        logger.info(f"[ADMIN] ✅ Produto #{produto_id} vinculado ao usuário #{usuario_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao vincular produto: {e}")
        flash(f'Erro ao vincular produto: {e}', 'danger')
    return redirect(url_for('admin.listar_usuarios'))


@admin_bp.route('/usuarios/<int:usuario_id>/produtos/<int:produto_id>/remover', methods=['POST'])
@requer_admin
def desvincular_produto_usuario(usuario_id, produto_id):
    try:
        db.execute_query(
            "DELETE FROM usuario_produtos WHERE usuario_id = %s AND produto_id = %s",
            (usuario_id, produto_id)
        )
        flash('Produto desvinculado.', 'success')
        logger.info(f"[ADMIN] ✅ Produto #{produto_id} desvinculado do usuário #{usuario_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao desvincular produto: {e}")
        flash(f'Erro ao desvincular produto: {e}', 'danger')
    return redirect(url_for('admin.listar_usuarios'))

@admin_bp.route('/usuarios/<int:usuario_id>/pedidos-telefone')
@requer_login
def listar_pedidos_telefone(usuario_id):
    try:
        fallback_url = url_for('admin.listar_usuarios') if current_user.is_admin() else url_for('admin.dashboard')

        if not current_user.is_admin() and usuario_id != current_user.id:
            flash('Você só pode visualizar pedidos do seu próprio usuário.', 'danger')
            return redirect(url_for('admin.listar_pedidos_telefone', usuario_id=current_user.id))

        usuario = db.execute_query(
            "SELECT id, nome, telefone FROM usuarios WHERE id = %s",
            (usuario_id,), fetch_one=True
        )
        if not usuario:
            flash('Usuário não encontrado.', 'danger')
            return redirect(fallback_url)
        if not usuario.get('telefone'):
            flash('Este usuário não tem telefone cadastrado.', 'warning')
            return redirect(fallback_url)

        pedidos = db.execute_query(
            """SELECT p.id, p.contact_name, ep.descricao AS estado, p.data_contato_site
               FROM pedidos p
               JOIN estado_pedidos ep ON ep.id = p.estado_id
               WHERE p.contact_phone = %s
               ORDER BY p.data_contato_site DESC""",
            (usuario['telefone'],), fetch_all=True
        ) or []

        usuarios_dropdown = []
        if current_user.is_admin():
            usuarios_dropdown = db.execute_query(
                "SELECT id, nome, telefone FROM usuarios WHERE ativo = TRUE ORDER BY nome",
                fetch_all=True
            ) or []

        return render_template(
            'admin/pedidos_telefone.html',
            usuario           = usuario,
            pedidos           = pedidos,
            usuarios_dropdown = usuarios_dropdown,
            pode_gerenciar_outros = current_user.is_admin(),
        )
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao listar pedidos do telefone do usuário #{usuario_id}: {e}")
        flash('Erro ao carregar pedidos.', 'danger')
        return redirect(fallback_url)


@admin_bp.route('/usuarios/pedidos-telefone', methods=['GET'])
@requer_admin
def selecionar_usuario_pedidos_telefone():
    usuario_id = request.args.get('usuario_id', type=int)
    if not usuario_id:
        flash('Selecione um usuário válido.', 'warning')
        return redirect(url_for('admin.listar_usuarios'))
    return redirect(url_for('admin.listar_pedidos_telefone', usuario_id=usuario_id))


@admin_bp.route('/usuarios/<int:usuario_id>/pedidos/<int:pedido_id>/apagar', methods=['POST'])
@requer_login
def apagar_pedido_usuario(usuario_id, pedido_id):
    try:
        if not current_user.is_admin() and usuario_id != current_user.id:
            flash('Você só pode apagar pedidos do seu próprio usuário.', 'danger')
            return redirect(url_for('admin.listar_pedidos_telefone', usuario_id=current_user.id))

        usuario = db.execute_query(
            "SELECT id, nome, telefone FROM usuarios WHERE id = %s",
            (usuario_id,), fetch_one=True
        )
        if not usuario or not usuario.get('telefone'):
            flash('Usuário ou telefone não encontrado.', 'danger')
            if current_user.is_admin():
                return redirect(url_for('admin.listar_usuarios'))
            return redirect(url_for('admin.dashboard'))

        # Segurança: verifica se o pedido pertence ao telefone deste usuário
        pedido = db.execute_query(
            "SELECT id FROM pedidos WHERE id = %s AND contact_phone = %s",
            (pedido_id, usuario['telefone']), fetch_one=True
        )
        if not pedido:
            flash('Pedido não encontrado ou não pertence ao telefone deste usuário.', 'danger')
            return redirect(url_for('admin.listar_pedidos_telefone', usuario_id=usuario_id))

        db.execute_query("DELETE FROM pedidos WHERE id = %s", (pedido_id,))
        flash(f'Pedido #{pedido_id} apagado com sucesso.', 'success')
        logger.info(f"[ADMIN] ✅ Pedido #{pedido_id} apagado por {current_user.email} (telefone {usuario['telefone']})")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao apagar pedido #{pedido_id}: {e}")
        flash(f'Erro ao apagar pedido: {e}', 'danger')
    return redirect(url_for('admin.listar_pedidos_telefone', usuario_id=usuario_id))


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

        # Insere uma cópia com nome diferente; execute_query retorna lastrowid
        novo_id = db.execute_query("""
            INSERT INTO produtos (
                nome, preco, descricao, prompt_vendas, faq, prompt_followup,
                url_faq_produto, url_audio_introducao, url_audio_explicativo,
                url_audio_pedido_entregue, url_imagem_complementar,
                url_arquivo_produto, caption_arquivo_produto, nome_arquivo_produto,
                mensagem_introducao, mensagem_pedido_enviado_sem_interesse,
                mensagem_para_pagamento, chave_pix, pix_destinatario_esperado,
                valor_minimo_pagamento, mensagem_pagamento_confirmado,
                mensagem_comprovante_invalido, url_arquivo_surpresa,
                caption_arquivo_surpresa, nome_arquivo_surpresa,
                google_sheets_spreadsheet_id, google_sheets_sheet_name,
                google_ads_conversion_name, numero_convenio_bb, disponivel_web,
                url_pdf, url_pdf_bonus, email_remetente,
                email_nome_remetente, email_cor_primaria, email_cor_secundaria,
                ativo
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            f"Cópia de {produto['nome']}",  # nome diferente para identificar
            produto['preco'],
            produto['descricao'],
            produto['prompt_vendas'],
            produto['faq'],
            produto['prompt_followup'],
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
            produto['google_sheets_spreadsheet_id'],
            produto['google_sheets_sheet_name'],
            produto['google_ads_conversion_name'],
            produto['numero_convenio_bb'],
            0,  # disponivel_web = FALSE por padrão
            produto['url_pdf'],
            produto['url_pdf_bonus'],
            produto['email_remetente'],
            produto['email_nome_remetente'],
            produto['email_cor_primaria'],
            produto['email_cor_secundaria'],
            0  # inativo por padrão — força o admin a revisar antes de ativar
        ))
        contador_acoes = 0
        contador_mensagens = 0

        # Clonar mensagens sugeridas
        mensagens_originais = listar_mensagens_sugeridas(produto_id)
        for msg in mensagens_originais:
            adicionar_mensagem_sugerida(novo_id, msg['mensagem'])
            contador_mensagens += 1

        # Clonar ações de fluxo para todos os 5 fluxos
        for fluxo in _FLUXOS:
            acoes_originais = listar_acoes_fluxo(produto_id, fluxo)
            for acao in acoes_originais:
                adicionar_acao_fluxo(
                    produto_id=novo_id,
                    fluxo=acao['fluxo'],
                    ordem=acao['ordem'],
                    condicao=acao['condicao'],
                    acao=acao['acao'],
                    url=acao['url'],
                    mensagem=acao['mensagem'],
                    caption=acao['caption'],
                    nome_arquivo=acao['nome_arquivo'],
                    delay_inicial=acao['delay_inicial'],
                    delay_final=acao['delay_final']
                )
                contador_acoes += 1

        # NOTA: Telefones NÃO são clonados porque cada número WhatsApp só pode pertencer a um produto
        # (constraint uk_telefone na tabela telefones_produto).
        # O usuário deve configurar telefones manualmente para o novo produto.

        flash(f'Produto clonado com sucesso! {contador_acoes} ações e {contador_mensagens} mensagens copiadas. ⚠️ Configure os números WhatsApp manualmente. Revise e ative quando estiver pronto.', 'success')
        logger.info(f"[ADMIN] ✅ Produto #{produto_id} clonado (#{novo_id}) por {current_user.email} - {contador_acoes} ações, {contador_mensagens} mensagens (telefones não clonados)")

        # Seleciona o clone como produto ativo e vai para os submenus
        session['produto_ativo_id'] = novo_id
        return redirect(url_for('admin.dados_basicos_produto', produto_id=novo_id))

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao clonar produto: {e}")
        flash(f'Erro ao clonar produto: {e}', 'danger')
        return redirect(url_for('admin.listar_produtos'))


# ============================================================
# Notificações de pedido
# ============================================================
@admin_bp.route('/produto/<int:produto_id>/notificacoes')
@requer_acesso_produto
def notificacoes_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query("SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True)
    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))
    notificacoes = listar_notificacoes_em_analise(produto_id)
    return render_template('admin/produto_notificacoes.html', produto=produto, notificacoes=notificacoes)


@admin_bp.route('/produto/<int:produto_id>/notificacoes/<int:notificacao_id>/responder', methods=['POST'])
@requer_acesso_produto
def responder_notificacao(produto_id, notificacao_id):
    marcar_notificacao_respondida(notificacao_id, produto_id)
    return redirect(url_for('admin.notificacoes_produto', produto_id=produto_id))


# ============================================================
# Conversas — visualização e envio manual de mensagens
# ============================================================
@admin_bp.route('/produto/<int:produto_id>/conversas', methods=['GET', 'POST'])
@requer_acesso_produto
def conversas_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query("SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True)
    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))

    if request.method == 'POST':
        q = (request.form.get('q') or '').strip()
        pedido = None
        if q.isdigit() and len(q) <= 7:
            pedido = get_pedido(int(q))
            if pedido and pedido.get('produto_id') != produto_id:
                pedido = None
        if not pedido:
            pedido = get_ultimo_pedido_by_phone(q, produto_id)
        if not pedido:
            pedido = buscar_pedido_por_nome(q, produto_id)

        if pedido:
            return redirect(url_for('admin.conversa_pedido', produto_id=produto_id, pedido_id=pedido['id']))
        flash('Nenhuma conversa encontrada para esse pedido, telefone ou nome.', 'danger')

    return render_template('admin/produto_conversas.html', produto=produto)


@admin_bp.route('/produto/<int:produto_id>/conversas/<int:pedido_id>')
@requer_acesso_produto
def conversa_pedido(produto_id, pedido_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query("SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True)
    pedido  = get_pedido(pedido_id)

    if not produto or not pedido or pedido.get('produto_id') != produto_id:
        flash('Conversa não encontrada.', 'danger')
        return redirect(url_for('admin.conversas_produto', produto_id=produto_id))

    mensagens = buscar_todas_mensagens_pedido(pedido_id)
    notificacao_ativa = buscar_notificacao_em_analise_pedido(pedido_id)
    return render_template('admin/produto_conversas.html',
                           produto=produto, pedido=pedido, mensagens=mensagens,
                           notificacao_ativa=notificacao_ativa)


@admin_bp.route('/produto/<int:produto_id>/conversas/<int:pedido_id>/bloquear-followup', methods=['POST'])
@requer_acesso_produto
def bloquear_followup_conversa(produto_id, pedido_id):
    pedido = get_pedido(pedido_id)
    if not pedido or pedido.get('produto_id') != produto_id:
        flash('Pedido não encontrado.', 'danger')
        return redirect(url_for('admin.conversas_produto', produto_id=produto_id))
    bloquear_followup_pedido(pedido_id)
    flash('Followup bloqueado. Nenhuma cobrança automática será enviada para este pedido.', 'success')
    return redirect(url_for('admin.conversa_pedido', produto_id=produto_id, pedido_id=pedido_id))


@admin_bp.route('/produto/<int:produto_id>/conversas/<int:pedido_id>/bloquear', methods=['POST'])
@requer_acesso_produto
def bloquear_conversa(produto_id, pedido_id):
    pedido = get_pedido(pedido_id)
    if not pedido or pedido.get('produto_id') != produto_id:
        flash('Pedido não encontrado.', 'danger')
        return redirect(url_for('admin.conversas_produto', produto_id=produto_id))
    bloquear_pedido(pedido_id)
    flash('Pedido bloqueado. O agente não responderá mais a este contato.', 'success')
    return redirect(url_for('admin.conversa_pedido', produto_id=produto_id, pedido_id=pedido_id))


@admin_bp.route('/produto/<int:produto_id>/conversas/<int:pedido_id>/enviar', methods=['POST'])
@requer_acesso_produto
def conversa_enviar_mensagem(produto_id, pedido_id):
    from whatsapp import enviar_mensagem as wpp_enviar, enviar_audio as wpp_audio, enviar_documento as wpp_doc
    pedido = get_pedido(pedido_id)
    if not pedido or pedido.get('produto_id') != produto_id:
        flash('Pedido não encontrado.', 'danger')
        return redirect(url_for('admin.conversas_produto', produto_id=produto_id))

    tipo = request.form.get('tipo', 'texto')
    try:
        if tipo == 'audio':
            url_audio = (request.form.get('url_audio') or '').strip()
            if not url_audio:
                flash('URL do áudio não pode ser vazia.', 'danger')
                return redirect(url_for('admin.conversa_pedido', produto_id=produto_id, pedido_id=pedido_id))
            mid = wpp_audio(pedido, url_audio)
            salvar_mensagem_pedido(mid, pedido_id, f'[Áudio: {url_audio}]', tipo_mensagem='enviada')

        elif tipo == 'arquivo':
            url_arquivo  = (request.form.get('url_arquivo') or '').strip()
            caption      = (request.form.get('caption') or '').strip()
            nome_arquivo = (request.form.get('nome_arquivo') or '').strip()
            if not url_arquivo or not nome_arquivo:
                flash('URL e nome do arquivo são obrigatórios.', 'danger')
                return redirect(url_for('admin.conversa_pedido', produto_id=produto_id, pedido_id=pedido_id))
            mid = wpp_doc(pedido, url_arquivo, caption, nome_arquivo)
            salvar_mensagem_pedido(mid, pedido_id, f'[Arquivo: {nome_arquivo} — {caption}]', tipo_mensagem='enviada')

        else:  # texto
            texto = (request.form.get('texto') or '').strip()
            if not texto:
                flash('Mensagem não pode ser vazia.', 'danger')
                return redirect(url_for('admin.conversa_pedido', produto_id=produto_id, pedido_id=pedido_id))
            mid = wpp_enviar(pedido, texto)
            salvar_mensagem_pedido(mid, pedido_id, texto, tipo_mensagem='enviada')

        logger.info(f"[ADMIN] ✅ Mensagem ({tipo}) enviada ao pedido #{pedido_id} por {current_user.email}")
        flash('Mensagem enviada com sucesso!', 'success')
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao enviar mensagem ({tipo}): {e}")
        flash(f'Erro ao enviar: {e}', 'danger')

    return redirect(url_for('admin.conversa_pedido', produto_id=produto_id, pedido_id=pedido_id))


# ============================================================
# Acertar Valor — ajuste manual de pagamento
# ============================================================
@admin_bp.route('/produto/<int:produto_id>/acertar-valor', methods=['GET', 'POST'])
@requer_acesso_produto
def acertar_valor_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query("SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True)
    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))

    pedido = None
    if request.method == 'POST':
        q = (request.form.get('q') or '').strip()
        if q.isdigit() and len(q) <= 7:
            pedido = get_pedido(int(q))
            if pedido and pedido.get('produto_id') != produto_id:
                pedido = None
        if not pedido:
            pedido = get_ultimo_pedido_by_phone(q, produto_id)
        if not pedido:
            pedido = buscar_pedido_por_nome(q, produto_id)

        if not pedido:
            flash('Nenhum pedido encontrado para esse ID, telefone ou nome.', 'danger')

    return render_template('admin/produto_acertar_valor.html', produto=produto, pedido=pedido)


@admin_bp.route('/produto/<int:produto_id>/acertar-valor/<int:pedido_id>/salvar', methods=['POST'])
@requer_acesso_produto
def acertar_valor_salvar(produto_id, pedido_id):
    pedido = get_pedido(pedido_id)
    if not pedido or pedido.get('produto_id') != produto_id:
        flash('Pedido não encontrado.', 'danger')
        return redirect(url_for('admin.acertar_valor_produto', produto_id=produto_id))

    try:
        valor = float((request.form.get('valor_pago') or '0').replace(',', '.'))
    except (ValueError, TypeError):
        valor = 0.0

    if valor <= 0.0:
        flash('Valor inválido. Informe um valor maior que zero.', 'danger')
        return redirect(url_for('admin.acertar_valor_produto', produto_id=produto_id))

    try:
        acertar_valor_pedido(pedido_id, valor)
        logger.info(f"[ADMIN] ✅ Pedido #{pedido_id} marcado como pago (R$ {valor:.2f}) por {current_user.email}")
        flash(f'Pedido #{pedido_id} atualizado: R$ {valor:.2f} — estado alterado para Pago.', 'success')
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao acertar valor do pedido #{pedido_id}: {e}")
        flash(f'Erro ao salvar: {e}', 'danger')

    return redirect(url_for('admin.acertar_valor_produto', produto_id=produto_id))


# ============================================================
# Seletor de produto ativo (sessão)
# ============================================================
@admin_bp.route('/selecionar-produto', methods=['POST'])
@requer_login
def selecionar_produto():
    produto_id = request.form.get('produto_id', type=int)
    if produto_id:
        # Consulta deve ter vínculo com o produto que está selecionando
        if not current_user.is_admin() and not usuario_tem_acesso_produto(current_user.id, produto_id):
            flash('Você não tem acesso a este produto.', 'danger')
            return redirect(url_for('admin.dashboard'))
        session['produto_ativo_id'] = produto_id
        return redirect(url_for('admin.analytics_produto', produto_id=produto_id))
    session.pop('produto_ativo_id', None)
    return redirect(url_for('admin.dashboard'))


# ============================================================
# Números WhatsApp por produto
# ============================================================
@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp')
@requer_acesso_produto
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
@requer_acesso_produto
def adicionar_numero_whatsapp(produto_id):
    telefone = request.form.get('telefone', '').strip()
    if not telefone:
        flash('Informe o número.', 'warning')
        return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))
    api_phone_number_id = request.form.get('api_phone_number_id', '').strip() or None
    token_env_key = request.form.get('token_env_key', '').strip() or 'WHATSAPP_ACCESS_TOKEN'
    try:
        adicionar_telefone_produto(telefone, produto_id, api_phone_number_id, token_env_key)
        flash(f'Número {telefone} adicionado com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ Telefone '{telefone}' associado ao produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao adicionar telefone: {e}")
        flash(f'Erro ao adicionar número: {e}', 'danger')
    return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp/<int:telefone_id>/remover', methods=['POST'])
@requer_acesso_produto
def remover_numero_whatsapp(produto_id, telefone_id):
    try:
        remover_telefone_produto(telefone_id, produto_id)
        flash('Número removido.', 'success')
        logger.info(f"[ADMIN] ✅ Telefone #{telefone_id} removido do produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover telefone: {e}")
        flash(f'Erro ao remover número: {e}', 'danger')
    return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp/<int:telefone_id>/editar', methods=['POST'])
@requer_acesso_produto
def editar_numero_whatsapp(produto_id, telefone_id):
    telefone = request.form.get('telefone', '').strip()
    if not telefone:
        flash('Informe o número.', 'warning')
        return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))
    api_phone_number_id = request.form.get('api_phone_number_id', '').strip() or None
    token_env_key = request.form.get('token_env_key', '').strip() or 'WHATSAPP_ACCESS_TOKEN'
    try:
        contador_uso = max(0, int(request.form.get('contador_uso', 0) or 0))
    except (ValueError, TypeError):
        contador_uso = 0
    try:
        atualizar_telefone_produto(telefone_id, produto_id, telefone, api_phone_number_id, token_env_key, contador_uso)
        flash(f'Número {telefone} atualizado com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ Telefone #{telefone_id} atualizado por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao editar telefone: {e}")
        flash(f'Erro ao atualizar número: {e}', 'danger')
    return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp/ativar', methods=['POST'])
@requer_admin
def ativar_numero_whatsapp(produto_id):
    api_phone_number_id = request.form.get('api_phone_number_id', '').strip()
    token_env_key = request.form.get('token_env_key', '').strip() or 'WHATSAPP_ACCESS_TOKEN'
    if not api_phone_number_id:
        flash('Informe o API phone_number_id para ativar.', 'warning')
        return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))
    token = os.getenv(token_env_key, '')
    if not token:
        flash(f'Token não encontrado para a chave "{token_env_key}".', 'danger')
        return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))
    sucesso = ativa_whatsapp(api_phone_number_id, token=token)
    if sucesso:
        flash(f'Número {api_phone_number_id} ativado com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ WhatsApp {api_phone_number_id} ativado por {current_user.email}")
    else:
        flash(f'Falha ao ativar o número {api_phone_number_id}. Verifique os logs.', 'danger')
    return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))


# ============================================================
# Mensagens Sugeridas por produto
# ============================================================
@admin_bp.route('/produto/<int:produto_id>/mensagens-sugeridas')
@requer_acesso_produto
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
            param1=request.form.get('param1'),
            param2=request.form.get('param2'),
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
                param1=request.form.get('param1'),
                param2=request.form.get('param2'),
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


# ============================================================
# Arquivos (PDF e Áudio OGG)
# ============================================================

_UPLOAD_CONFIG = {
    'pdf':    {'ext': '.pdf', 'magic': b'%PDF', 'max_mb': 10, 'subdir': 'arquivos'},
    'audio':  {'subdir': 'audios'},
    'imagem': {'subdir': 'images', 'max_mb': 5},
}

_AUDIO_EXTS = {'.ogg', '.mp3', '.wav', '.m4a'}
_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.svg', '.webp'}


def _e_ogg_opus(caminho):
    """Retorna True se o arquivo já for OGG com codec Opus."""
    with open(caminho, 'rb') as f:
        cabecalho = f.read(64)
    return cabecalho[:4] == b'OggS' and b'OpusHead' in cabecalho


def _converter_para_opus(caminho_entrada):
    """Converte qualquer áudio para ogg/opus com bitrate ajustado para ficar ≤ 490KB.
    Retorna (caminho_saida, erro). caminho_saida é None em caso de erro."""
    # Descobrir duração
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            caminho_entrada
        ], capture_output=True, text=True, timeout=30, check=True)
        duracao = float(result.stdout.strip() or '0')
    except Exception:
        duracao = 0

    # Bitrate dinâmico: manter resultado ≤ 490KB (com margem de 10KB)
    if duracao > 0:
        bitrate = max(12, min(64, int(400 * 8 / duracao)))
    else:
        bitrate = 32  # fallback seguro quando ffprobe não detecta duração

    fd, caminho_saida = tempfile.mkstemp(suffix='_opus.ogg')
    os.close(fd)

    try:
        subprocess.run([
            'ffmpeg', '-y', '-i', caminho_entrada,
            '-c:a', 'libopus', '-b:a', f'{bitrate}k',
            '-ar', '48000', '-ac', '1',
            '-map_metadata', '-1',
            '-vn', caminho_saida
        ], capture_output=True, timeout=120, check=True)
    except subprocess.CalledProcessError:
        if os.path.exists(caminho_saida):
            os.remove(caminho_saida)
        return None, 'Erro na conversão. Verifique se o arquivo é um áudio válido.'
    except subprocess.TimeoutExpired:
        if os.path.exists(caminho_saida):
            os.remove(caminho_saida)
        return None, 'Conversão demorou demais. Tente um arquivo menor.'

    if os.path.getsize(caminho_saida) > 500 * 1024:
        os.remove(caminho_saida)
        return None, 'Áudio muito longo. Máximo suportado: aproximadamente 4 minutos.'

    return caminho_saida, None


def _listar_arquivos(subdir):
    pasta = os.path.join(current_app.static_folder, subdir)
    os.makedirs(pasta, exist_ok=True)
    resultado = []
    for nome in sorted(os.listdir(pasta)):
        caminho = os.path.join(pasta, nome)
        if not os.path.isfile(caminho):
            continue
        stat = os.stat(caminho)
        size = stat.st_size
        if size < 1024:
            tamanho_fmt = f'{size} B'
        elif size < 1024 * 1024:
            tamanho_fmt = f'{size / 1024:.1f} KB'
        else:
            tamanho_fmt = f'{size / (1024 * 1024):.1f} MB'
        resultado.append({
            'nome': nome,
            'tamanho_fmt': tamanho_fmt,
            'modificado_fmt': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M'),
        })
    return resultado


@admin_bp.route('/arquivos')
@requer_login
def listar_arquivos():
    aba = request.args.get('aba', 'pdf')
    if aba not in _UPLOAD_CONFIG:
        aba = 'pdf'
    pdfs     = _listar_arquivos('arquivos')
    audios   = _listar_arquivos('audios')
    imagens  = _listar_arquivos('images')
    base_url = os.getenv('APP_BASE_URL', request.host_url.rstrip('/')).rstrip('/')
    return render_template('admin/arquivos.html', aba=aba, pdfs=pdfs, audios=audios, imagens=imagens, base_url=base_url)


@admin_bp.route('/arquivos/upload', methods=['POST'])
@requer_admin
def upload_arquivo():
    tipo = request.form.get('tipo')
    if tipo not in _UPLOAD_CONFIG:
        flash('Tipo de arquivo inválido.', 'danger')
        return redirect(url_for('admin.listar_arquivos'))

    cfg     = _UPLOAD_CONFIG[tipo]
    arquivo = request.files.get('arquivo')

    if not arquivo or arquivo.filename == '':
        flash('Nenhum arquivo selecionado.', 'warning')
        return redirect(url_for('admin.listar_arquivos', aba=tipo))

    nome_original = secure_filename(arquivo.filename)
    ext           = os.path.splitext(nome_original)[1].lower()
    pasta         = os.path.join(current_app.static_folder, cfg['subdir'])
    os.makedirs(pasta, exist_ok=True)

    # ── PDF ────────────────────────────────────────────────────
    if tipo == 'pdf':
        if ext != cfg['ext']:
            flash('Extensão inválida. Use apenas .pdf.', 'danger')
            return redirect(url_for('admin.listar_arquivos', aba=tipo))

        cabecalho = arquivo.read(4)
        arquivo.seek(0)
        if cabecalho[:4] != cfg['magic']:
            flash('Arquivo inválido. O conteúdo não corresponde a um PDF.', 'danger')
            return redirect(url_for('admin.listar_arquivos', aba=tipo))

        arquivo.seek(0, 2)
        tamanho_mb = arquivo.tell() / (1024 * 1024)
        arquivo.seek(0)
        if tamanho_mb > cfg['max_mb']:
            flash(f'PDF muito grande. Máximo permitido: {cfg["max_mb"]}MB.', 'danger')
            return redirect(url_for('admin.listar_arquivos', aba=tipo))

        caminho = os.path.join(pasta, nome_original)
        arquivo.save(caminho)
        os.chmod(caminho, 0o644)
        logger.info(f"[ADMIN] ✅ PDF '{nome_original}' enviado por {current_user.email}")
        flash(f'PDF "{nome_original}" enviado com sucesso!', 'success')

    # ── Áudio (converte para OGG/Opus ≤ 500KB) ──────────────────
    elif tipo == 'audio':
        if ext not in _AUDIO_EXTS:
            flash(f'Formato não suportado. Use: {", ".join(sorted(_AUDIO_EXTS))}.', 'danger')
            return redirect(url_for('admin.listar_arquivos', aba=tipo))

        # Salvar arquivo de entrada em temp
        fd_in, caminho_temp = tempfile.mkstemp(suffix=ext)
        os.close(fd_in)
        nome_base  = os.path.splitext(nome_original)[0]
        nome_final = nome_base + '.ogg'
        destino    = os.path.join(pasta, nome_final)

        try:
            arquivo.save(caminho_temp)

            # Sempre re-encodar para garantir parâmetros compatíveis com WhatsApp
            caminho_opus, erro = _converter_para_opus(caminho_temp)
            if erro:
                flash(erro, 'danger')
                return redirect(url_for('admin.listar_arquivos', aba=tipo))
            try:
                os.replace(caminho_opus, destino)
            except Exception:
                import shutil
                shutil.move(caminho_opus, destino)
            os.chmod(destino, 0o644)
            tamanho_kb = os.path.getsize(destino) / 1024
            msg = f'Áudio "{nome_final}" convertido para OGG/Opus ({tamanho_kb:.0f} KB) e salvo com sucesso!'
        finally:
            if os.path.exists(caminho_temp):
                os.remove(caminho_temp)

        logger.info(f"[ADMIN] ✅ Áudio '{nome_final}' ({tamanho_kb:.0f}KB) enviado por {current_user.email}")
        flash(msg, 'success')

    # ── Imagem ───────────────────────────────────────────────────
    elif tipo == 'imagem':
        if ext not in _IMAGE_EXTS:
            flash(f'Formato não suportado. Use: {", ".join(sorted(_IMAGE_EXTS))}.', 'danger')
            return redirect(url_for('admin.listar_arquivos', aba=tipo))

        cabecalho = arquivo.read(256)
        arquivo.seek(0)
        valido = (
            cabecalho[:3] == b'\xff\xd8\xff'                                             or  # JPG
            cabecalho[:4] == b'\x89PNG'                                                  or  # PNG
            (cabecalho[:4] == b'RIFF' and cabecalho[8:12] == b'WEBP')                   or  # WEBP
            (ext == '.svg' and (b'<svg' in cabecalho.lower() or b'<?xml' in cabecalho.lower()))  # SVG
        )
        if not valido:
            flash('Arquivo inválido. O conteúdo não corresponde ao formato de imagem esperado.', 'danger')
            return redirect(url_for('admin.listar_arquivos', aba=tipo))

        arquivo.seek(0, 2)
        tamanho_mb = arquivo.tell() / (1024 * 1024)
        arquivo.seek(0)
        if tamanho_mb > cfg['max_mb']:
            flash(f'Imagem muito grande. Máximo permitido: {cfg["max_mb"]}MB.', 'danger')
            return redirect(url_for('admin.listar_arquivos', aba=tipo))

        caminho = os.path.join(pasta, nome_original)
        arquivo.save(caminho)
        os.chmod(caminho, 0o644)
        logger.info(f"[ADMIN] ✅ Imagem '{nome_original}' enviada por {current_user.email}")
        flash(f'Imagem "{nome_original}" enviada com sucesso!', 'success')

    return redirect(url_for('admin.listar_arquivos', aba=tipo))


@admin_bp.route('/arquivos/remover', methods=['POST'])
@requer_admin
def remover_arquivo():
    tipo = request.form.get('tipo')
    nome = request.form.get('nome', '')

    if tipo not in _UPLOAD_CONFIG or not nome:
        flash('Parâmetros inválidos.', 'danger')
        return redirect(url_for('admin.listar_arquivos'))

    nome_seguro = secure_filename(nome)
    if nome_seguro != nome:
        flash('Nome de arquivo inválido.', 'danger')
        return redirect(url_for('admin.listar_arquivos', aba=tipo))

    cfg     = _UPLOAD_CONFIG[tipo]
    caminho = os.path.join(current_app.static_folder, cfg['subdir'], nome_seguro)

    if not os.path.isfile(caminho):
        flash('Arquivo não encontrado.', 'danger')
        return redirect(url_for('admin.listar_arquivos', aba=tipo))

    os.remove(caminho)
    logger.info(f"[ADMIN] ✅ Arquivo '{nome_seguro}' removido por {current_user.email}")
    flash(f'Arquivo "{nome_seguro}" removido.', 'success')
    return redirect(url_for('admin.listar_arquivos', aba=tipo))


# ============================================================
# Analytics por produto
# ============================================================

_SQL_FUNIL = """
    SELECT
        COUNT(CASE WHEN estado_id IN (0,1,2,3,4) THEN 1 END) AS total_leads,
        COUNT(CASE WHEN estado_id IN (0,2,3,4) THEN 1 END)   AS mandaram_msg,
        COUNT(CASE WHEN estado_id IN (0,2,3,4) THEN 1 END)   AS responderam,
        COUNT(CASE WHEN estado_id IN (0,2,3,4) AND interesse_produto = 1 THEN 1 END) AS responderam_com_interesse,
        COUNT(CASE WHEN estado_id IN (0,2,3,4) AND interesse_produto = 0 THEN 1 END) AS responderam_sem_interesse,
        COUNT(CASE WHEN estado_id = 0 THEN 1 END)             AS pagaram,
        COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 1 THEN 1 END) AS pagaram_vindo_interesse_sim,
        COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 0 THEN 1 END) AS pagaram_vindo_interesse_nao,
        COUNT(CASE WHEN estado_id = 0 AND data_followup IS NULL THEN 1 END)     AS pagaram_sem_followup,
        COUNT(CASE WHEN estado_id = 0 AND data_followup IS NOT NULL THEN 1 END) AS pagaram_com_followup
    FROM pedidos
    WHERE produto_id = %s
      AND data_contato_site BETWEEN %s AND %s
"""

_SQL_RECEITA = """
    SELECT
        COUNT(*)                                                      AS total_pagamentos,
        COALESCE(SUM(valor_pago), 0)                                  AS total_receita,
        COUNT(CASE WHEN data_followup IS NOT NULL THEN 1 END)         AS com_followup,
        COALESCE(SUM(CASE WHEN data_followup IS NOT NULL THEN valor_pago END), 0) AS receita_com_followup,
        COUNT(CASE WHEN data_followup IS NULL THEN 1 END)             AS sem_followup,
        COALESCE(SUM(CASE WHEN data_followup IS NULL THEN valor_pago END), 0)     AS receita_sem_followup
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id = 0
      AND data_pagamento BETWEEN %s AND %s
"""

_SQL_CAMPANHAS = """
    SELECT
        COALESCE(c.nome, NULLIF(p.campaignid, ''), 'Campanha não informada') AS campanha,
        COUNT(*)                AS quantidade,
        COALESCE(SUM(p.valor_pago), 0) AS total
    FROM pedidos p
    LEFT JOIN campanhas c ON c.produto_id = p.produto_id AND c.campaignid = p.campaignid
    WHERE p.produto_id = %s
      AND p.estado_id = 0
      AND p.data_pagamento BETWEEN %s AND %s
    GROUP BY COALESCE(c.nome, NULLIF(p.campaignid, ''), 'Campanha não informada')
    ORDER BY total DESC
"""

_SQL_FUNIL_WEB = """
    SELECT
        COUNT(CASE WHEN estado_id IN (1000,1001,1002) THEN 1 END) AS total_pedidos,
        COUNT(CASE WHEN estado_id = 1000 THEN 1 END)              AS pagos
    FROM pedidos
    WHERE produto_id = %s
      AND data_contato_site BETWEEN %s AND %s
"""

_SQL_RECEITA_WEB = """
    SELECT
        COUNT(*)                     AS total_pagamentos,
        COALESCE(SUM(valor_pago), 0) AS total_receita
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id = 1000
      AND data_pagamento BETWEEN %s AND %s
"""

_SQL_CAMPANHAS_WEB = """
    SELECT
        COALESCE(c.nome, NULLIF(p.campaignid, ''), 'Campanha não informada') AS campanha,
        COUNT(*)                     AS quantidade,
        COALESCE(SUM(p.valor_pago), 0) AS total
    FROM pedidos p
    LEFT JOIN campanhas c ON c.produto_id = p.produto_id AND c.campaignid = p.campaignid
    WHERE p.produto_id = %s
      AND p.estado_id = 1000
      AND p.data_pagamento BETWEEN %s AND %s
    GROUP BY COALESCE(c.nome, NULLIF(p.campaignid, ''), 'Campanha não informada')
    ORDER BY total DESC
"""


# ── Analytics Pro ─────────────────────────────────────────────────────────────

_SQL_PRO_FUNIL = """
    SELECT
        COUNT(*)                                                                                    AS visitantes,
        COUNT(CASE WHEN estado_id IN (0,2,3,4) THEN 1 END)                                         AS whatsapp,
        COUNT(CASE WHEN estado_id IN (0,2,3,4) AND interesse_produto IS NOT NULL THEN 1 END)        AS responderam,
        COUNT(CASE WHEN estado_id = 0 THEN 1 END)                                                   AS pagaram,
        COUNT(CASE WHEN estado_id IN (0,2,3,4) AND interesse_produto = 1 THEN 1 END)                AS com_interesse,
        COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 1 THEN 1 END)                         AS ci_pagou,
        COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 1 AND data_followup IS NULL THEN 1 END)     AS ci_pagou_sem_fup,
        COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 1 AND data_followup IS NOT NULL THEN 1 END) AS ci_pagou_com_fup,
        COUNT(CASE WHEN estado_id IN (2,3,4) AND interesse_produto = 1 THEN 1 END)                  AS ci_nao_pagou,
        COUNT(CASE WHEN estado_id IN (0,2,3,4) AND interesse_produto = 0 THEN 1 END)                AS sem_interesse,
        COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 0 THEN 1 END)                         AS si_pagou,
        COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 0 AND data_followup_interesse_1 IS NULL THEN 1 END)                                               AS si_pag_sem_engaj,
        COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 0 AND data_followup_interesse_1 IS NOT NULL AND data_followup_interesse_2 IS NULL THEN 1 END)     AS si_pag_com_engaj1,
        COUNT(CASE WHEN estado_id = 0 AND interesse_produto = 0 AND data_followup_interesse_2 IS NOT NULL THEN 1 END)                                           AS si_pag_com_engaj2,
        COUNT(CASE WHEN estado_id IN (2,3,4) AND interesse_produto = 0 THEN 1 END)                  AS si_nao_pagou,
        COUNT(CASE WHEN estado_id IN (2,3,4) AND interesse_produto IS NULL THEN 1 END)               AS sem_resposta,
        COUNT(CASE WHEN estado_id IN (2,3,4) AND interesse_produto IS NULL AND data_followup_interesse_1 IS NULL THEN 1 END)                                    AS sr_dropoff,
        COUNT(CASE WHEN estado_id IN (2,3,4) AND interesse_produto IS NULL AND data_followup_interesse_1 IS NOT NULL AND data_followup_interesse_2 IS NULL THEN 1 END) AS sr_fup1,
        COUNT(CASE WHEN estado_id IN (2,3,4) AND interesse_produto IS NULL AND data_followup_interesse_2 IS NOT NULL THEN 1 END)                                AS sr_fup2
    FROM pedidos
    WHERE produto_id = %s
      AND data_contato_site BETWEEN %s AND %s
"""

_SQL_PRO_RECEITA = """
    SELECT
        COUNT(*)                                                                    AS total_pagamentos,
        COALESCE(SUM(valor_pago), 0)                                                AS total_receita,
        COUNT(CASE WHEN interesse_produto = 1 THEN 1 END)                           AS ci_pagamentos,
        COALESCE(SUM(CASE WHEN interesse_produto = 1 THEN valor_pago END), 0)       AS ci_receita,
        COUNT(CASE WHEN interesse_produto = 0 THEN 1 END)                           AS si_pagamentos,
        COALESCE(SUM(CASE WHEN interesse_produto = 0 THEN valor_pago END), 0)       AS si_receita,
        COUNT(CASE WHEN data_followup IS NOT NULL THEN 1 END)                       AS com_followup_pgto,
        COALESCE(SUM(CASE WHEN data_followup IS NOT NULL THEN valor_pago END), 0)   AS receita_com_followup
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id = 0
      AND data_pagamento BETWEEN %s AND %s
"""

_SQL_PRO_INVESTIMENTO = """
    SELECT
        COALESCE(SUM(valor_investido), 0) AS total_investido,
        COALESCE(SUM(cliques), 0)         AS total_cliques,
        COALESCE(SUM(impressoes), 0)      AS total_impressoes
    FROM orcamento_campanha
    WHERE produto_id = %s
      AND data BETWEEN %s AND %s
"""

_SQL_PRO_CAMP_INV = """
    SELECT campaignid,
           SUM(valor_investido)          AS valor_investido,
           COALESCE(SUM(cliques), 0)     AS cliques,
           COALESCE(SUM(impressoes), 0)  AS impressoes
    FROM orcamento_campanha
    WHERE produto_id = %s AND data BETWEEN %s AND %s
    GROUP BY campaignid
"""

_SQL_PRO_CAMP_FUNIL = """
    SELECT campaignid,
           COUNT(*)                                                                         AS visitantes,
           COUNT(CASE WHEN estado_id IN (0,2,3,4) THEN 1 END)                              AS whatsapp,
           COUNT(CASE WHEN estado_id IN (0,2,3,4) AND interesse_produto IS NOT NULL THEN 1 END) AS responderam
    FROM pedidos
    WHERE produto_id = %s AND data_contato_site BETWEEN %s AND %s
    GROUP BY campaignid
"""

_SQL_PRO_CAMP_PAG = """
    SELECT campaignid,
           COUNT(*)                      AS pagaram,
           COALESCE(SUM(valor_pago), 0)  AS receita
    FROM pedidos
    WHERE produto_id = %s AND estado_id = 0 AND data_pagamento BETWEEN %s AND %s
    GROUP BY campaignid
"""

_SQL_PRO_CAMP_NOMES = """
    SELECT campaignid, nome FROM campanhas WHERE produto_id = %s
"""


@admin_bp.route('/produto/<int:produto_id>/analytics-pro')
@requer_acesso_produto
def analytics_pro_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    ontem = (_hoje_sao_paulo() - datetime.timedelta(days=1)).isoformat()
    data_ini_str = request.args.get('data_ini', ontem)
    data_fim_str = request.args.get('data_fim', ontem)

    try:
        data_ini = datetime.datetime.fromisoformat(data_ini_str)
        data_fim = datetime.datetime.fromisoformat(data_fim_str) + datetime.timedelta(days=1, seconds=-1)
    except ValueError:
        ontem_dt = _hoje_sao_paulo() - datetime.timedelta(days=1)
        data_ini = datetime.datetime.combine(ontem_dt, datetime.time.min)
        data_fim  = datetime.datetime.combine(ontem_dt, datetime.time.max)
        data_ini_str = data_fim_str = ontem

    data_ini_date = data_ini.date().isoformat()
    data_fim_date = data_fim.date().isoformat()

    funil = receita = investimento = None
    campanhas_pro = []

    try:
        funil        = db.execute_query(_SQL_PRO_FUNIL,        (produto_id, data_ini, data_fim), fetch_one=True)
        receita      = db.execute_query(_SQL_PRO_RECEITA,      (produto_id, data_ini, data_fim), fetch_one=True)
        investimento = db.execute_query(_SQL_PRO_INVESTIMENTO, (produto_id, data_ini_date, data_fim_date), fetch_one=True)

        camp_inv   = db.execute_query(_SQL_PRO_CAMP_INV,   (produto_id, data_ini_date, data_fim_date), fetch_all=True)
        camp_funil = db.execute_query(_SQL_PRO_CAMP_FUNIL, (produto_id, data_ini, data_fim), fetch_all=True)
        camp_pag   = db.execute_query(_SQL_PRO_CAMP_PAG,   (produto_id, data_ini, data_fim), fetch_all=True)
        camp_nomes = db.execute_query(_SQL_PRO_CAMP_NOMES, (produto_id,), fetch_all=True)

        nomes  = {r['campaignid']: r['nome'] for r in (camp_nomes or [])}
        merged = {}
        for r in (camp_inv or []):
            cid = r['campaignid'] or ''
            merged.setdefault(cid, {})['valor_investido'] = float(r['valor_investido'] or 0)
            merged[cid]['cliques']    = int(r['cliques']    or 0)
            merged[cid]['impressoes'] = int(r['impressoes'] or 0)
        for r in (camp_funil or []):
            cid = r['campaignid'] or ''
            merged.setdefault(cid, {}).update({
                'visitantes':  int(r['visitantes']  or 0),
                'whatsapp':    int(r['whatsapp']    or 0),
                'responderam': int(r['responderam'] or 0),
            })
        for r in (camp_pag or []):
            cid = r['campaignid'] or ''
            merged.setdefault(cid, {}).update({
                'pagaram': int(r['pagaram'] or 0),
                'receita': float(r['receita'] or 0),
            })
        for cid, row in merged.items():
            row['campanha']       = nomes.get(cid) or (cid if cid else 'Sem campanha')
            row.setdefault('valor_investido', 0.0)
            row.setdefault('cliques', 0)
            row.setdefault('impressoes', 0)
            row.setdefault('visitantes', 0)
            row.setdefault('whatsapp', 0)
            row.setdefault('responderam', 0)
            row.setdefault('pagaram', 0)
            row.setdefault('receita', 0.0)
            inv = row['valor_investido']
            pag = row['pagaram']
            rec = row['receita']
            vis = row['visitantes']
            imp = row['impressoes']
            cli = row['cliques']
            row['roas']         = round(rec / inv, 2) if inv > 0 else None
            row['cpa']          = round(inv / pag, 2) if pag > 0 else None
            row['conv_vis_pag'] = round(pag / vis * 100, 1) if vis > 0 else 0.0
            row['ctr']          = round(cli / imp * 100, 2) if imp > 0 and imp >= cli else None
            row['cpm']          = round(inv / imp * 1000, 2) if imp > 0 else None
        campanhas_pro = sorted(merged.values(), key=lambda x: x['receita'], reverse=True)

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro analytics pro produto #{produto_id}: {e}")
        flash('Erro ao carregar Analytics Pro.', 'danger')

    m = {}
    if funil:
        v  = funil['visitantes']    or 0
        w  = funil['whatsapp']      or 0
        r  = funil['responderam']   or 0
        p  = funil['pagaram']       or 0
        ci = funil['com_interesse'] or 0
        si = funil['sem_interesse'] or 0
        sr = funil['sem_resposta']  or 0
        m['pct_visita_whats']   = round(w / v * 100, 1) if v else 0.0
        m['pct_whats_resp']     = round(r / w * 100, 1) if w else 0.0
        m['pct_resp_pagaram']   = round(p / r * 100, 1) if r else 0.0
        m['pct_visita_pagaram'] = round(p / v * 100, 1) if v else 0.0
        m['pct_ci']             = round(ci / w * 100, 1) if w else 0.0
        m['pct_si']             = round(si / w * 100, 1) if w else 0.0
        m['pct_sr']             = round(sr / w * 100, 1) if w else 0.0
        ci_p = funil['ci_pagou'] or 0
        si_p = funil['si_pagou'] or 0
        m['pct_ci_pagou']  = round(ci_p / ci * 100, 1) if ci else 0.0
        m['pct_si_pagou']  = round(si_p / si * 100, 1) if si else 0.0
        m['pct_pag_de_ci'] = round(ci_p / p * 100, 1)  if p  else 0.0
        m['pct_pag_de_si'] = round(si_p / p * 100, 1)  if p  else 0.0

    m['ticket_medio']    = 0.0
    m['roas']            = None
    m['total_investido'] = 0.0
    m['total_cliques']   = 0
    m['total_impressoes']= 0
    m['ctr_total']       = None
    m['cpm_total']       = None

    if receita and receita['total_pagamentos']:
        m['ticket_medio'] = float(receita['total_receita']) / receita['total_pagamentos']
    if investimento:
        m['total_investido']  = float(investimento['total_investido'])
        m['total_cliques']    = int(investimento['total_cliques']    or 0)
        m['total_impressoes'] = int(investimento['total_impressoes'] or 0)
        if m['total_investido'] > 0 and receita:
            m['roas'] = round(float(receita['total_receita']) / m['total_investido'], 2)
        ti = m['total_impressoes']
        tc = m['total_cliques']
        if ti > 0 and ti >= tc:
            m['ctr_total'] = round(tc / ti * 100, 2)
        if ti > 0 and m['total_investido'] > 0:
            m['cpm_total'] = round(m['total_investido'] / ti * 1000, 2)

    chart_receita = {
        'labels': ['Com Interesse', 'Sem Interesse'],
        'valores': [
            float(receita['ci_receita']) if receita else 0,
            float(receita['si_receita']) if receita else 0,
        ],
        'cores': ['#4a9632', '#e07b2a'],
    }

    return render_template('admin/produto_analytics_pro.html',
        produto=produto, funil=funil, receita=receita,
        investimento=investimento, campanhas_pro=campanhas_pro,
        m=m, chart_receita=chart_receita,
        data_ini=data_ini_str, data_fim=data_fim_str,
    )


@admin_bp.route('/produto/<int:produto_id>/analytics-pro/analisar', methods=['POST'])
@requer_acesso_produto
def analisar_campanhas_pro(produto_id):
    from agente_analisa_campanhas import analisar as _analisar

    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return {'erro': 'Produto não encontrado.'}, 404

    ontem = (_hoje_sao_paulo() - datetime.timedelta(days=1)).isoformat()
    data_ini_str = request.form.get('data_ini', ontem)
    data_fim_str = request.form.get('data_fim', ontem)

    try:
        data_ini = datetime.datetime.fromisoformat(data_ini_str)
        data_fim = datetime.datetime.fromisoformat(data_fim_str) + datetime.timedelta(days=1, seconds=-1)
    except ValueError:
        ontem_dt = _hoje_sao_paulo() - datetime.timedelta(days=1)
        data_ini = datetime.datetime.combine(ontem_dt, datetime.time.min)
        data_fim  = datetime.datetime.combine(ontem_dt, datetime.time.max)
        data_ini_str = data_fim_str = ontem

    data_ini_date = data_ini.date().isoformat()
    data_fim_date = data_fim.date().isoformat()

    try:
        camp_inv   = db.execute_query(_SQL_PRO_CAMP_INV,   (produto_id, data_ini_date, data_fim_date), fetch_all=True)
        camp_funil = db.execute_query(_SQL_PRO_CAMP_FUNIL, (produto_id, data_ini, data_fim), fetch_all=True)
        camp_pag   = db.execute_query(_SQL_PRO_CAMP_PAG,   (produto_id, data_ini, data_fim), fetch_all=True)
        camp_nomes = db.execute_query(_SQL_PRO_CAMP_NOMES, (produto_id,), fetch_all=True)
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro analisar campanhas #{produto_id}: {e}")
        return {'erro': 'Erro ao buscar dados das campanhas.'}, 500

    nomes  = {r['campaignid']: r['nome'] for r in (camp_nomes or [])}
    merged = {}
    for r in (camp_inv or []):
        cid = r['campaignid'] or ''
        merged.setdefault(cid, {})['valor_investido'] = float(r['valor_investido'] or 0)
        merged[cid]['cliques']    = int(r['cliques']    or 0)
        merged[cid]['impressoes'] = int(r['impressoes'] or 0)
    for r in (camp_funil or []):
        cid = r['campaignid'] or ''
        merged.setdefault(cid, {}).update({
            'visitantes':  int(r['visitantes']  or 0),
            'whatsapp':    int(r['whatsapp']    or 0),
            'responderam': int(r['responderam'] or 0),
        })
    for r in (camp_pag or []):
        cid = r['campaignid'] or ''
        merged.setdefault(cid, {}).update({
            'pagaram': int(r['pagaram'] or 0),
            'receita': float(r['receita'] or 0),
        })

    campanhas_completas = []
    for cid, row in merged.items():
        row['campanha']       = nomes.get(cid) or (cid if cid else 'Sem campanha')
        row.setdefault('valor_investido', 0.0)
        row.setdefault('cliques', 0)
        row.setdefault('impressoes', 0)
        row.setdefault('visitantes', 0)
        row.setdefault('whatsapp', 0)
        row.setdefault('responderam', 0)
        row.setdefault('pagaram', 0)
        row.setdefault('receita', 0.0)

        if not (row['impressoes'] > 0 and row['cliques'] > 0
                and row['visitantes'] > 0 and row['valor_investido'] > 0):
            continue

        inv = row['valor_investido']
        imp = row['impressoes']
        cli = row['cliques']
        vis = row['visitantes']
        wha = row['whatsapp']
        res = row['responderam']
        pag = row['pagaram']
        rec = row['receita']

        row['ctr']         = round(cli / imp * 100, 2) if imp >= cli else None
        row['landing_pct'] = round(vis / cli * 100, 1) if cli > 0 else None
        row['engaj_pct']   = round(wha / vis * 100, 1) if vis > 0 else None
        row['resp_pct']    = round(res / wha * 100, 1) if wha > 0 else None
        row['conv_pct']    = round(pag / res * 100, 1) if res > 0 else None
        row['roas']        = round(rec / inv, 2) if inv > 0 else None
        row['cpa']         = round(inv / pag, 2) if pag > 0 else None
        row['cpm']         = round(inv / imp * 1000, 2) if imp > 0 else None
        campanhas_completas.append(row)

    if not campanhas_completas:
        return {'analise': 'Nenhuma campanha tem dados completos (impressões + cliques + visitantes + investido) para o período selecionado. Preencha os dados em Orçamento.'}, 200

    periodo_str = data_ini_str if data_ini_str == data_fim_str else f"{data_ini_str} a {data_fim_str}"
    analise = _analisar(produto['nome'], periodo_str, campanhas_completas)

    logger.info(f"[ADMIN] ✅ Análise de campanhas gerada para produto #{produto_id} por {current_user.email}")
    return {'analise': analise}, 200


@admin_bp.route('/produto/<int:produto_id>/analytics')
@requer_acesso_produto
def analytics_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    hoje = _hoje_sao_paulo()
    data_ini_str = request.args.get('data_ini', hoje.isoformat())
    data_fim_str = request.args.get('data_fim', hoje.isoformat())

    try:
        data_ini = datetime.datetime.fromisoformat(data_ini_str)
        data_fim = datetime.datetime.fromisoformat(data_fim_str) + datetime.timedelta(days=1, seconds=-1)
    except ValueError:
        data_ini = datetime.datetime.combine(hoje, datetime.time.min)
        data_fim  = datetime.datetime.combine(hoje, datetime.time.max)
        data_ini_str = data_fim_str = hoje.isoformat()

    try:
        funil     = db.execute_query(_SQL_FUNIL,     (produto_id, data_ini, data_fim), fetch_one=True)
        receita   = db.execute_query(_SQL_RECEITA,   (produto_id, data_ini, data_fim), fetch_one=True)
        campanhas = db.execute_query(_SQL_CAMPANHAS, (produto_id, data_ini, data_fim), fetch_all=True)
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro no analytics produto #{produto_id}: {e}")
        flash('Erro ao carregar analytics.', 'danger')
        funil = receita = None
        campanhas = []

    # Calcular percentuais de conversão do funil
    conv_1_2 = 0.0  # Saber mais → Mandaram msg
    conv_3_com = 0.0  # % Com interesse
    conv_3_sem = 0.0  # % Sem interesse
    conv_interesse_sim_paga = 0.0  # COM interesse → Pagaram
    conv_interesse_nao_paga = 0.0  # SEM interesse → Pagaram (estratégia de presente)
    conv_responderam_pagaram = 0.0  # Responderam (total) → Pagaram (conversão geral)
    pct_pagaram_interesse_sim = 0.0  # % dos pagamentos que vieram de COM interesse
    pct_pagaram_interesse_nao = 0.0  # % dos pagamentos que vieram de SEM interesse
    conv_4_sem_followup = 0.0  # % Sem followup
    conv_4_com_followup = 0.0  # % Com followup
    ticket_medio = 0.0

    if funil:
        if funil['total_leads'] > 0:
            conv_1_2 = round((funil['mandaram_msg'] / funil['total_leads']) * 100, 1)

        if funil['responderam'] > 0:
            conv_3_com = round((funil['responderam_com_interesse'] / funil['responderam']) * 100, 1)
            conv_3_sem = round((funil['responderam_sem_interesse'] / funil['responderam']) * 100, 1)

            # Conversão geral: responderam → pagaram
            conv_responderam_pagaram = round((funil['pagaram'] / funil['responderam']) * 100, 1)

        # Conversão de cada grupo para pagamento
        if funil['responderam_com_interesse'] > 0:
            conv_interesse_sim_paga = round((funil['pagaram_vindo_interesse_sim'] / funil['responderam_com_interesse']) * 100, 1)

        if funil['responderam_sem_interesse'] > 0:
            conv_interesse_nao_paga = round((funil['pagaram_vindo_interesse_nao'] / funil['responderam_sem_interesse']) * 100, 1)

        # Distribuição de origem dos pagamentos
        if funil['pagaram'] > 0:
            pct_pagaram_interesse_sim = round((funil['pagaram_vindo_interesse_sim'] / funil['pagaram']) * 100, 1)
            pct_pagaram_interesse_nao = round((funil['pagaram_vindo_interesse_nao'] / funil['pagaram']) * 100, 1)
            conv_4_sem_followup = round((funil['pagaram_sem_followup'] / funil['pagaram']) * 100, 1)
            conv_4_com_followup = round((funil['pagaram_com_followup'] / funil['pagaram']) * 100, 1)

    if receita and receita['total_pagamentos']:
        ticket_medio = float(receita['total_receita']) / receita['total_pagamentos']

    return render_template('admin/produto_analytics.html',
        produto        = produto,
        funil          = funil,
        receita        = receita,
        campanhas      = campanhas,
        data_ini       = data_ini_str,
        data_fim       = data_fim_str,
        ticket_medio   = ticket_medio,
        # Percentuais do funil
        conv_1_2       = conv_1_2,
        conv_3_com     = conv_3_com,
        conv_3_sem     = conv_3_sem,
        conv_interesse_sim_paga = conv_interesse_sim_paga,
        conv_interesse_nao_paga = conv_interesse_nao_paga,
        conv_responderam_pagaram = conv_responderam_pagaram,
        pct_pagaram_interesse_sim = pct_pagaram_interesse_sim,
        pct_pagaram_interesse_nao = pct_pagaram_interesse_nao,
        conv_4_sem_followup = conv_4_sem_followup,
        conv_4_com_followup = conv_4_com_followup,
    )


@admin_bp.route('/produto/<int:produto_id>/analytics-web')
@requer_acesso_produto
def analytics_web_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    hoje = _hoje_sao_paulo()
    data_ini_str = request.args.get('data_ini', hoje.isoformat())
    data_fim_str = request.args.get('data_fim', hoje.isoformat())

    try:
        data_ini = datetime.datetime.fromisoformat(data_ini_str)
        data_fim = datetime.datetime.fromisoformat(data_fim_str) + datetime.timedelta(days=1, seconds=-1)
    except ValueError:
        data_ini = datetime.datetime.combine(hoje, datetime.time.min)
        data_fim  = datetime.datetime.combine(hoje, datetime.time.max)
        data_ini_str = data_fim_str = hoje.isoformat()

    try:
        funil     = db.execute_query(_SQL_FUNIL_WEB,     (produto_id, data_ini, data_fim), fetch_one=True)
        receita   = db.execute_query(_SQL_RECEITA_WEB,   (produto_id, data_ini, data_fim), fetch_one=True)
        campanhas = db.execute_query(_SQL_CAMPANHAS_WEB, (produto_id, data_ini, data_fim), fetch_all=True)
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro no analytics web produto #{produto_id}: {e}")
        flash('Erro ao carregar analytics web.', 'danger')
        funil = receita = None
        campanhas = []

    conv_pedidos_pagos = 0.0
    ticket_medio = 0.0

    if funil and funil['total_pedidos'] > 0:
        conv_pedidos_pagos = round((funil['pagos'] / funil['total_pedidos']) * 100, 1)

    if receita and receita['total_pagamentos']:
        ticket_medio = float(receita['total_receita']) / receita['total_pagamentos']

    return render_template('admin/produto_analytics_web.html',
        produto            = produto,
        funil              = funil,
        receita            = receita,
        campanhas          = campanhas,
        data_ini           = data_ini_str,
        data_fim           = data_fim_str,
        ticket_medio       = ticket_medio,
        conv_pedidos_pagos = conv_pedidos_pagos,
    )


# ── Campanhas ─────────────────────────────────────────────────────────────────

_SQL_LISTA_CAMPANHAS = """
    SELECT
        p.campaignid,
        c.nome,
        COUNT(*) AS total_pedidos
    FROM pedidos p
    LEFT JOIN campanhas c ON c.produto_id = p.produto_id AND c.campaignid = p.campaignid
    WHERE p.produto_id = %s
      AND p.campaignid IS NOT NULL AND p.campaignid != ''
    GROUP BY p.campaignid
    ORDER BY total_pedidos DESC
"""


@admin_bp.route('/produto/<int:produto_id>/campanhas')
@requer_acesso_produto
def campanhas_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))
    campanhas = db.execute_query(_SQL_LISTA_CAMPANHAS, (produto_id,), fetch_all=True)
    return render_template('admin/campanhas_produto.html', produto=produto, campanhas=campanhas)


@admin_bp.route('/produto/<int:produto_id>/campanhas/salvar', methods=['POST'])
@requer_acesso_produto
def salvar_campanha(produto_id):
    campaignid = request.form.get('campaignid', '').strip()
    nome = request.form.get('nome', '').strip()
    if not campaignid or not nome:
        flash('Informe o Campaign ID e o nome.', 'warning')
        return redirect(url_for('admin.campanhas_produto', produto_id=produto_id))
    try:
        db.execute_query(
            """INSERT INTO campanhas (produto_id, campaignid, nome)
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE nome = VALUES(nome)""",
            (produto_id, campaignid, nome)
        )
        flash(f'Nome "{nome}" salvo para a campanha {campaignid}.', 'success')
        logger.info(f"[ADMIN] ✅ Campanha {campaignid} → '{nome}' salva no produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao salvar campanha: {e}")
        flash(f'Erro ao salvar campanha: {e}', 'danger')
    return redirect(url_for('admin.campanhas_produto', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/campanhas/remover', methods=['POST'])
@requer_acesso_produto
def remover_campanha(produto_id):
    campaignid = request.form.get('campaignid', '').strip()
    if not campaignid:
        flash('Campaign ID não informado.', 'warning')
        return redirect(url_for('admin.campanhas_produto', produto_id=produto_id))
    try:
        db.execute_query(
            "DELETE FROM campanhas WHERE produto_id = %s AND campaignid = %s",
            (produto_id, campaignid)
        )
        flash(f'Nome removido da campanha {campaignid}.', 'success')
        logger.info(f"[ADMIN] ✅ Nome da campanha {campaignid} removido do produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover campanha: {e}")
        flash(f'Erro ao remover campanha: {e}', 'danger')
    return redirect(url_for('admin.campanhas_produto', produto_id=produto_id))


# ── Orçamento de Campanhas ────────────────────────────────────────────────────

_SQL_LISTA_ORCAMENTO = """
    SELECT
        base.campaignid,
        COALESCE(cam.nome, base.campaignid) AS campanha,
        orc.valor_investido,
        orc.cliques,
        orc.impressoes
    FROM (
        SELECT campaignid FROM pedidos
        WHERE produto_id = %s AND DATE(data_contato_site) = %s
          AND campaignid IS NOT NULL AND campaignid != ''
        UNION
        SELECT campaignid FROM orcamento_campanha
        WHERE produto_id = %s AND data = %s
        UNION
        SELECT campaignid FROM campanhas
        WHERE produto_id = %s
    ) base
    LEFT JOIN campanhas cam
        ON cam.produto_id = %s AND cam.campaignid = base.campaignid
    LEFT JOIN orcamento_campanha orc
        ON orc.produto_id = %s AND orc.campaignid = base.campaignid AND orc.data = %s
    ORDER BY campanha
"""

_SQL_ROI = """
    SELECT
        base.campaignid,
        COALESCE(cam.nome, base.campaignid, 'Campanha não informada') AS campanha,
        COALESCE(ped.total_vendido,   0) AS valor_vendido,
        COALESCE(orc.total_investido, 0) AS valor_investido
    FROM (
        SELECT campaignid FROM pedidos
        WHERE produto_id = %s AND data_pagamento BETWEEN %s AND %s
          AND campaignid IS NOT NULL AND campaignid != ''
        UNION
        SELECT campaignid FROM orcamento_campanha
        WHERE produto_id = %s AND data BETWEEN %s AND %s
    ) base
    LEFT JOIN (
        SELECT campaignid, SUM(valor_pago) AS total_vendido
        FROM pedidos
        WHERE produto_id = %s AND estado_id = 0 AND data_pagamento BETWEEN %s AND %s
        GROUP BY campaignid
    ) ped ON ped.campaignid = base.campaignid
    LEFT JOIN (
        SELECT campaignid, SUM(valor_investido) AS total_investido
        FROM orcamento_campanha
        WHERE produto_id = %s AND data BETWEEN %s AND %s
        GROUP BY campaignid
    ) orc ON orc.campaignid = base.campaignid
    LEFT JOIN campanhas cam
        ON cam.produto_id = %s AND cam.campaignid = base.campaignid
    ORDER BY valor_vendido DESC
"""

_SQL_ROI_REAL = """
    SELECT
        COALESCE((
            SELECT SUM(pp.valor)
            FROM pagamento_pix pp
            WHERE pp.produto_id = %s
              AND pp.horario BETWEEN %s AND %s
        ), 0) AS total_pix,
        COALESCE((
            SELECT SUM(oc.valor_investido)
            FROM orcamento_campanha oc
            WHERE oc.produto_id = %s
              AND oc.data BETWEEN %s AND %s
        ), 0) AS total_investido
"""


@admin_bp.route('/produto/<int:produto_id>/orcamento')
@requer_acesso_produto
def orcamento_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    hoje = _hoje_sao_paulo().isoformat()
    data_str = request.args.get('data', hoje)
    try:
        datetime.date.fromisoformat(data_str)
    except ValueError:
        data_str = hoje

    orcamentos = db.execute_query(
        _SQL_LISTA_ORCAMENTO,
        (produto_id, data_str, produto_id, data_str, produto_id, produto_id, produto_id, data_str),
        fetch_all=True
    )
    return render_template('admin/orcamento_produto.html',
        produto=produto, orcamentos=orcamentos, data_selecionada=data_str)


@admin_bp.route('/produto/<int:produto_id>/orcamento/salvar', methods=['POST'])
@requer_acesso_produto
def salvar_orcamento(produto_id):
    campaignid = request.form.get('campaignid', '').strip()
    data_str   = request.form.get('data', '').strip()
    valor_str  = request.form.get('valor_investido', '').strip()
    if not campaignid or not data_str or not valor_str:
        flash('Informe campanha, data e valor.', 'warning')
        return redirect(url_for('admin.orcamento_produto', produto_id=produto_id, data=data_str))
    try:
        valor = float(valor_str)
        if valor < 0:
            raise ValueError
    except ValueError:
        flash('Valor inválido.', 'warning')
        return redirect(url_for('admin.orcamento_produto', produto_id=produto_id, data=data_str))
    cliques_str = request.form.get('cliques', '').strip()
    cliques = int(cliques_str) if cliques_str.isdigit() else None
    impressoes_str = request.form.get('impressoes', '').strip()
    impressoes = int(impressoes_str) if impressoes_str.isdigit() else None
    try:
        db.execute_query(
            """INSERT INTO orcamento_campanha (produto_id, campaignid, data, valor_investido, cliques, impressoes)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                   valor_investido = VALUES(valor_investido),
                   cliques         = VALUES(cliques),
                   impressoes      = VALUES(impressoes)""",
            (produto_id, campaignid, data_str, valor, cliques, impressoes)
        )
        flash(f'Investimento de R$ {valor:.2f} salvo para {data_str}.', 'success')
        logger.info(f"[ADMIN] ✅ Orçamento {campaignid} {data_str} R${valor:.2f} salvo no produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao salvar orçamento: {e}")
        flash(f'Erro ao salvar: {e}', 'danger')
    return redirect(url_for('admin.orcamento_produto', produto_id=produto_id, data=data_str))


@admin_bp.route('/produto/<int:produto_id>/orcamento/remover', methods=['POST'])
@requer_acesso_produto
def remover_orcamento(produto_id):
    campaignid = request.form.get('campaignid', '').strip()
    data_str   = request.form.get('data', '').strip()
    if not campaignid or not data_str:
        flash('Dados insuficientes.', 'warning')
        return redirect(url_for('admin.orcamento_produto', produto_id=produto_id))
    try:
        db.execute_query(
            "DELETE FROM orcamento_campanha WHERE produto_id = %s AND campaignid = %s AND data = %s",
            (produto_id, campaignid, data_str)
        )
        flash('Investimento removido.', 'success')
        logger.info(f"[ADMIN] ✅ Orçamento {campaignid} {data_str} removido do produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover orçamento: {e}")
        flash(f'Erro ao remover: {e}', 'danger')
    return redirect(url_for('admin.orcamento_produto', produto_id=produto_id, data=data_str))


@admin_bp.route('/produto/<int:produto_id>/roi')
@requer_acesso_produto
def roi_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    hoje = _hoje_sao_paulo()
    data_ini_str = request.args.get('data_ini', hoje.isoformat())
    data_fim_str = request.args.get('data_fim', hoje.isoformat())

    try:
        data_ini = datetime.datetime.fromisoformat(data_ini_str)
        data_fim = datetime.datetime.fromisoformat(data_fim_str) + datetime.timedelta(days=1, seconds=-1)
    except ValueError:
        data_ini = datetime.datetime.combine(hoje, datetime.time.min)
        data_fim  = datetime.datetime.combine(hoje, datetime.time.max)
        data_ini_str = data_fim_str = hoje.isoformat()

    data_ini_date = data_ini.date().isoformat()
    data_fim_date = data_fim.date().isoformat()

    roi_real = {'total_pix': 0, 'total_investido': 0}
    roi_real_erro = False
    try:
        roi_real_row = db.execute_query(
            _SQL_ROI_REAL,
            (produto_id, data_ini, data_fim,
             produto_id, data_ini_date, data_fim_date),
            fetch_one=True
        )
        if roi_real_row:
            roi_real = roi_real_row
    except Exception as e:
        roi_real_erro = True
        roi_real = None
        logger.error(f"[ADMIN] ❌ Erro ao calcular ROI real do produto #{produto_id}: {e}")

    try:
        rows = db.execute_query(
            _SQL_ROI,
            (produto_id, data_ini, data_fim,
             produto_id, data_ini_date, data_fim_date,
             produto_id, data_ini, data_fim,
             produto_id, data_ini_date, data_fim_date,
             produto_id),
            fetch_all=True
        )
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro no ROI produto #{produto_id}: {e}")
        flash('Erro ao carregar ROI.', 'danger')
        rows = []

    return render_template('admin/roi_produto.html',
        produto=produto, rows=rows, roi_real=roi_real, roi_real_erro=roi_real_erro,
        data_ini=data_ini_str, data_fim=data_fim_str)


# ── Chaves PIX ────────────────────────────────────────────────────────────────

@admin_bp.route('/produto/<int:produto_id>/chaves-pix')
@requer_login
def chaves_pix_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))
    chaves = listar_chaves_pix_produto(produto_id)
    return render_template('admin/produto_chaves_pix.html', produto=produto, chaves=chaves)


@admin_bp.route('/produto/<int:produto_id>/chaves-pix/adicionar', methods=['POST'])
@requer_admin
def adicionar_chave_pix(produto_id):
    chave = request.form.get('chave_pix', '').strip()
    if not chave:
        flash('Informe a chave PIX.', 'warning')
        return redirect(url_for('admin.chaves_pix_produto', produto_id=produto_id))
    try:
        adicionar_chave_pix_produto(produto_id, chave)
        flash(f'Chave PIX "{chave}" adicionada com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ Chave PIX '{chave}' associada ao produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao adicionar chave PIX: {e}")
        flash(f'Erro ao adicionar chave PIX: {e}', 'danger')
    return redirect(url_for('admin.chaves_pix_produto', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/chaves-pix/<int:chave_id>/desativar', methods=['POST'])
@requer_admin
def desativar_chave_pix(produto_id, chave_id):
    try:
        desativar_chave_pix_produto(chave_id)
        flash('Chave PIX desativada.', 'success')
        logger.info(f"[ADMIN] ✅ Chave PIX #{chave_id} desativada do produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao desativar chave PIX: {e}")
        flash(f'Erro ao desativar chave PIX: {e}', 'danger')
    return redirect(url_for('admin.chaves_pix_produto', produto_id=produto_id))


# ── Planilhas Google Ads por DNS ─────────────────────────────────────────────

@admin_bp.route('/produto/<int:produto_id>/planilhas-google')
@requer_login
def planilhas_google_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))
    planilhas = listar_planilhas_dns_produto(produto_id)
    return render_template('admin/produto_planilhas_google.html', produto=produto, planilhas=planilhas)


@admin_bp.route('/produto/<int:produto_id>/planilhas-google/adicionar', methods=['POST'])
@requer_admin
def adicionar_planilha_google(produto_id):
    dns            = request.form.get('dns', '').strip()
    spreadsheet_id = request.form.get('spreadsheet_id', '').strip()
    sheet_name     = request.form.get('sheet_name', 'Página1').strip()
    conversion_name = request.form.get('conversion_name', '').strip()
    sa_env_var     = request.form.get('sa_env_var', '').strip()
    if not all([dns, spreadsheet_id, conversion_name, sa_env_var]):
        flash('Preencha todos os campos obrigatórios.', 'danger')
        return redirect(url_for('admin.planilhas_google_produto', produto_id=produto_id))
    try:
        adicionar_planilha_dns(produto_id, dns, spreadsheet_id, sheet_name, conversion_name, sa_env_var)
        flash(f'Planilha para "{dns}" adicionada.', 'success')
        logger.info(f"[ADMIN] ✅ Planilha Google DNS '{dns}' adicionada ao produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao adicionar planilha DNS: {e}")
        flash(f'Erro ao adicionar: {e}', 'danger')
    return redirect(url_for('admin.planilhas_google_produto', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/planilhas-google/<int:planilha_id>/editar', methods=['POST'])
@requer_admin
def editar_planilha_google(produto_id, planilha_id):
    dns            = request.form.get('dns', '').strip()
    spreadsheet_id = request.form.get('spreadsheet_id', '').strip()
    sheet_name     = request.form.get('sheet_name', 'Página1').strip()
    conversion_name = request.form.get('conversion_name', '').strip()
    sa_env_var     = request.form.get('sa_env_var', '').strip()
    ativo          = request.form.get('ativo') == '1'
    if not all([dns, spreadsheet_id, conversion_name, sa_env_var]):
        flash('Preencha todos os campos obrigatórios.', 'danger')
        return redirect(url_for('admin.planilhas_google_produto', produto_id=produto_id))
    try:
        atualizar_planilha_dns(planilha_id, dns, spreadsheet_id, sheet_name, conversion_name, sa_env_var, ativo)
        flash(f'Planilha para "{dns}" atualizada.', 'success')
        logger.info(f"[ADMIN] ✅ Planilha Google DNS #{planilha_id} editada no produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao editar planilha DNS: {e}")
        flash(f'Erro ao editar: {e}', 'danger')
    return redirect(url_for('admin.planilhas_google_produto', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/planilhas-google/<int:planilha_id>/remover', methods=['POST'])
@requer_admin
def remover_planilha_google(produto_id, planilha_id):
    try:
        remover_planilha_dns(planilha_id)
        flash('Planilha removida.', 'success')
        logger.info(f"[ADMIN] ✅ Planilha Google DNS #{planilha_id} removida do produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover planilha DNS: {e}")
        flash(f'Erro ao remover: {e}', 'danger')
    return redirect(url_for('admin.planilhas_google_produto', produto_id=produto_id))


# ── Financeiro PIX ────────────────────────────────────────────────────────────

@admin_bp.route('/produto/<int:produto_id>/financeiro')
@requer_acesso_produto
def financeiro_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    hoje = _hoje_sao_paulo()
    data_ini_str = request.args.get('data_ini', hoje.isoformat())
    data_fim_str = request.args.get('data_fim', hoje.isoformat())

    try:
        data_ini = datetime.datetime.fromisoformat(data_ini_str)
        data_fim = datetime.datetime.fromisoformat(data_fim_str) + datetime.timedelta(days=1, seconds=-1)
    except ValueError:
        data_ini = datetime.datetime.combine(hoje, datetime.time.min)
        data_fim  = datetime.datetime.combine(hoje, datetime.time.max)
        data_ini_str = data_fim_str = hoje.isoformat()

    try:
        financeiro = busca_financeiro_pix(produto_id, data_ini, data_fim)
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro no financeiro PIX produto #{produto_id}: {e}")
        flash('Erro ao carregar dados financeiros.', 'danger')
        financeiro = {'resumo': {'total_valor': 0, 'qtd_transacoes': 0, 'ticket_medio': 0}, 'transacoes': []}

    return render_template('admin/produto_financeiro.html',
        produto     = produto,
        financeiro  = financeiro,
        data_ini    = data_ini_str,
        data_fim    = data_fim_str,
    )


@admin_bp.route('/produto/<int:produto_id>/financeiro/atualizar-pix', methods=['POST'])
@requer_admin
def financeiro_atualizar_pix(produto_id):
    try:
        from celery_app import celery_app
        celery_app.send_task('tasks.processar_pagamentos_pix')
        return jsonify({'ok': True, 'msg': 'Busca de PIX iniciada. Aguarde alguns segundos e atualize a página.'})
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao disparar task PIX: {e}")
        return jsonify({'ok': False, 'msg': f'Erro ao iniciar busca: {e}'}), 500


# ── Pagamentos ────────────────────────────────────────────────────────────

PAGAMENTOS_POR_PAGINA = 50

_SQL_PAGAMENTOS_TOTAL = """
    SELECT COUNT(*) as total
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id = 0
      AND data_pagamento BETWEEN %s AND %s
"""

_SQL_PAGAMENTOS_LISTA = """
    SELECT
        id,
        data_contato_site,
        data_pagamento,
        data_followup,
        path_comprovante,
        contact_name,
        contact_phone,
        nome_pagador,
        valor_pago
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id = 0
      AND data_pagamento BETWEEN %s AND %s
    ORDER BY data_pagamento DESC
    LIMIT %s
    OFFSET %s
"""

_SQL_PAGAMENTOS_RECEITA = """
    SELECT SUM(valor_pago) AS receita_total
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id = 0
      AND data_pagamento BETWEEN %s AND %s
"""


@admin_bp.route('/produto/<int:produto_id>/pagamentos')
@requer_acesso_produto
def pagamentos_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    hoje = _hoje_sao_paulo()
    data_ini_str = request.args.get('data_ini', hoje.isoformat())
    data_fim_str = request.args.get('data_fim', hoje.isoformat())
    pagina_str = request.args.get('page', '1')

    try:
        data_ini = datetime.datetime.fromisoformat(data_ini_str)
        data_fim = datetime.datetime.fromisoformat(data_fim_str) + datetime.timedelta(days=1, seconds=-1)

        # Validar: data_ini não pode ser maior que data_fim
        if data_ini > data_fim:
            data_ini, data_fim = data_fim, data_ini
    except ValueError:
        data_ini = datetime.datetime.combine(hoje, datetime.time.min)
        data_fim = datetime.datetime.combine(hoje, datetime.time.max)
        data_ini_str = data_fim_str = hoje.isoformat()

    # Validar página
    try:
        pagina_atual = max(1, int(pagina_str))
    except (ValueError, TypeError):
        pagina_atual = 1

    try:
        # Contar total de registros
        total_result = db.execute_query(_SQL_PAGAMENTOS_TOTAL, (produto_id, data_ini, data_fim), fetch_one=True)
        total_registros = total_result['total'] if total_result else 0
        total_paginas = (total_registros + PAGAMENTOS_POR_PAGINA - 1) // PAGAMENTOS_POR_PAGINA or 1

        # Validar página (se for > total, redirecionar para última)
        if pagina_atual > total_paginas:
            return redirect(url_for('admin.pagamentos_produto',
                                  produto_id=produto_id,
                                  data_ini=data_ini_str,
                                  data_fim=data_fim_str,
                                  page=total_paginas))

        # Calcular offset
        offset = (pagina_atual - 1) * PAGAMENTOS_POR_PAGINA

        # Buscar pedidos da página
        pedidos = db.execute_query(
            _SQL_PAGAMENTOS_LISTA,
            (produto_id, data_ini, data_fim, PAGAMENTOS_POR_PAGINA, offset),
            fetch_all=True
        )

        # Buscar receita do período
        receita_result = db.execute_query(_SQL_PAGAMENTOS_RECEITA, (produto_id, data_ini, data_fim), fetch_one=True)
        receita_total = receita_result['receita_total'] or 0 if receita_result else 0
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao carregar pagamentos produto #{produto_id}: {e}")
        flash('Erro ao carregar pagamentos.', 'danger')
        pedidos = []
        receita_total = 0
        total_registros = 0
        total_paginas = 1
        pagina_atual = 1

    return render_template('admin/produto_pagamentos.html',
        produto=produto,
        pedidos=pedidos,
        data_ini=data_ini_str,
        data_fim=data_fim_str,
        receita_total=receita_total,
        pagina_atual=pagina_atual,
        total_paginas=total_paginas,
        total_registros=total_registros,
        pagamentos_por_pagina=PAGAMENTOS_POR_PAGINA,
    )


@admin_bp.route('/pedido/<int:pedido_id>/comprovante')
@requer_login
def visualizar_comprovante(pedido_id):
    """AJAX endpoint: retorna info do comprovante para modal"""
    try:
        # Get pedido
        pedido = get_pedido(pedido_id)
        if not pedido:
            logger.warning(f"[ADMIN] ⚠️ Pedido não encontrado para visualização de comprovante: pedido_id={pedido_id}")
            return jsonify({'ok': False, 'msg': 'Pedido não encontrado'}), 404

        # Verify user has access to produto (admin sempre pode)
        if (not current_user.is_admin()) and (not usuario_tem_acesso_produto(current_user.id, pedido['produto_id'])):
            logger.warning(f"[ADMIN] ⚠️ Acesso negado ao comprovante: user={current_user.email} pedido_id={pedido_id} produto_id={pedido['produto_id']}")
            return jsonify({'ok': False, 'msg': 'Acesso negado'}), 403

        # Check se tem comprovante
        path_comprovante = pedido.get('path_comprovante')
        if not path_comprovante:
            logger.warning(f"[ADMIN] ⚠️ Pedido sem path_comprovante: pedido_id={pedido_id}")
            return jsonify({'ok': False, 'msg': 'Comprovante não disponível'}), 404

        # Validate path (security: no path traversal)
        path_normalizado = str(path_comprovante).strip().lstrip('/')
        if '..' in path_normalizado:
            logger.warning(f"[ADMIN] ⚠️ Caminho inválido em path_comprovante: pedido_id={pedido_id} path={path_normalizado}")
            return jsonify({'ok': False, 'msg': 'Caminho inválido'}), 400

        # Get extension
        filename = os.path.basename(path_normalizado)
        _, ext = os.path.splitext(filename)
        ext = ext.lstrip('.').lower()

        # Validate extension
        allowed_extensions = ['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp']
        if ext not in allowed_extensions:
            logger.warning(f"[ADMIN] ⚠️ Extensão não suportada no comprovante: pedido_id={pedido_id} ext={ext} path={path_normalizado}")
            return jsonify({'ok': False, 'msg': f'Tipo de arquivo não suportado: {ext}'}), 400

        # Verifica se o arquivo existe em local esperado (storage ou static)
        caminhos_candidatos = []
        if path_normalizado.startswith('storage/'):
            caminhos_candidatos.append(os.path.join(current_app.root_path, path_normalizado))
        if path_normalizado.startswith('static/'):
            caminhos_candidatos.append(os.path.join(current_app.root_path, path_normalizado))
        caminhos_candidatos.append(os.path.join(current_app.static_folder, path_normalizado))

        caminho_absoluto = next((c for c in caminhos_candidatos if os.path.isfile(c)), None)
        if not caminho_absoluto:
            logger.warning(f"[ADMIN] ⚠️ Comprovante não encontrado para pedido #{pedido_id}: path={path_normalizado} candidatos={caminhos_candidatos}")
            return jsonify({'ok': False, 'msg': 'Arquivo de comprovante não encontrado'}), 404

        # Log de auditoria: quem visualizou o comprovante
        logger.info(f"[ADMIN] 👀 Usuário {current_user.email} solicitou visualização do comprovante do pedido #{pedido_id} (produto #{pedido['produto_id']}) path={path_normalizado}")

        return jsonify({
            'ok': True,
            'path': url_for('admin.visualizar_comprovante_arquivo', pedido_id=pedido_id),
            'extension': ext,
            'filename': filename
        })

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao visualizar comprovante pedido #{pedido_id}: {e}")
        return jsonify({'ok': False, 'msg': f'Erro ao carregar comprovante: {e}'}), 500


@admin_bp.route('/pedido/<int:pedido_id>/comprovante/arquivo')
@requer_login
def visualizar_comprovante_arquivo(pedido_id):
    """Entrega o arquivo do comprovante com validação de acesso ao pedido."""
    try:
        pedido = get_pedido(pedido_id)
        if not pedido:
            return jsonify({'ok': False, 'msg': 'Pedido não encontrado'}), 404

        if (not current_user.is_admin()) and (not usuario_tem_acesso_produto(current_user.id, pedido['produto_id'])):
            return jsonify({'ok': False, 'msg': 'Acesso negado'}), 403

        path_comprovante = pedido.get('path_comprovante')
        if not path_comprovante:
            return jsonify({'ok': False, 'msg': 'Comprovante não disponível'}), 404

        path_normalizado = str(path_comprovante).strip().lstrip('/')
        if '..' in path_normalizado:
            return jsonify({'ok': False, 'msg': 'Caminho inválido'}), 400

        caminhos_candidatos = []
        if path_normalizado.startswith('storage/'):
            caminhos_candidatos.append(os.path.join(current_app.root_path, path_normalizado))
        if path_normalizado.startswith('static/'):
            caminhos_candidatos.append(os.path.join(current_app.root_path, path_normalizado))
        caminhos_candidatos.append(os.path.join(current_app.static_folder, path_normalizado))

        caminho_absoluto = next((c for c in caminhos_candidatos if os.path.isfile(c)), None)
        if not caminho_absoluto:
            return jsonify({'ok': False, 'msg': 'Arquivo de comprovante não encontrado'}), 404

        return send_file(caminho_absoluto, conditional=True)
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao entregar comprovante do pedido #{pedido_id}: {e}")
        return jsonify({'ok': False, 'msg': 'Erro ao entregar comprovante'}), 500
