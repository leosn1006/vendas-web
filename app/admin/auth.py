from flask import render_template, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from database import db
import logging

logger = logging.getLogger(__name__)

# ============================================================
# Modelo de usuário para o Flask-Login
# ============================================================
class Usuario(UserMixin):
    def __init__(self, id, email, nome, perfil, ativo, primeiro_acesso=False):
        self.id              = id
        self.email           = email
        self.nome            = nome
        self.perfil          = perfil
        self.ativo           = ativo
        self.primeiro_acesso = primeiro_acesso

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
            id              = usuario['id'],
            email           = usuario['email'],
            nome            = usuario['nome'],
            perfil          = usuario['perfil'],
            ativo           = usuario['ativo'],
            primeiro_acesso = bool(usuario.get('primeiro_acesso', False)),
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


def usuario_tem_acesso_produto(usuario_id, produto_id):
    """Retorna True se o usuário tem vínculo com o produto (admin sempre tem)."""
    try:
        row = db.execute_query(
            "SELECT 1 FROM usuario_produtos WHERE usuario_id = %s AND produto_id = %s",
            (usuario_id, produto_id),
            fetch_one=True
        )
        return row is not None
    except Exception as e:
        logger.error(f"[AUTH] ❌ Erro ao verificar acesso ao produto: {e}")
        return False


def requer_acesso_produto(f):
    """Verifica se o usuário tem acesso ao produto identificado na URL (kwargs: produto_id ou id)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('admin.login'))
        if not current_user.is_admin():
            produto_id = kwargs.get('produto_id') or kwargs.get('id')
            if produto_id is None:
                abort(403)
            if not usuario_tem_acesso_produto(current_user.id, produto_id):
                logger.warning(
                    f"[AUTH] ⚠️ {current_user.email} sem acesso ao produto #{produto_id}"
                )
                abort(403)
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
                    id              = usuario['id'],
                    email           = usuario['email'],
                    nome            = usuario['nome'],
                    perfil          = usuario['perfil'],
                    ativo           = usuario['ativo'],
                    primeiro_acesso = bool(usuario.get('primeiro_acesso', False)),
                )
                login_user(user_obj, remember=True)
                logger.info(f"[AUTH] ✅ Login: {email} ({usuario['perfil']})")

                if user_obj.primeiro_acesso:
                    return redirect(url_for('admin.alterar_senha'))

                from urllib.parse import urlparse, urljoin as _urljoin
                def _url_segura(url):
                    if not url:
                        return False
                    ref  = urlparse(request.host_url)
                    test = urlparse(_urljoin(request.host_url, url))
                    return test.scheme in ('http', 'https') and ref.netloc == test.netloc
                next_page = request.args.get('next')
                return redirect(next_page if _url_segura(next_page) else url_for('admin.dashboard'))
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


# ============================================================
# Alterar senha (obrigatório no primeiro acesso)
# ============================================================

# Endpoints que ficam acessíveis mesmo durante o primeiro acesso
_ENDPOINTS_LIVRES = {'admin.alterar_senha', 'admin.logout', 'admin.login'}

@admin_bp.before_request
def forcar_troca_senha():
    """Redireciona para alterar_senha enquanto primeiro_acesso for True."""
    if request.endpoint in _ENDPOINTS_LIVRES:
        return
    if current_user.is_authenticated and current_user.primeiro_acesso:
        return redirect(url_for('admin.alterar_senha'))


@admin_bp.route('/alterar-senha', methods=['GET', 'POST'])
@requer_login
def alterar_senha():
    if request.method == 'POST':
        nova        = request.form.get('nova_senha', '')
        confirmacao = request.form.get('confirmacao', '')

        if not nova:
            flash('Informe a nova senha.', 'danger')
        elif nova == '1234':
            flash('A nova senha não pode ser "1234". Escolha uma senha pessoal.', 'danger')
        elif nova != confirmacao:
            flash('As senhas não coincidem.', 'danger')
        elif len(nova) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
        else:
            try:
                db.execute_query(
                    "UPDATE usuarios SET senha = %s, primeiro_acesso = FALSE WHERE id = %s",
                    (generate_password_hash(nova), current_user.id)
                )
                current_user.primeiro_acesso = False
                logger.info(f"[AUTH] ✅ Senha alterada por {current_user.email}")
                flash('Senha alterada com sucesso!', 'success')
                return redirect(url_for('admin.dashboard'))
            except Exception as e:
                logger.error(f"[AUTH] ❌ Erro ao alterar senha: {e}")
                flash('Erro interno ao salvar senha. Tente novamente.', 'danger')

    return render_template('admin/alterar_senha.html')
