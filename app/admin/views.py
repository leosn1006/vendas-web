import logging
import os
import datetime
import subprocess
import tempfile
import bleach
from zoneinfo import ZoneInfo
from flask import render_template, redirect, url_for, request, flash, session, current_app, jsonify, send_file
from flask_login import current_user
from werkzeug.utils import secure_filename
from admin import admin_bp
from admin.auth import requer_login, requer_admin, requer_acesso_produto, usuario_tem_acesso_produto
from Whatsapp_config import ativa_whatsapp
from database import (db,
    listar_telefones_produto, adicionar_telefone_produto, remover_telefone_produto, atualizar_telefone_produto,
    contar_notificacoes_telefone_recentes, listar_notificacoes_telefone,
    contar_notificacoes_conta_recentes, listar_notificacoes_conta_whatsapp_produto,
    listar_mensagens_sugeridas, adicionar_mensagem_sugerida, remover_mensagem_sugerida,
    listar_acoes_fluxo, get_acao_fluxo,
    adicionar_acao_fluxo, atualizar_acao_fluxo, remover_acao_fluxo, tipo_acao_variantes_existentes,
    listar_bonus_produto, adicionar_bonus_produto, remover_bonus_produto,
    listar_bump_produto, get_bump_produto,
    adicionar_bump_produto, atualizar_bump_produto, remover_bump_produto,
    get_pedido, get_ultimo_pedido_by_phone, salvar_mensagem_pedido, listar_itens_pedido,
    buscar_todas_mensagens_pedido,
    pedido_dentro_da_janela_24h, buscar_data_ultima_mensagem_recebida_pedido,
    numero_empresa_operacional, buscar_status_numero_empresa,
    buscar_pedido_por_nome, acertar_valor_pedido,
    listar_chaves_pix_produto, adicionar_chave_pix_produto, desativar_chave_pix_produto,
    busca_financeiro_pix, buscar_tenant_slug_produto,
    listar_planilhas_dns_produto, adicionar_planilha_dns, atualizar_planilha_dns, remover_planilha_dns,
    listar_notificacoes_em_analise, marcar_notificacao_respondida, bloquear_pedido,
    buscar_notificacao_em_analise_pedido, bloquear_followup_pedido,
    buscar_pedido_web_por_email, buscar_mensagens_email_pedido, buscar_anexos_email_pedido,
    buscar_notificacao_email_pedido, bloquear_pedido_email, buscar_anexo_email_por_id,
    buscar_notificacao_por_id)

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

def _nome_arquivo_imagem(valor):
    """Extrai só o nome do arquivo de `imagem_checkout` — protege contra o admin colar
    a URL completa por engano (hábito do campo vizinho url_imagem_complementar) e contra
    qualquer componente de diretório (ex: '../') no valor digitado."""
    valor = (valor or '').strip()
    if not valor:
        return None
    return os.path.basename(valor.split('?')[0].rstrip('/')) or None

@admin_bp.route('/produtos/novo', methods=['GET', 'POST'])
@requer_admin
def novo_produto():
    if request.method == 'POST':
        try:
            novo_id = db.execute_query("""
                INSERT INTO produtos (nome, preco, descricao, ativo)
                VALUES (%s, %s, %s, 1)
            """, (
                request.form.get('nome'),
                request.form.get('preco'),
                request.form.get('descricao'),
            ))
            flash('Produto criado com sucesso! Complete os demais dados abaixo.', 'success')
            logger.info(f"[ADMIN] ✅ Produto criado por {current_user.email}")
            return redirect(url_for('admin.dados_basicos_produto', produto_id=novo_id))

        except Exception as e:
            logger.error(f"[ADMIN] ❌ Erro ao criar produto: {e}")
            flash(f'Erro ao criar produto: {e}', 'danger')

    return render_template('admin/produto_form.html', produto=None, acao='novo')

@admin_bp.route('/produtos/<int:produto_id>', methods=['GET', 'POST'])
@requer_acesso_produto
def editar_produto(produto_id):
    # Rota antiga ("Editar Produto", sem abas) — a edição foi unificada em
    # dados_basicos_produto pra acabar com o UPDATE duplicado/desalinhado entre
    # as duas telas (inclusive um bug real: essa rota zerava url_pagina_vendas,
    # porque o campo existia no UPDATE mas não no template). Mantida como
    # redirect só pra não quebrar links/favoritos antigos.
    return redirect(url_for('admin.dados_basicos_produto', produto_id=produto_id))

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
            # ativo e nfe_config_id só aparecem no formulário pra admin (produto_dados_basicos.html)
            # — sem essa checagem no servidor, um usuário com acesso ao produto mas sem ser admin
            # poderia mudar os dois só forjando o POST, já que @requer_acesso_produto não exige admin.
            if current_user.is_admin():
                ativo_novo = int(request.form.get('ativo', 1))
                nfe_config_id_novo = request.form.get('nfe_config_id') or None
            else:
                ativo_novo = produto['ativo']
                nfe_config_id_novo = produto['nfe_config_id']

            db.execute_query("""
                UPDATE produtos SET
                    nome                  = %s,
                    descricao             = %s,
                    preco                 = %s,
                    ativo                 = %s,
                    nfe_config_id         = %s,
                    disponivel_web        = %s,
                    url_pagina_vendas     = %s,
                    numero_convenio_bb    = %s,
                    imagem_checkout       = %s,
                    url_pdf               = %s,
                    url_imagem_complementar = %s,
                    email_remetente       = %s,
                    email_nome_remetente  = %s,
                    email_cor_primaria    = %s,
                    email_cor_secundaria  = %s,
                    prompt_vendas_email   = %s
                WHERE id = %s
            """, (
                request.form.get('nome'),
                request.form.get('descricao'),
                request.form.get('preco'),
                ativo_novo,
                nfe_config_id_novo,
                1 if request.form.get('disponivel_web') else 0,
                request.form.get('url_pagina_vendas') or None,
                request.form.get('numero_convenio_bb') or None,
                _nome_arquivo_imagem(request.form.get('imagem_checkout')),
                request.form.get('url_pdf') or None,
                request.form.get('url_imagem_complementar') or None,
                request.form.get('email_remetente') or None,
                request.form.get('email_nome_remetente') or None,
                request.form.get('email_cor_primaria') or None,
                request.form.get('email_cor_secundaria') or None,
                request.form.get('prompt_vendas_email') or None,
                produto_id
            ))
            flash('Dados básicos atualizados com sucesso!', 'success')
            logger.info(f"[ADMIN] ✅ Dados básicos do produto #{produto_id} atualizados por {current_user.email}")
        except Exception as e:
            logger.error(f"[ADMIN] ❌ Erro ao atualizar dados básicos: {e}")
            flash(f'Erro ao atualizar: {e}', 'danger')
        return redirect(url_for('admin.dados_basicos_produto', produto_id=produto_id))

    configs_nfe = db.execute_query(
        "SELECT id, tenant_slug, razao_social FROM nfe_configuracao ORDER BY id",
        fetch_all=True,
    ) or []
    return render_template('admin/produto_dados_basicos.html', produto=produto, configs_nfe=configs_nfe)

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
                    delay_final=acao['delay_final'],
                    variante=acao['variante']
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
    notificacao = buscar_notificacao_por_id(notificacao_id, produto_id)
    marcar_notificacao_respondida(notificacao_id, produto_id)
    if notificacao and notificacao['motivo'] == 'sugestao_resposta_email':
        return redirect(url_for('admin.conversa_email_pedido', produto_id=produto_id, pedido_id=notificacao['pedido_id']))
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
        if not q:
            flash('Digite um número de pedido, telefone ou nome pra buscar.', 'danger')
            return render_template('admin/produto_conversas.html', produto=produto)

        pedido = None
        if q.isdigit() and len(q) <= 7:
            pedido = get_pedido(int(q))
            if pedido and pedido.get('produto_id') != produto_id:
                pedido = None
        if not pedido:
            pedido = get_ultimo_pedido_by_phone(q, produto_id)
        if not pedido:
            pedido = buscar_pedido_por_nome(q, produto_id, canal_web=False)

        if pedido and pedido.get('estado_id', 0) >= 1000:
            flash('Esse pedido é uma venda web — use "Conversas Web" pra encontrá-lo pelo e-mail/nome.', 'warning')
            pedido = None

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
    dentro_da_janela = pedido_dentro_da_janela_24h(pedido_id)
    ultima_mensagem_cliente_em = buscar_data_ultima_mensagem_recebida_pedido(pedido_id)
    numero_operacional = numero_empresa_operacional(pedido.get('phone_number_id'))
    status_numero_empresa = None if numero_operacional else buscar_status_numero_empresa(pedido.get('phone_number_id'))
    pode_enviar_mensagem = dentro_da_janela and numero_operacional
    return render_template('admin/produto_conversas.html',
                           produto=produto, pedido=pedido, mensagens=mensagens,
                           notificacao_ativa=notificacao_ativa,
                           dentro_da_janela=dentro_da_janela,
                           ultima_mensagem_cliente_em=ultima_mensagem_cliente_em,
                           numero_operacional=numero_operacional,
                           status_numero_empresa=status_numero_empresa,
                           pode_enviar_mensagem=pode_enviar_mensagem)


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

    if not pedido_dentro_da_janela_24h(pedido_id):
        flash('Não é possível enviar: fora da janela de 24h da API do WhatsApp '
              '(nenhuma mensagem do cliente nas últimas 24h). Aguarde o cliente responder.', 'danger')
        return redirect(url_for('admin.conversa_pedido', produto_id=produto_id, pedido_id=pedido_id))

    if not numero_empresa_operacional(pedido.get('phone_number_id')):
        status_info = buscar_status_numero_empresa(pedido.get('phone_number_id'))
        if status_info:
            flash(f"Não é possível enviar: o número da empresa ({status_info['telefone']}) está "
                  f"com status \"{status_info['status_api']}\" na Meta (possível banimento/restrição). "
                  f"Contate o time técnico.", 'danger')
        else:
            flash('Não é possível enviar: o número da empresa vinculado a este pedido não está mais '
                  'cadastrado na base de números ativos (removido ou nunca vinculado).', 'danger')
        return redirect(url_for('admin.conversa_pedido', produto_id=produto_id, pedido_id=pedido_id))

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
# Conversas por e-mail (pedidos web 1000-1004) — tela própria, não reaproveita
# produto_conversas.html (evita condicionais grandes misturando WhatsApp/e-mail).
# ============================================================
_TAGS_HTML_EMAIL_PERMITIDAS = ['p', 'br', 'strong', 'b', 'em', 'i', 'u', 'a', 'ul', 'ol', 'li', 'blockquote']
_ATRIBUTOS_HTML_EMAIL_PERMITIDOS = {'a': ['href', 'title']}


