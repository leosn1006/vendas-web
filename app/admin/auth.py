from flask import render_template, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from database import db
import logging

logger = logging.getLogger(__name__)

# ============================================================
# Modelo de usuário para o Flask-Login
# ============================================================
class Usuario(UserMixin):
    def __init__(self, id, email, nome, perfil, ativo):
        self.id     = id
        self.email  = email
        self.nome   = nome
        self.perfil = perfil
        self.ativo  = ativo

    def is_admin(self):
        return self.perfil == 'admin'

    def is_active(self):
        return self.ativo

# ============================================================
# Configuração do LoginManager
# ============================================================
login_manager = LoginManager()

def init_login_manager(app):
    login_manager.init_app(app)
    login_manager.login_view           = 'admin.login'
    login_manager.login_message        = 'Por favor, faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    """Carrega o usuário da sessão — chamado pelo Flask-Login a cada request."""
    try:
        query = "SELECT * FROM usuarios WHERE id = %s AND ativo = TRUE"
        usuario = db.execute_query(query, (user_id,), fetch_one=True)
        if usuario is None:
            return None
        return Usuario(
            id     = usuario['id'],
            email  = usuario['email'],
            nome   = usuario['nome'],
            perfil = usuario['perfil'],
            ativo  = usuario['ativo']
        )
    except Exception as e:
        logger.error(f"[AUTH] ❌ Erro ao carregar usuário: {e}")
        return None

# ============================================================
# Decorators de perfil
# ============================================================
from functools import wraps
from flask import abort

def requer_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login'))
        if not current_user.is_admin():
            logger.warning(f"[AUTH] ⚠️ Acesso negado para {current_user.email} — perfil: {current_user.perfil}")
            abort(403)
        return f(*args, **kwargs)
    return decorated

def requer_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated

# ============================================================
# Rotas de autenticação
# ============================================================
from admin import admin_bp

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '')

        try:
            query = "SELECT * FROM usuarios WHERE email = %s AND ativo = TRUE"
            usuario = db.execute_query(query, (email,), fetch_one=True)

            if usuario and check_password_hash(usuario['senha'], senha):
                user_obj = Usuario(
                    id     = usuario['id'],
                    email  = usuario['email'],
                    nome   = usuario['nome'],
                    perfil = usuario['perfil'],
                    ativo  = usuario['ativo']
                )
                login_user(user_obj, remember=True)
                logger.info(f"[AUTH] ✅ Login: {email} ({usuario['perfil']})")

                next_page = request.args.get('next')
                return redirect(next_page or url_for('admin.dashboard'))
            else:
                flash('E-mail ou senha incorretos.', 'danger')
                logger.warning(f"[AUTH] ⚠️ Tentativa de login inválida: {email}")

        except Exception as e:
            logger.error(f"[AUTH] ❌ Erro no login: {e}")
            flash('Erro interno. Tente novamente.', 'danger')

    return render_template('admin/login.html')

@admin_bp.route('/logout')
@login_required
def logout():
    logger.info(f"[AUTH] 👋 Logout: {current_user.email}")
    logout_user()
    return redirect(url_for('admin.login'))
