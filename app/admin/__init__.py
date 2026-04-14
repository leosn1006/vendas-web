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

        return dict(
            produtos_lista     = produtos,
            produto_ativo      = produto_ativo,
            has_produto_acesso = has_produto_acesso,
        )
    except Exception:
        return dict(produtos_lista=[], produto_ativo=None, has_produto_acesso=False)