def _sanitizar_html_email(html: str) -> str:
    """Sanitiza HTML de e-mail (recebido do cliente ou editado pelo admin) antes de renderizar
    ou enviar — remove <script>, on*=, javascript: etc. Sem 'style' na allowlist de propósito:
    evita ter que sanitizar CSS à parte (url(), expression()) só para preservar formatação de
    um remetente não confiável."""
    return bleach.clean(html or '', tags=_TAGS_HTML_EMAIL_PERMITIDAS,
                        attributes=_ATRIBUTOS_HTML_EMAIL_PERMITIDOS,
                        protocols=['http', 'https', 'mailto'], strip=True)


@admin_bp.route('/produto/<int:produto_id>/notificacoes-web')
@requer_acesso_produto
def notificacoes_web_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query("SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True)
    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))
    notificacoes = listar_notificacoes_em_analise(produto_id, motivo='sugestao_resposta_email')
    return render_template('admin/produto_notificacoes_web.html', produto=produto, notificacoes=notificacoes)


@admin_bp.route('/produto/<int:produto_id>/emails/conversas', methods=['GET', 'POST'])
@requer_acesso_produto
def conversas_email_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query("SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True)
    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))

    if request.method == 'POST':
        q = (request.form.get('q') or '').strip()
        if not q:
            flash('Digite um número de pedido, e-mail ou nome pra buscar.', 'danger')
            return render_template('admin/produto_conversas_email.html', produto=produto)

        pedido = None
        if q.isdigit() and len(q) <= 7:
            pedido = get_pedido(int(q))
            if pedido and pedido.get('produto_id') != produto_id:
                pedido = None
        if not pedido:
            pedido = buscar_pedido_web_por_email(q, produto_id)
        if not pedido:
            pedido = buscar_pedido_por_nome(q, produto_id, canal_web=True)

        if pedido and pedido.get('estado_id', 0) < 1000:
            flash('Esse pedido é uma venda por WhatsApp — use "Conversas" pra encontrá-lo.', 'warning')
            pedido = None

        if pedido:
            return redirect(url_for('admin.conversa_email_pedido', produto_id=produto_id, pedido_id=pedido['id']))
        flash('Nenhuma conversa encontrada para esse pedido, e-mail ou nome.', 'danger')

    return render_template('admin/produto_conversas_email.html', produto=produto)


