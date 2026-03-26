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
    """Injeta produtos_lista e produto_ativo em todos os templates do admin."""
    from flask_login import current_user
    from database import db
    if not current_user.is_authenticated:
        return dict(produtos_lista=[], produto_ativo=None)
    try:
        produtos = db.execute_query(
            "SELECT id, nome FROM produtos ORDER BY nome",
            fetch_all=True
        ) or []
        produto_ativo_id = request.view_args.get('produto_id') or session.get('produto_ativo_id')
        produto_ativo = next((p for p in produtos if p['id'] == produto_ativo_id), None)
        return dict(produtos_lista=produtos, produto_ativo=produto_ativo)
    except Exception:
        return dict(produtos_lista=[], produto_ativo=None)
