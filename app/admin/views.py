import logging
import os
import datetime
import subprocess
import tempfile
from flask import render_template, redirect, url_for, request, flash, session, current_app
from flask_login import current_user
from werkzeug.utils import secure_filename
from admin import admin_bp
from admin.auth import requer_login, requer_admin
from database import (db,
    listar_telefones_produto, adicionar_telefone_produto, remover_telefone_produto,
    listar_mensagens_sugeridas, adicionar_mensagem_sugerida, remover_mensagem_sugerida,
    listar_acoes_fluxo, get_acao_fluxo,
    adicionar_acao_fluxo, atualizar_acao_fluxo, remover_acao_fluxo,
    get_pedido, get_ultimo_pedido_by_phone, salvar_mensagem_pedido,
    buscar_todas_mensagens_pedido,
    buscar_pedido_por_nome, acertar_valor_pedido)

_FLUXOS = ['introducao', 'pedido', 'comprovante', 'responder', 'followup', 'confirmacao_web']
_FLUXOS_READONLY = {'responder'}
_FLUXOS_LABELS = {
    'introducao':      '👋 Introdução',
    'pedido':          '📦 Pedido',
    'comprovante':     '🧾 Comprovante',
    'responder':       '💬 Responder',
    'followup':        '🔔 Follow-up',
    'confirmacao_web': '🌐 Confirmação Web',
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
@requer_login
def agente_vendas_produto(produto_id):
    produto = db.execute_query(
        "SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True
    )
    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))

    if request.method == 'POST':
        if not current_user.is_admin():
            flash('Você não tem permissão para editar produtos.', 'danger')
            return redirect(url_for('admin.agente_vendas_produto', produto_id=produto_id))
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
@requer_login
def dados_basicos_produto(produto_id):
    produto = db.execute_query(
        "SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True
    )
    if produto is None:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin.listar_produtos'))

    if request.method == 'POST':
        if not current_user.is_admin():
            flash('Você não tem permissão para editar produtos.', 'danger')
            return redirect(url_for('admin.dados_basicos_produto', produto_id=produto_id))
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
# Conversas — visualização e envio manual de mensagens
# ============================================================
@admin_bp.route('/produto/<int:produto_id>/conversas', methods=['GET', 'POST'])
@requer_login
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
@requer_login
def conversa_pedido(produto_id, pedido_id):
    session['produto_ativo_id'] = produto_id
    produto = db.execute_query("SELECT * FROM produtos WHERE id = %s", (produto_id,), fetch_one=True)
    pedido  = get_pedido(pedido_id)

    if not produto or not pedido or pedido.get('produto_id') != produto_id:
        flash('Conversa não encontrada.', 'danger')
        return redirect(url_for('admin.conversas_produto', produto_id=produto_id))

    mensagens = buscar_todas_mensagens_pedido(pedido_id)
    return render_template('admin/produto_conversas.html',
                           produto=produto, pedido=pedido, mensagens=mensagens)


@admin_bp.route('/produto/<int:produto_id>/conversas/<int:pedido_id>/enviar', methods=['POST'])
@requer_admin
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
@requer_admin
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
@requer_admin
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
        session['produto_ativo_id'] = produto_id
        return redirect(url_for('admin.analytics_produto', produto_id=produto_id))
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
    api_phone_number_id = request.form.get('api_phone_number_id', '').strip() or None
    try:
        adicionar_telefone_produto(telefone, produto_id, api_phone_number_id)
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
        bitrate = max(12, min(64, int(490 * 8 / duracao)))
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

    tamanho_saida = os.path.getsize(caminho_saida)
    logger.info(f"[AUDIO-UPLOAD] duracao={duracao:.1f}s bitrate={bitrate}k tamanho_saida={tamanho_saida // 1024}KB")
    if tamanho_saida > 500 * 1024:
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
        COALESCE(NULLIF(campaignid, ''), 'Campanha não informada') AS campanha,
        COUNT(*)                AS quantidade,
        COALESCE(SUM(valor_pago), 0) AS total
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id = 0
      AND data_pagamento BETWEEN %s AND %s
    GROUP BY campaignid
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
        COALESCE(NULLIF(campaignid, ''), 'Campanha não informada') AS campanha,
        COUNT(*)                     AS quantidade,
        COALESCE(SUM(valor_pago), 0) AS total
    FROM pedidos
    WHERE produto_id = %s
      AND estado_id = 1000
      AND data_pagamento BETWEEN %s AND %s
    GROUP BY campaignid
    ORDER BY total DESC
"""


@admin_bp.route('/produto/<int:produto_id>/analytics')
@requer_login
def analytics_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    hoje = datetime.date.today()
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
@requer_login
def analytics_web_produto(produto_id):
    session['produto_ativo_id'] = produto_id
    produto = _get_produto_or_redirect(produto_id)
    if not produto:
        return redirect(url_for('admin.dashboard'))

    hoje = datetime.date.today()
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
