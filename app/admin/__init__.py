from flask import Blueprint

admin_bp = Blueprint(
    'admin',
    __name__,
    template_folder='templates',
    url_prefix='/admin'
)

from admin import auth, views  # noqa: E402, F401 — era "from app.admin"
