from flask import Blueprint, request, session

admin_bp = Blueprint(
    'admin',
    __name__,
    template_folder='templates',
    url_prefix='/admin'
)

from admin import auth, views  # noqa: E402, F401 — era "from app.admin"


@admin_bp.context_processor
def inject_produto_ativo():
    """Injeta produtos_lista, produto_ativo e has_produto_acesso em todos os templates do admin."""
    from flask_login import current_user
    from database import db
    if not current_user.is_authenticated:
        return dict(produtos_lista=[], produto_ativo=None, has_produto_acesso=False)
    try:
        if current_user.is_admin():
            produtos = db.execute_query(
                "SELECT id, nome FROM produtos WHERE ativo = TRUE ORDER BY nome",
                fetch_all=True
            ) or []
        else:
            produtos = db.execute_query(
                """SELECT p.id, p.nome
                   FROM produtos p
                   INNER JOIN usuario_produtos up ON up.produto_id = p.id
                   WHERE up.usuario_id = %s AND p.ativo = TRUE
                   ORDER BY p.nome""",
                (current_user.id,),
                fetch_all=True
            ) or []

        produto_ativo_id = request.view_args.get('produto_id') or session.get('produto_ativo_id')
        produto_ativo    = next((p for p in produtos if p['id'] == produto_ativo_id), None)

        # has_produto_acesso é True quando o usuário tem vínculo com o produto ativo
        # (admins sempre têm acesso; para consulta, o produto precisa estar na lista filtrada)
        has_produto_acesso = produto_ativo is not None

        badge_notificacoes = 0
        badge_notificacoes_web = 0
        badge_qualidade_cor = None   # None | 'green' | 'yellow' | 'red'
        badge_qualidade_qtd = 0
        if produto_ativo:
            from database import contar_notificacoes_em_analise
            badge_notificacoes = contar_notificacoes_em_analise(produto_ativo['id'])
            badge_notificacoes_web = contar_notificacoes_em_analise(produto_ativo['id'], motivo='sugestao_resposta_email')

            # Try/except isolado: uma falha aqui (ex: migration de qualidade ainda não aplicada
            # nesse ambiente) não pode apagar o badge_notificacoes calculado acima, que é uma
            # feature pré-existente sem relação nenhuma com qualidade de WhatsApp.
            try:
                from database import contar_telefones_por_qualidade
                contagem_q = contar_telefones_por_qualidade(produto_ativo['id'])
                if contagem_q['RED'] > 0:
                    badge_qualidade_cor, badge_qualidade_qtd = 'red', contagem_q['RED']
                elif contagem_q['YELLOW'] > 0:
                    badge_qualidade_cor, badge_qualidade_qtd = 'yellow', contagem_q['YELLOW']
                elif contagem_q['GREEN'] > 0:
                    badge_qualidade_cor = 'green'
            except Exception:
                pass  # badge de qualidade fica None/0; resto da navegação segue normal

        return dict(
            produtos_lista        = produtos,
            produto_ativo         = produto_ativo,
            has_produto_acesso    = has_produto_acesso,
            badge_notificacoes    = badge_notificacoes,
            badge_notificacoes_web = badge_notificacoes_web,
            badge_qualidade_cor   = badge_qualidade_cor,
            badge_qualidade_qtd   = badge_qualidade_qtd,
        )
    except Exception:
        return dict(produtos_lista=[], produto_ativo=None, has_produto_acesso=False, badge_notificacoes=0,
                     badge_notificacoes_web=0, badge_qualidade_cor=None, badge_qualidade_qtd=0)