@admin_bp.route('/produto/<int:produto_id>/emails/conversas/<int:pedido_id>')
@requer_acesso_produto
def conversa_email_pedido(produto_id, pedido_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query("SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True)
    pedido  = get_pedido(pedido_id)

    if not produto or not pedido or pedido.get('produto_id') != produto_id:
        flash('Conversa não encontrada.', 'danger')
        return redirect(url_for('admin.conversas_email_produto', produto_id=produto_id))

    mensagens = buscar_mensagens_email_pedido(pedido_id)
    for msg in mensagens:
        if msg.get('corpo_html'):
            msg['corpo_html'] = _sanitizar_html_email(msg['corpo_html'])

    anexos_por_mensagem = {}
    for anexo in buscar_anexos_email_pedido(pedido_id):
        anexos_por_mensagem.setdefault(anexo['mensagem_id'], []).append(anexo)

    notificacao_sugestao = buscar_notificacao_email_pedido(pedido_id)
    rascunho_ia = notificacao_sugestao['mensagem'] if notificacao_sugestao else ''

    return render_template('admin/conversa_email_pedido.html',
                           produto=produto, pedido=pedido, mensagens=mensagens,
                           anexos_por_mensagem=anexos_por_mensagem,
                           notificacao_sugestao=notificacao_sugestao,
                           rascunho_ia=rascunho_ia)


@admin_bp.route('/produto/<int:produto_id>/emails/conversas/<int:pedido_id>/enviar', methods=['POST'])
@requer_acesso_produto
def conversa_email_enviar_mensagem(produto_id, pedido_id):
    from fluxos.fluxo_resposta_email import enviar_resposta
    from agente_resposta_email_produto import _garantir_html as _garantir_html_email
    pedido = get_pedido(pedido_id)
    if not pedido or pedido.get('produto_id') != produto_id:
        flash('Pedido não encontrado.', 'danger')
        return redirect(url_for('admin.conversas_email_produto', produto_id=produto_id))

    corpo_html = (request.form.get('corpo_html') or '').strip()
    if not corpo_html:
        flash('Mensagem não pode ser vazia.', 'danger')
        return redirect(url_for('admin.conversa_email_pedido', produto_id=produto_id, pedido_id=pedido_id))

    notificacao_id = request.form.get('notificacao_id', type=int)
    # Mesma rede de segurança do agente (_garantir_html): se o admin apagou o rascunho e digitou
    # só texto corrido, sem nenhuma tag, embrulha em <p> — senão a quebra de linha simplesmente
    # some no e-mail final (confirmado em teste real: texto puro editado saiu sem <p> nenhuma).
    corpo_html = _garantir_html_email(corpo_html)
    corpo_html = _sanitizar_html_email(corpo_html)  # defesa em profundidade — não confia só no client-side

    try:
        enviar_resposta(pedido_id, corpo_html, notificacao_id=notificacao_id)
        logger.info(f"[ADMIN] ✅ Resposta de e-mail enviada ao pedido #{pedido_id} por {current_user.email}")
        flash('Resposta enviada com sucesso!', 'success')
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao enviar resposta de e-mail: {e}")
        flash(f'Erro ao enviar: {e}', 'danger')

    return redirect(url_for('admin.conversa_email_pedido', produto_id=produto_id, pedido_id=pedido_id))


@admin_bp.route('/produto/<int:produto_id>/emails/conversas/<int:pedido_id>/bloquear', methods=['POST'])
@requer_acesso_produto
def bloquear_conversa_email(produto_id, pedido_id):
    pedido = get_pedido(pedido_id)
    if not pedido or pedido.get('produto_id') != produto_id:
        flash('Pedido não encontrado.', 'danger')
        return redirect(url_for('admin.conversas_email_produto', produto_id=produto_id))
    bloquear_pedido_email(pedido_id)
    flash('E-mail bloqueado. O agente não vai mais sugerir resposta para este pedido (WhatsApp não é afetado).', 'success')
    return redirect(url_for('admin.conversa_email_pedido', produto_id=produto_id, pedido_id=pedido_id))


@admin_bp.route('/produto/<int:produto_id>/emails/preview', methods=['POST'])
@requer_acesso_produto
def preview_email_html(produto_id):
    """AJAX: sanitiza o HTML atual do textarea de resposta para o botão 'Pré-visualizar'."""
    return _sanitizar_html_email(request.form.get('html', ''))


_EXTENSOES_PREVIEW_SEGURO_EMAIL = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'}


@admin_bp.route('/pedido/<int:pedido_id>/email/anexo/<int:anexo_id>')
@requer_login
def visualizar_anexo_email(pedido_id, anexo_id):
    """Entrega um anexo de e-mail. Aceitamos qualquer tipo de arquivo do cliente, então por
    padrão força download (nunca deixa o navegador tentar renderizar algo potencialmente
    perigoso — .html/.svg disfarçados — dentro da sessão logada do admin). Só abre inline pra
    uma allowlist de tipos seguros (imagem/PDF), mesmo padrão de visualizar_comprovante_arquivo
    — a extensão vem do nome do arquivo, nunca do mime_type autoinformado pelo remetente."""
    pedido = get_pedido(pedido_id)
    if not pedido:
        return jsonify({'ok': False, 'msg': 'Pedido não encontrado'}), 404
    if (not current_user.is_admin()) and (not usuario_tem_acesso_produto(current_user.id, pedido['produto_id'])):
        return jsonify({'ok': False, 'msg': 'Acesso negado'}), 403

    anexo = buscar_anexo_email_por_id(anexo_id)
    if not anexo or anexo['pedido_id'] != pedido_id:
        return jsonify({'ok': False, 'msg': 'Anexo não encontrado'}), 404

    from fluxos.fluxo_email_conversas import resolver_caminho_anexo
    caminho = resolver_caminho_anexo(anexo['caminho_arquivo'])
    if not caminho:
        return jsonify({'ok': False, 'msg': 'Arquivo não encontrado'}), 404

    nome = anexo['nome_arquivo']
    extensao = nome.rsplit('.', 1)[-1].lower() if '.' in nome else ''
    seguro_para_visualizar = extensao in _EXTENSOES_PREVIEW_SEGURO_EMAIL

    logger.info(f"[ADMIN] 👀 Usuário {current_user.email} abriu anexo de e-mail do pedido #{pedido_id}: {nome}")
    return send_file(caminho, as_attachment=not seguro_para_visualizar, download_name=nome, conditional=True)


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
        return redirect(url_for('admin.roi_produto', produto_id=produto_id))
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
    notif_recentes = contar_notificacoes_telefone_recentes(produto_id, horas=24)
    notif_conta_recentes = contar_notificacoes_conta_recentes(produto_id, horas=24)
    return render_template('admin/numeros_whatsapp.html', produto=produto, telefones=telefones,
                            notif_recentes=notif_recentes, notif_conta_recentes=notif_conta_recentes)


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


@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp/atualizar-qualidade', methods=['POST'])
@requer_acesso_produto
def atualizar_qualidade_numeros_whatsapp(produto_id):
    try:
        from celery_app import celery_app
        celery_app.send_task('tasks.verificar_qualidade_whatsapp_produto', args=[produto_id])
        return jsonify({'ok': True, 'msg': 'Checagem de qualidade iniciada. Aguarde alguns segundos e atualize a página.'})
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao disparar checagem de qualidade: {e}")
        return jsonify({'ok': False, 'msg': f'Erro ao iniciar checagem: {e}'}), 500


@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp/notificacoes-conta')
@requer_acesso_produto
def notificacoes_conta_whatsapp_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query(
        "SELECT id, nome FROM produtos WHERE id = %s", (produto_id,), fetch_one=True
    )
    if not produto:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.dashboard'))
    notificacoes = listar_notificacoes_conta_whatsapp_produto(produto_id)
    return render_template('admin/produto_notificacoes_conta.html', produto=produto, notificacoes=notificacoes)


@admin_bp.route('/produto/<int:produto_id>/numeros-whatsapp/<int:telefone_id>/historico')
@requer_acesso_produto
def historico_numero_whatsapp(produto_id, telefone_id):
    session['produto_ativo_id'] = produto_id
    telefones = listar_telefones_produto(produto_id)
    telefone_atual = next((t for t in telefones if t['id'] == telefone_id), None)
    if not telefone_atual:
        flash('Número não encontrado.', 'danger')
        return redirect(url_for('admin.numeros_whatsapp', produto_id=produto_id))
    notificacoes = listar_notificacoes_telefone(telefone_id)
    return render_template('admin/numero_notificacoes.html',
                            produto_id=produto_id, telefones=telefones,
                            telefone_atual=telefone_atual, notificacoes=notificacoes)


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
    grupos_variantes = {}
    for a in acoes:
        grupos_variantes.setdefault((a['condicao'], a['ordem']), []).append(a['variante'])
    return render_template('admin/fluxo_acoes.html',
                           produto=produto,
                           fluxo=fluxo,
                           fluxos=_FLUXOS,
                           fluxos_labels=_FLUXOS_LABELS,
                           acoes=acoes,
                           grupos_variantes=grupos_variantes,
                           readonly=fluxo in _FLUXOS_READONLY)


@admin_bp.route('/produto/<int:produto_id>/fluxos/<fluxo>/adicionar', methods=['POST'])
@requer_admin
def adicionar_acao_fluxo_view(produto_id, fluxo):
    if fluxo in _FLUXOS_READONLY:
        flash('Este fluxo é somente leitura.', 'warning')
        return redirect(url_for('admin.fluxo_acoes', produto_id=produto_id, fluxo=fluxo))
    try:
        ordem = int(request.form['ordem'])
        condicao = request.form['condicao']
        tipo_acao = request.form['acao']
        variante = max(1, int(request.form.get('variante') or 1))

        tipo_existente = tipo_acao_variantes_existentes(produto_id, fluxo, condicao, ordem)
        if tipo_existente and tipo_existente != tipo_acao:
            raise ValueError(
                f"As variantes do passo ordem={ordem} ({condicao}) já usam a ação "
                f"'{tipo_existente}'. Todas as variantes do mesmo passo devem ter o mesmo tipo de ação."
            )

        adicionar_acao_fluxo(
            produto_id, fluxo,
            ordem=ordem,
            condicao=condicao,
            acao=tipo_acao,
            url=request.form.get('url'),
            mensagem=request.form.get('mensagem'),
            caption=request.form.get('caption'),
            nome_arquivo=request.form.get('nome_arquivo'),
            delay_inicial=float(request.form.get('delay_inicial') or 0),
            delay_final=float(request.form.get('delay_final') or 0),
            param1=request.form.get('param1'),
            param2=request.form.get('param2'),
            variante=variante,
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
            ordem = int(request.form['ordem'])
            condicao = request.form['condicao']
            tipo_acao = request.form['acao']
            variante = max(1, int(request.form.get('variante') or 1))

            tipo_existente = tipo_acao_variantes_existentes(produto_id, fluxo, condicao, ordem, excluir_acao_id=acao_id)
            if tipo_existente and tipo_existente != tipo_acao:
                raise ValueError(
                    f"As variantes do passo ordem={ordem} ({condicao}) já usam a ação "
                    f"'{tipo_existente}'. Todas as variantes do mesmo passo devem ter o mesmo tipo de ação."
                )

            atualizar_acao_fluxo(
                acao_id,
                ordem=ordem,
                condicao=condicao,
                acao=tipo_acao,
                url=request.form.get('url'),
                mensagem=request.form.get('mensagem'),
                caption=request.form.get('caption'),
                nome_arquivo=request.form.get('nome_arquivo'),
                delay_inicial=float(request.form.get('delay_inicial') or 0),
                delay_final=float(request.form.get('delay_final') or 0),
                param1=request.form.get('param1'),
                param2=request.form.get('param2'),
                variante=variante,
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
# Bônus por produto (venda web)
# ============================================================

@admin_bp.route('/produto/<int:produto_id>/bonus')
@requer_login
def produto_bonus(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))
    bonus = listar_bonus_produto(produto_id)
    return render_template('admin/produto_bonus.html', produto=produto, bonus=bonus)


@admin_bp.route('/produto/<int:produto_id>/bonus/adicionar', methods=['POST'])
@requer_admin
def adicionar_bonus_produto_view(produto_id):
    nome = request.form.get('nome', '').strip()
    path_arquivo = request.form.get('path_arquivo', '').strip()
    nome_arquivo = request.form.get('nome_arquivo', '').strip() or path_arquivo
    if not nome or not path_arquivo:
        flash('Informe nome e arquivo do bônus.', 'warning')
        return redirect(url_for('admin.produto_bonus', produto_id=produto_id))
    try:
        adicionar_bonus_produto(
            produto_id, nome, path_arquivo, nome_arquivo,
            descricao=request.form.get('descricao'),
            ordem=int(request.form.get('ordem') or 1),
        )
        flash('Bônus adicionado com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ Bônus adicionado ao produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao adicionar bônus: {e}")
        flash(f'Erro ao adicionar bônus: {e}', 'danger')
    return redirect(url_for('admin.produto_bonus', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/bonus/<int:bonus_id>/remover', methods=['POST'])
@requer_admin
def remover_bonus_produto_view(produto_id, bonus_id):
    try:
        remover_bonus_produto(bonus_id, produto_id)
        flash('Bônus removido.', 'success')
        logger.info(f"[ADMIN] ✅ Bônus #{bonus_id} removido do produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover bônus: {e}")
        flash(f'Erro ao remover bônus: {e}', 'danger')
    return redirect(url_for('admin.produto_bonus', produto_id=produto_id))


# ============================================================
# Order Bumps por produto (venda web)
# ============================================================

@admin_bp.route('/produto/<int:produto_id>/bumps')
@requer_login
def produto_bumps(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))
    bumps = listar_bump_produto(produto_id)
    return render_template('admin/produto_bumps.html', produto=produto, bumps=bumps)


@admin_bp.route('/produto/<int:produto_id>/bumps/adicionar', methods=['POST'])
@requer_admin
def adicionar_bump_produto_view(produto_id):
    nome = request.form.get('nome', '').strip()
    path_arquivo = request.form.get('path_arquivo', '').strip()
    nome_arquivo = request.form.get('nome_arquivo', '').strip() or path_arquivo
    if not nome or not path_arquivo:
        flash('Informe nome e arquivo do order bump.', 'warning')
        return redirect(url_for('admin.produto_bumps', produto_id=produto_id))
    try:
        adicionar_bump_produto(
            produto_id, nome, path_arquivo, nome_arquivo,
            preco_original=float(request.form['preco_original']),
            preco_promocional=float(request.form['preco_promocional']),
            descricao=request.form.get('descricao'),
            ordem=int(request.form.get('ordem') or 1),
            imagem_checkout=_nome_arquivo_imagem(request.form.get('imagem_checkout')),
        )
        flash('Order bump adicionado com sucesso!', 'success')
        logger.info(f"[ADMIN] ✅ Order bump adicionado ao produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao adicionar order bump: {e}")
        flash(f'Erro ao adicionar order bump: {e}', 'danger')
    return redirect(url_for('admin.produto_bumps', produto_id=produto_id))


@admin_bp.route('/produto/<int:produto_id>/bumps/<int:bump_id>/editar', methods=['GET', 'POST'])
@requer_admin
def editar_bump_produto(produto_id, bump_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    bump = get_bump_produto(bump_id, produto_id)
    if not bump:
        flash('Order bump não encontrado.', 'danger')
        return redirect(url_for('admin.produto_bumps', produto_id=produto_id))

    if request.method == 'POST':
        try:
            path_arquivo = request.form['path_arquivo'].strip()
            atualizar_bump_produto(
                bump_id, produto_id,
                nome=request.form['nome'].strip(),
                path_arquivo=path_arquivo,
                nome_arquivo=request.form.get('nome_arquivo', '').strip() or path_arquivo,
                preco_original=float(request.form['preco_original']),
                preco_promocional=float(request.form['preco_promocional']),
                descricao=request.form.get('descricao'),
                ordem=int(request.form.get('ordem') or 1),
                imagem_checkout=_nome_arquivo_imagem(request.form.get('imagem_checkout')),
            )
            flash('Order bump atualizado com sucesso!', 'success')
            logger.info(f"[ADMIN] ✅ Order bump #{bump_id} atualizado por {current_user.email}")
            return redirect(url_for('admin.produto_bumps', produto_id=produto_id))
        except Exception as e:
            logger.error(f"[ADMIN] ❌ Erro ao atualizar order bump: {e}")
            flash(f'Erro ao salvar: {e}', 'danger')

    return render_template('admin/produto_bump_editar.html', produto=produto, bump=bump)


@admin_bp.route('/produto/<int:produto_id>/bumps/<int:bump_id>/remover', methods=['POST'])
@requer_admin
def remover_bump_produto_view(produto_id, bump_id):
    try:
        remover_bump_produto(bump_id, produto_id)
        flash('Order bump removido.', 'success')
        logger.info(f"[ADMIN] ✅ Order bump #{bump_id} removido do produto #{produto_id} por {current_user.email}")
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao remover order bump: {e}")
        flash(f'Erro ao remover order bump: {e}', 'danger')
    return redirect(url_for('admin.produto_bumps', produto_id=produto_id))


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
        COUNT(CASE WHEN estado_id IN (1004,1003,1001,1002,1000) THEN 1 END) AS chegou_landing,
        COUNT(CASE WHEN estado_id IN (1003,1001,1002,1000) THEN 1 END)      AS chegou_checkout,
        COUNT(CASE WHEN estado_id IN (1000,1001,1002) THEN 1 END)          AS total_pedidos,
        COUNT(CASE WHEN estado_id = 1000 THEN 1 END)                        AS pagos
    FROM pedidos
    WHERE produto_id = %s
      AND data_contato_site BETWEEN %s AND %s
"""
# Nota: como o estado é atualizado na mesma linha (1004→1003→1001→1002→1000, não um evento por
# etapa), "chegou_landing"/"chegou_checkout" somam também quem já avançou além daquela etapa —
# funciona porque hoje 100% do tráfego de checkout passa pela landing primeiro (pudim-e.html é
# a única porta de entrada pro produto 8). Se um dia um anúncio apontar direto pro checkout
# (pulando a landing), essa contagem de "chegou_landing" ficaria imprecisa — nesse caso valeria
# adicionar colunas de timestamp por marco (ex: data_chegou_landing) em vez de inferir pelo
# estado atual.

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

_SQL_PRO_PIX_HORARIO = """
    SELECT
        WEEKDAY(horario) AS dia_semana,   -- 0=Segunda ... 6=Domingo
        HOUR(horario)    AS hora,
        COUNT(*)                      AS qtd,
        COALESCE(SUM(valor), 0)       AS receita
    FROM pagamento_pix
    WHERE produto_id = %s
      AND horario BETWEEN %s AND %s
    GROUP BY WEEKDAY(horario), HOUR(horario)
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
    pix_horario = None
    campanhas_pro = []

    try:
        funil        = db.execute_query(_SQL_PRO_FUNIL,        (produto_id, data_ini, data_fim), fetch_one=True)
        receita      = db.execute_query(_SQL_PRO_RECEITA,      (produto_id, data_ini, data_fim), fetch_one=True)
        investimento = db.execute_query(_SQL_PRO_INVESTIMENTO, (produto_id, data_ini_date, data_fim_date), fetch_one=True)
        pix_horario  = db.execute_query(_SQL_PRO_PIX_HORARIO,  (produto_id, data_ini, data_fim), fetch_all=True)

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

    DIAS_SEMANA = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

    matriz     = [[0.0] * 24 for _ in range(7)]
    qtd_matriz = [[0] * 24 for _ in range(7)]
    for row in (pix_horario or []):
        d, h = int(row['dia_semana']), int(row['hora'])
        matriz[d][h]     = float(row['receita'] or 0)
        qtd_matriz[d][h] = int(row['qtd'] or 0)

    max_valor = max((v for linha in matriz for v in linha), default=0.0)

    def _alpha(valor):
        if not max_valor or valor <= 0:
            return 0.0
        return round(0.15 + (valor / max_valor) * 0.75, 3)

    linhas = []
    for d, dia_label in enumerate(DIAS_SEMANA):
        celulas = [
            {
                'hora': h,
                'valor': matriz[d][h],
                'qtd': qtd_matriz[d][h],
                'alpha': _alpha(matriz[d][h]),
            }
            for h in range(24)
        ]
        linhas.append({'label': dia_label, 'celulas': celulas})

    total_por_hora = [sum(matriz[d][h] for d in range(7)) for h in range(24)]
    max_total_hora = max(total_por_hora, default=0.0)
    hora_pico = total_por_hora.index(max_total_hora) if max_total_hora else None
    totais_hora = [
        {
            'hora': h,
            'valor': total_por_hora[h],
            'pct_barra': round(total_por_hora[h] / max_total_hora * 100, 1) if max_total_hora else 0,
            'pico': h == hora_pico,
        }
        for h in range(24)
    ]

    heatmap_pix = {
        'linhas': linhas,
        'totais_hora': totais_hora,
        'total_geral': sum(total_por_hora),
        'max_valor': max_valor,
        'hora_pico': hora_pico,
    }

    return render_template('admin/produto_analytics_pro.html',
        produto=produto, funil=funil, receita=receita,
        investimento=investimento, campanhas_pro=campanhas_pro,
        m=m, heatmap_pix=heatmap_pix,
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
        funil       = db.execute_query(_SQL_FUNIL_WEB,        (produto_id, data_ini, data_fim), fetch_one=True)
        receita     = db.execute_query(_SQL_RECEITA_WEB,      (produto_id, data_ini, data_fim), fetch_one=True)
        campanhas   = db.execute_query(_SQL_CAMPANHAS_WEB,    (produto_id, data_ini, data_fim), fetch_all=True)
        investimento = db.execute_query(_SQL_PRO_INVESTIMENTO, (produto_id, data_ini, data_fim), fetch_one=True)
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro no analytics web produto #{produto_id}: {e}")
        flash('Erro ao carregar analytics web.', 'danger')
        funil = receita = investimento = None
        campanhas = []

    conv_pedidos_pagos = 0.0
    conv_landing_checkout = 0.0
    conv_checkout_pedido = 0.0
    ticket_medio = 0.0
    cliques_google_ads = investimento['total_cliques'] if investimento else 0

    if funil and funil['total_pedidos'] > 0:
        conv_pedidos_pagos = round((funil['pagos'] / funil['total_pedidos']) * 100, 1)

    if funil and funil['chegou_landing'] > 0:
        conv_landing_checkout = round((funil['chegou_checkout'] / funil['chegou_landing']) * 100, 1)

    if funil and funil['chegou_checkout'] > 0:
        conv_checkout_pedido = round((funil['total_pedidos'] / funil['chegou_checkout']) * 100, 1)

    if receita and receita['total_pagamentos']:
        ticket_medio = float(receita['total_receita']) / receita['total_pagamentos']

    return render_template('admin/produto_analytics_web.html',
        produto               = produto,
        funil                 = funil,
        receita               = receita,
        campanhas             = campanhas,
        cliques_google_ads    = cliques_google_ads,
        conv_landing_checkout = conv_landing_checkout,
        conv_checkout_pedido  = conv_checkout_pedido,
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
        COALESCE(c.venda_web, FALSE) AS venda_web,
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
    venda_web = request.form.get('venda_web') == 'on'
    if not campaignid or not nome:
        flash('Informe o Campaign ID e o nome.', 'warning')
        return redirect(url_for('admin.campanhas_produto', produto_id=produto_id))
    try:
        db.execute_query(
            """INSERT INTO campanhas (produto_id, campaignid, nome, venda_web)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE nome = VALUES(nome), venda_web = VALUES(venda_web)""",
            (produto_id, campaignid, nome, venda_web)
        )
        flash(f'Nome "{nome}" salvo para a campanha {campaignid}.', 'success')
        logger.info(f"[ADMIN] ✅ Campanha {campaignid} → '{nome}' (venda_web={venda_web}) salva no produto #{produto_id} por {current_user.email}")
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
        WHERE produto_id = %s AND estado_id IN (0, 1000) AND data_pagamento BETWEEN %s AND %s
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
            SELECT SUM(pp.valor)
            FROM pagamento_pix pp
            WHERE pp.produto_id = %s
              AND pp.horario BETWEEN %s AND %s
              AND NOT EXISTS (
                  SELECT 1 FROM pedidos ped
                  WHERE ped.estado_id = 1000
                    AND ped.e2e_id = pp.e2e_id
                    AND ped.e2e_id != ''
              )
        ), 0) AS total_pix_sem_duplicidade_web,
        COALESCE((
            SELECT SUM(oc.valor_investido)
            FROM orcamento_campanha oc
            LEFT JOIN campanhas cam
                ON cam.produto_id = oc.produto_id AND cam.campaignid = oc.campaignid
            WHERE oc.produto_id = %s
              AND oc.data BETWEEN %s AND %s
              AND COALESCE(cam.venda_web, FALSE) = FALSE
        ), 0) AS total_investido
"""

_SQL_ROI_REAL_WEB = """
    SELECT
        COALESCE((
            SELECT SUM(p.valor_pago)
            FROM pedidos p
            WHERE p.produto_id = %s
              AND p.estado_id = 1000
              AND p.data_pagamento BETWEEN %s AND %s
        ), 0) AS total_web,
        COALESCE((
            SELECT SUM(oc.valor_investido)
            FROM orcamento_campanha oc
            JOIN campanhas cam
                ON cam.produto_id = oc.produto_id AND cam.campaignid = oc.campaignid
            WHERE oc.produto_id = %s
              AND oc.data BETWEEN %s AND %s
              AND cam.venda_web = TRUE
        ), 0) AS total_investido
"""


_SQL_ROI_TODOS_PRODUTOS = """
    SELECT
        p.id,
        p.nome,
        COALESCE(oc.total_investido,  0) AS total_investido,
        COALESCE(pp.total_pix,        0) AS total_pix,
        COALESCE(pw.total_web,        0) AS total_web
    FROM produtos p
    LEFT JOIN (
        SELECT produto_id, SUM(valor_investido) AS total_investido
        FROM orcamento_campanha
        WHERE data BETWEEN %(ini_date)s AND %(fim_date)s
        GROUP BY produto_id
    ) oc ON oc.produto_id = p.id
    LEFT JOIN (
        SELECT produto_id, SUM(valor) AS total_pix
        FROM pagamento_pix pp_inner
        WHERE horario BETWEEN %(ini)s AND %(fim)s
          AND NOT EXISTS (
              SELECT 1 FROM pedidos ped
              WHERE ped.estado_id = 1000
                AND ped.e2e_id = pp_inner.e2e_id
                AND ped.e2e_id != ''
          )
        GROUP BY produto_id
    ) pp ON pp.produto_id = p.id
    LEFT JOIN (
        SELECT produto_id, SUM(valor_pago) AS total_web
        FROM pedidos
        WHERE estado_id = 1000
          AND data_pagamento BETWEEN %(ini)s AND %(fim)s
        GROUP BY produto_id
    ) pw ON pw.produto_id = p.id
    WHERE p.ativo = TRUE
    ORDER BY total_pix DESC
"""


def _parse_taxa_imposto(default: float = 7.3) -> float:
    """Lê e limita a `?imposto=` da query string a uma faixa válida de percentual (0-100)."""
    try:
        return max(0.0, min(100.0, float(request.args.get('imposto', str(default)) or default)))
    except (ValueError, TypeError):
        return default


@admin_bp.route('/roi-produtos')
@requer_admin
def roi_todos_produtos():
    hoje = _hoje_sao_paulo()
    data_ini_str = request.args.get('data_ini', hoje.isoformat())
    data_fim_str = request.args.get('data_fim', hoje.isoformat())

    try:
        data_ini = datetime.datetime.fromisoformat(data_ini_str)
        data_fim = datetime.datetime.fromisoformat(data_fim_str) + datetime.timedelta(days=1, seconds=-1)
    except ValueError:
        data_ini = datetime.datetime.combine(hoje, datetime.time.min)
        data_fim = datetime.datetime.combine(hoje, datetime.time.max)
        data_ini_str = data_fim_str = hoje.isoformat()

    data_ini_date = data_ini.date().isoformat()
    data_fim_date = data_fim.date().isoformat()

    try:
        rows = db.execute_query(
            _SQL_ROI_TODOS_PRODUTOS,
            {'ini': data_ini, 'fim': data_fim,
             'ini_date': data_ini_date, 'fim_date': data_fim_date},
            fetch_all=True
        )
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro no ROI todos os produtos: {e}")
        flash('Erro ao carregar ROI dos produtos.', 'danger')
        rows = []

    taxa = _parse_taxa_imposto()

    for r in rows:
        investido = float(r['total_investido'])
        pix = float(r['total_pix'])
        web = float(r['total_web'])
        total_recebido = pix + web
        imposto_valor = total_recebido * taxa / 100
        r['imposto_valor'] = imposto_valor
        r['roi_multiplier'] = ((total_recebido - imposto_valor) / investido) if investido > 0 else None
        r['lucro_liquido'] = total_recebido - investido - imposto_valor

    return render_template('admin/roi_todos_produtos.html',
        rows=rows, data_ini=data_ini_str, data_fim=data_fim_str, taxa_imposto=taxa)


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

    roi_real = {'total_pix': 0, 'total_pix_sem_duplicidade_web': 0, 'total_investido': 0}
    roi_real_erro = False
    try:
        roi_real_row = db.execute_query(
            _SQL_ROI_REAL,
            (produto_id, data_ini, data_fim,
             produto_id, data_ini, data_fim,
             produto_id, data_ini_date, data_fim_date),
            fetch_one=True
        )
        if roi_real_row:
            roi_real = roi_real_row
    except Exception as e:
        roi_real_erro = True
        roi_real = None
        logger.error(f"[ADMIN] ❌ Erro ao calcular ROI real do produto #{produto_id}: {e}")

    roi_real_web = {'total_web': 0, 'total_investido': 0}
    roi_real_web_erro = False
    try:
        roi_real_web_row = db.execute_query(
            _SQL_ROI_REAL_WEB,
            (produto_id, data_ini, data_fim,
             produto_id, data_ini_date, data_fim_date),
            fetch_one=True
        )
        if roi_real_web_row:
            roi_real_web = roi_real_web_row
    except Exception as e:
        roi_real_web_erro = True
        roi_real_web = None
        logger.error(f"[ADMIN] ❌ Erro ao calcular ROI real web do produto #{produto_id}: {e}")

    taxa_imposto = _parse_taxa_imposto()

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
        produto=produto, rows=rows,
        roi_real=roi_real, roi_real_erro=roi_real_erro,
        roi_real_web=roi_real_web, roi_real_web_erro=roi_real_web_erro,
        taxa_imposto=taxa_imposto,
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


# ── Financeiro (PIX + Web) ────────────────────────────────────────────────────

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
        logger.error(f"[ADMIN] ❌ Erro no financeiro produto #{produto_id}: {e}")
        flash('Erro ao carregar dados financeiros.', 'danger')
        financeiro = {'resumo': {'total_valor': 0, 'qtd_transacoes': 0, 'ticket_medio': 0}, 'transacoes': []}

    return render_template('admin/produto_financeiro.html',
        produto     = produto,
        financeiro  = financeiro,
        data_ini    = data_ini_str,
        data_fim    = data_fim_str,
    )


@admin_bp.route('/fiscal/configuracao')
@requer_admin
def fiscal_nfe_configuracao_lista():
    configs = db.execute_query(
        "SELECT id, tenant_slug, razao_social, cnpj, ambiente, ativo FROM nfe_configuracao ORDER BY id",
        fetch_all=True,
    ) or []
    return render_template('admin/fiscal_nfe_configuracao_lista.html', configs=configs)


_NFE_CONFIG_DEFAULTS = {
    'id': None,
    'tenant_slug': '',
    'razao_social': '', 'nome_fantasia': '', 'cnpj': '', 'ie': '', 'crt': 3,
    'logradouro': '', 'numero': '', 'complemento': '', 'bairro': '',
    'cep': '', 'x_mun': 'Brasilia', 'c_mun': '5300108', 'uf': 'DF',
    'fone': '', 'email': '',
    'x_prod': 'Livro Digital',
    'ncm': '49011000', 'cfop': '5102',
    'nat_op': 'VENDA DE PRODUTO DIGITAL',
    'c_benef': 'DF811004',
    'cst_icms': '41', 'aliq_icms_deson': '0.1200', 'mot_des_icms': '90',
    'cst_pis': '06', 'cst_cofins': '06',
    'cst_ibs_cbs': '410', 'c_class_trib': '410009',
    'ambiente': 2, 'serie_padrao': '001', 'ultimo_numero_nfe': 0,
    'certificado_path': '/app/empresa/cert/empresa.pfx',
    'certificado_senha_env': 'NF_CERT_SENHA_EMPRESA',
    'ca_bundle_path': '', 'ativo': 1,
}


def _validar_nfe_config_form() -> tuple[dict | None, str | None]:
    """
    Valida e extrai os campos do formulário de nfe_configuracao.
    Retorna (campos_dict, None) em caso de sucesso ou (None, mensagem_de_erro).
    """
    aliq_raw = request.form.get('aliq_icms_deson', '').replace(',', '.').strip()
    aliq_dec = None
    if aliq_raw:
        try:
            aliq_pct = float(aliq_raw)
        except ValueError:
            return None, 'Alíquota ICMS inválida.'
        if not (0 <= aliq_pct <= 100):
            return None, 'Alíquota ICMS deve estar entre 0 e 100 (ex: 12 para 12%).'
        aliq_dec = round(aliq_pct / 100, 4)

    cnpj = ''.join(filter(str.isdigit, request.form.get('cnpj', '')))
    if len(cnpj) != 14:
        return None, 'CNPJ deve ter exatamente 14 dígitos.'

    campos = dict(
        razao_social=request.form.get('razao_social', '').strip(),
        nome_fantasia=request.form.get('nome_fantasia', '').strip() or None,
        cnpj=cnpj,
        ie=request.form.get('ie', '').strip() or None,
        crt=request.form.get('crt', '3'),
        logradouro=request.form.get('logradouro', '').strip(),
        numero=request.form.get('numero', '').strip(),
        complemento=request.form.get('complemento', '').strip() or None,
        bairro=request.form.get('bairro', '').strip(),
        cep=''.join(filter(str.isdigit, request.form.get('cep', ''))),
        x_mun=request.form.get('x_mun', '').strip(),
        c_mun=request.form.get('c_mun', '').strip(),
        uf=request.form.get('uf', '').strip().upper(),
        fone=request.form.get('fone', '').strip() or None,
        email=request.form.get('email', '').strip() or None,
        x_prod=request.form.get('x_prod', '').strip() or None,
        ncm=request.form.get('ncm', '').strip() or None,
        cfop=request.form.get('cfop', '').strip() or None,
        nat_op=request.form.get('nat_op', '').strip() or None,
        c_benef=request.form.get('c_benef', '').strip() or None,
        cst_icms=request.form.get('cst_icms', '').strip() or None,
        aliq_icms_deson=aliq_dec,
        mot_des_icms=request.form.get('mot_des_icms', '').strip() or None,
        cst_pis=request.form.get('cst_pis', '').strip() or None,
        cst_cofins=request.form.get('cst_cofins', '').strip() or None,
        cst_ibs_cbs=request.form.get('cst_ibs_cbs', '').strip() or None,
        c_class_trib=request.form.get('c_class_trib', '').strip() or None,
        ambiente=int(request.form.get('ambiente', 2)),
        serie_padrao=request.form.get('serie_padrao', '001').strip(),
        certificado_path=request.form.get('certificado_path', '').strip(),
        certificado_senha_env=request.form.get('certificado_senha_env', '').strip(),
        ca_bundle_path=request.form.get('ca_bundle_path', '').strip() or None,
        ativo=1 if request.form.get('ativo') else 0,
    )
    return campos, None


@admin_bp.route('/fiscal/configuracao/novo', methods=['GET', 'POST'])
@requer_admin
def fiscal_nfe_configuracao_novo():
    aliq_pct_form = '12'
    if request.method == 'POST':
        aliq_pct_form = request.form.get('aliq_icms_deson', '12')
        campos, erro = _validar_nfe_config_form()
        if erro:
            flash(erro, 'danger')
        else:
            try:
                db.execute_query(
                    """INSERT INTO nfe_configuracao
                       (tenant_slug, api_key, razao_social, nome_fantasia, cnpj, ie, crt,
                        logradouro, numero, complemento, bairro, cep, x_mun, c_mun, uf, fone, email,
                        x_prod, ncm, cfop, nat_op, c_benef,
                        cst_icms, aliq_icms_deson, mot_des_icms, cst_pis, cst_cofins,
                        cst_ibs_cbs, c_class_trib,
                        ambiente, serie_padrao, certificado_path, certificado_senha_env,
                        ca_bundle_path, ativo)
                       VALUES (%s, UUID(), %s, %s, %s, %s, %s,
                               %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               %s, %s, %s, %s, %s,
                               %s, %s, %s, %s, %s,
                               %s, %s,
                               %s, %s, %s, %s,
                               %s, %s)""",
                    (
                        request.form.get('tenant_slug', '').strip().lower(),
                        campos['razao_social'], campos['nome_fantasia'], campos['cnpj'],
                        campos['ie'], campos['crt'],
                        campos['logradouro'], campos['numero'], campos['complemento'],
                        campos['bairro'], campos['cep'], campos['x_mun'], campos['c_mun'],
                        campos['uf'], campos['fone'], campos['email'],
                        campos['x_prod'], campos['ncm'], campos['cfop'],
                        campos['nat_op'], campos['c_benef'],
                        campos['cst_icms'], campos['aliq_icms_deson'], campos['mot_des_icms'],
                        campos['cst_pis'], campos['cst_cofins'],
                        campos['cst_ibs_cbs'], campos['c_class_trib'],
                        campos['ambiente'], campos['serie_padrao'],
                        campos['certificado_path'], campos['certificado_senha_env'],
                        campos['ca_bundle_path'], campos['ativo'],
                    ),
                )
                flash('Configuração criada com sucesso.', 'success')
                logger.info(f'[ADMIN] Nova NF-e config criada por {current_user.email}')
                return redirect(url_for('admin.fiscal_nfe_configuracao_lista'))
            except Exception as e:
                logger.error(f'[ADMIN] Erro ao criar NF-e config: {e}')
                # Exibe mensagem genérica para não vazar detalhes do banco para o admin
                if 'Duplicate entry' in str(e):
                    flash('Tenant slug já cadastrado. Escolha um identificador diferente.', 'danger')
                else:
                    flash('Erro ao salvar. Verifique os dados e tente novamente.', 'danger')

    config = dict(_NFE_CONFIG_DEFAULTS)
    return render_template(
        'admin/fiscal_nfe_configuracao_editar.html',
        config=config,
        aliq_pct=aliq_pct_form,
        novo=True,
    )


@admin_bp.route('/fiscal/configuracao/<int:config_id>', methods=['GET', 'POST'])
@requer_admin
def fiscal_nfe_configuracao_editar(config_id):
    config = db.execute_query(
        "SELECT * FROM nfe_configuracao WHERE id = %s", (config_id,), fetch_one=True
    )
    if not config:
        flash('Configuração NF-e não encontrada.', 'danger')
        return redirect(url_for('admin.fiscal_nfe_configuracao_lista'))

    if request.method == 'POST':
        campos, erro = _validar_nfe_config_form()
        if erro:
            flash(erro, 'danger')
        else:
            try:
                db.execute_query(
                    """UPDATE nfe_configuracao SET
                        razao_social=%s, nome_fantasia=%s, cnpj=%s, ie=%s, crt=%s,
                        logradouro=%s, numero=%s, complemento=%s, bairro=%s,
                        cep=%s, x_mun=%s, c_mun=%s, uf=%s, fone=%s, email=%s,
                        x_prod=%s, ncm=%s, cfop=%s, nat_op=%s, c_benef=%s,
                        cst_icms=%s, aliq_icms_deson=%s, mot_des_icms=%s,
                        cst_pis=%s, cst_cofins=%s, cst_ibs_cbs=%s, c_class_trib=%s,
                        ambiente=%s, serie_padrao=%s,
                        certificado_path=%s, certificado_senha_env=%s, ca_bundle_path=%s,
                        ativo=%s
                       WHERE id=%s""",
                    (
                        campos['razao_social'], campos['nome_fantasia'], campos['cnpj'],
                        campos['ie'], campos['crt'],
                        campos['logradouro'], campos['numero'], campos['complemento'],
                        campos['bairro'], campos['cep'], campos['x_mun'], campos['c_mun'],
                        campos['uf'], campos['fone'], campos['email'],
                        campos['x_prod'], campos['ncm'], campos['cfop'],
                        campos['nat_op'], campos['c_benef'],
                        campos['cst_icms'], campos['aliq_icms_deson'], campos['mot_des_icms'],
                        campos['cst_pis'], campos['cst_cofins'],
                        campos['cst_ibs_cbs'], campos['c_class_trib'],
                        campos['ambiente'], campos['serie_padrao'],
                        campos['certificado_path'], campos['certificado_senha_env'],
                        campos['ca_bundle_path'], campos['ativo'],
                        config_id,
                    ),
                )
                flash('Configuração salva com sucesso.', 'success')
                logger.info(f'[ADMIN] NF-e config id={config_id} atualizada por {current_user.email}')
                return redirect(url_for('admin.fiscal_nfe_configuracao_editar', config_id=config_id))
            except Exception as e:
                logger.error(f'[ADMIN] Erro ao salvar NF-e config id={config_id}: {e}')
                flash('Erro ao salvar. Verifique os dados e tente novamente.', 'danger')

    aliq_pct = ''
    if config.get('aliq_icms_deson') is not None:
        aliq_pct = f"{float(config['aliq_icms_deson']) * 100:.2f}".rstrip('0').rstrip('.')

    return render_template(
        'admin/fiscal_nfe_configuracao_editar.html',
        config=config,
        aliq_pct=aliq_pct,
    )


@admin_bp.route('/fiscal/configuracao/<int:config_id>/testar', methods=['POST'])
@requer_admin
def fiscal_nfe_testar_conexao(config_id):
    from flask import jsonify
    import os
    config = db.execute_query(
        "SELECT * FROM nfe_configuracao WHERE id = %s", (config_id,), fetch_one=True
    )
    if not config:
        return jsonify({'ok': False, 'mensagem': 'Configuração não encontrada.'}), 404

    try:
        cert_path = config.get('certificado_path', '')
        if not os.path.exists(cert_path):
            return jsonify({'ok': False, 'mensagem': f'Certificado não encontrado: {cert_path}'})

        senha_env = config.get('certificado_senha_env', '')
        senha = os.getenv(senha_env, '')
        if not senha:
            return jsonify({'ok': False, 'mensagem': f'Variável {senha_env!r} não definida no ambiente do servidor.'})

        from fiscal.nfe_soap import consultar_status_servico
        ca_bundle = config.get('ca_bundle_path') or False
        resultado = consultar_status_servico(
            cert_pfx=cert_path,
            cert_senha=senha,
            ambiente=int(config.get('ambiente', 2)),
            verify=ca_bundle,
        )
        ok = resultado.get('c_stat') == '107'
        return jsonify({
            'ok': ok,
            'c_stat': resultado.get('c_stat', ''),
            'mensagem': resultado.get('x_motivo', ''),
        })
    except Exception as e:
        logger.error(f'[ADMIN] Erro ao testar SEFAZ config={config_id}: {e}')
        return jsonify({'ok': False, 'mensagem': 'Erro ao conectar ao SEFAZ. Verifique os logs do servidor.'})


@admin_bp.route('/fiscal/nfe/<int:nfe_id>/danfe')
@requer_admin
def fiscal_danfe(nfe_id):
    from flask import Response
    row = db.execute_query(
        "SELECT xml_nfe_proc, xml_assinado, chave_acesso FROM nfe_emitidas WHERE id = %s",
        (nfe_id,),
        fetch_one=True,
    )
    if not row:
        return 'NF-e não encontrada', 404
    xml = row['xml_nfe_proc'] or row['xml_assinado']
    if not xml:
        return 'XML da NF-e não disponível', 404
    try:
        from brazilfiscalreport.danfe import Danfe
        danfe = Danfe(xml=xml.encode('utf-8') if isinstance(xml, str) else xml)
        pdf_bytes = danfe.output()
    except Exception as e:
        logger.error(f'[ADMIN] Erro ao gerar DANFE nfe_id={nfe_id}: {e}')
        return f'Erro ao gerar DANFE: {e}', 500
    chave = row['chave_acesso'] or str(nfe_id)
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename="danfe_{chave}.pdf"'},
    )


@admin_bp.route('/produto/<int:produto_id>/financeiro/atualizar-pix', methods=['POST'])
@requer_admin
def financeiro_atualizar_pix(produto_id):
    try:
        from celery_app import celery_app
        tenant_slug = buscar_tenant_slug_produto(produto_id)
        celery_app.send_task('tasks.processar_pagamentos_pix', kwargs={'tenant_slug': tenant_slug})
        return jsonify({'ok': True, 'msg': 'Busca de PIX iniciada. Aguarde alguns segundos e atualize a página.'})
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao disparar task PIX: {e}")
        return jsonify({'ok': False, 'msg': f'Erro ao iniciar busca: {e}'}), 500


# ── Pagamentos ────────────────────────────────────────────────────────────

PAGAMENTOS_POR_PAGINA = 50

# estado_id: 0 = pago via WhatsApp, 1000 = pago via Web (Pix/BB Pay)
ORIGEM_ESTADOS = {
    'todos': (0, 1000),
    'whatsapp': (0,),
    'web': (1000,),
}

_SQL_PAGAMENTOS_TOTAL = """
    SELECT COUNT(*) as total
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id IN ({placeholders})
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
        valor_pago,
        estado_id
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id IN ({placeholders})
      AND data_pagamento BETWEEN %s AND %s
    ORDER BY data_pagamento DESC
    LIMIT %s
    OFFSET %s
"""

_SQL_PAGAMENTOS_RECEITA = """
    SELECT SUM(valor_pago) AS receita_total
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id IN ({placeholders})
      AND data_pagamento BETWEEN %s AND %s
"""

# Contadores por origem, independentes do filtro selecionado (alimentam os botões do seletor).
# 0 e 1000 aqui são literais fixos, não vêm de input do usuário -- seguro embutir na SQL.
_SQL_PAGAMENTOS_COUNTS_ORIGEM = """
    SELECT
        COUNT(CASE WHEN estado_id = 0    THEN 1 END) AS total_whatsapp,
        COUNT(CASE WHEN estado_id = 1000 THEN 1 END) AS total_web
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id IN (0, 1000)
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

    origem = request.args.get('origem', 'todos')
    if origem not in ORIGEM_ESTADOS:
        origem = 'todos'
    estados = ORIGEM_ESTADOS[origem]
    placeholders = ','.join(['%s'] * len(estados))

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

    sql_total = _SQL_PAGAMENTOS_TOTAL.format(placeholders=placeholders)
    sql_lista = _SQL_PAGAMENTOS_LISTA.format(placeholders=placeholders)
    sql_receita = _SQL_PAGAMENTOS_RECEITA.format(placeholders=placeholders)

    try:
        # Contar total de registros
        total_result = db.execute_query(sql_total, (produto_id, *estados, data_ini, data_fim), fetch_one=True)
        total_registros = total_result['total'] if total_result else 0
        total_paginas = (total_registros + PAGAMENTOS_POR_PAGINA - 1) // PAGAMENTOS_POR_PAGINA or 1

        # Validar página (se for > total, redirecionar para última)
        if pagina_atual > total_paginas:
            return redirect(url_for('admin.pagamentos_produto',
                                  produto_id=produto_id,
                                  data_ini=data_ini_str,
                                  data_fim=data_fim_str,
                                  origem=origem,
                                  page=total_paginas))

        # Calcular offset
        offset = (pagina_atual - 1) * PAGAMENTOS_POR_PAGINA

        # Buscar pedidos da página
        pedidos = db.execute_query(
            sql_lista,
            (produto_id, *estados, data_ini, data_fim, PAGAMENTOS_POR_PAGINA, offset),
            fetch_all=True
        )

        # Buscar receita do período
        receita_result = db.execute_query(sql_receita, (produto_id, *estados, data_ini, data_fim), fetch_one=True)
        receita_total = receita_result['receita_total'] or 0 if receita_result else 0

        # Contadores por origem (independentes do filtro selecionado, para os botões do seletor)
        counts_result = db.execute_query(_SQL_PAGAMENTOS_COUNTS_ORIGEM, (produto_id, data_ini, data_fim), fetch_one=True)
        count_whatsapp = (counts_result['total_whatsapp'] or 0) if counts_result else 0
        count_web = (counts_result['total_web'] or 0) if counts_result else 0
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao carregar pagamentos produto #{produto_id}: {e}")
        flash('Erro ao carregar pagamentos.', 'danger')
        pedidos = []
        receita_total = 0
        total_registros = 0
        total_paginas = 1
        pagina_atual = 1
        count_whatsapp = 0
        count_web = 0

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
        origem=origem,
        count_whatsapp=count_whatsapp,
        count_web=count_web,
        count_todos=count_whatsapp + count_web,
    )


@admin_bp.route('/pedido/<int:pedido_id>/itens')
@requer_login
def visualizar_itens_pedido(pedido_id):
    """AJAX endpoint: retorna os itens (principal/bônus/bump) de um pedido para o popup de detalhe"""
    try:
        pedido = get_pedido(pedido_id)
        if not pedido:
            return jsonify({'ok': False, 'msg': 'Pedido não encontrado'}), 404

        if (not current_user.is_admin()) and (not usuario_tem_acesso_produto(current_user.id, pedido['produto_id'])):
            logger.warning(f"[ADMIN] ⚠️ Acesso negado aos itens do pedido: user={current_user.email} pedido_id={pedido_id} produto_id={pedido['produto_id']}")
            return jsonify({'ok': False, 'msg': 'Acesso negado'}), 403

        itens = listar_itens_pedido(pedido_id)

        return jsonify({
            'ok': True,
            'pedido': {
                'id': pedido_id,
                'valor_pago': float(pedido['valor_pago'] or 0),
                'nome_pagador': pedido.get('nome_pagador') or pedido.get('contact_name'),
                'data_pagamento': pedido['data_pagamento'].strftime('%d/%m/%Y %H:%M') if pedido.get('data_pagamento') else None,
            },
            'itens': [
                {'tipo': item['tipo'], 'nome': item['nome'], 'valor': float(item['valor'] or 0)}
                for item in itens
            ],
        })
    except Exception as e:
        logger.error(f"[ADMIN] ❌ Erro ao carregar itens do pedido #{pedido_id}: {e}")
        return jsonify({'ok': False, 'msg': f'Erro ao carregar detalhes: {e}'}), 500


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
