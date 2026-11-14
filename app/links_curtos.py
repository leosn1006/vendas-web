"""Link curto do sistema: /m/<codigo> → o endereço completo (docs/SMS.md "Link curto").

Nasceu para o SMS (160 caracteres não comportam o link da prévia ou do checkout), mas serve qualquer canal. Cada
acesso fica registrado (links_curtos_acessos), existente ou não, para avaliarmos com dados o risco de alguém chutar
códigos: não há bloqueio por IP porque as operadoras põem milhares de clientes atrás do mesmo IP (CGNAT).
"""
import logging
import re
import secrets

from flask import Blueprint, redirect, request

logger = logging.getLogger(__name__)

# 57 símbolos (sem 0 O 1 l I, que se confundem ao ler ou digitar) × 7 posições ≈ 1,9 trilhão de códigos.
ALFABETO = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
TAMANHO = 7
# O nginx derruba (444) qualquer URL que contenha estes trechos (filtro anti-robô em infra/nginx/conf.d): o código
# nunca pode formá-los, em maiúscula ou minúscula.
_PROIBIDOS = re.compile(r'aws|dump|wp-|backup|config', re.IGNORECASE)
_CODIGO_VALIDO = re.compile(r'^[A-Za-z0-9]{4,16}$')

# Quem "clica" sem ser gente: pré-visualização de link (WhatsApp, iMessage = facebookexternalhit, Telegram...),
# verificadores de e-mail/antivírus e clientes HTTP. Não contam como clique (o acesso fica registrado como robô).
_ROBOS = ('bot', 'crawler', 'spider', 'preview', 'facebookexternalhit', 'whatsapp', 'curl', 'wget', 'python',
          'httpclient', 'go-http', 'okhttp', 'java/', 'headless', 'proofpoint', 'barracuda', 'mimecast', 'scanner')

bp = Blueprint('links_curtos', __name__)


def gerar_codigo() -> str:
    while True:
        codigo = ''.join(secrets.choice(ALFABETO) for _ in range(TAMANHO))
        if not _PROIBIDOS.search(codigo):
            return codigo


def eh_robo(user_agent: str | None, metodo: str = 'GET') -> bool:
    ua = (user_agent or '').lower()
    return metodo != 'GET' or not ua or any(marca in ua for marca in _ROBOS)


def criar(url_destino: str, origem: str, ref_tipo: str | None = None, ref_id: int | None = None,
          expira_em=None) -> dict:
    """Grava um link novo; devolve {'id', 'codigo'}. Colisão de código (quase impossível) sorteia de novo."""
    from database import db
    for _ in range(5):
        codigo = gerar_codigo()
        try:
            link_id = db.execute_query(
                "INSERT INTO links_curtos (codigo, url_destino, origem, ref_tipo, ref_id, expira_em) "
                "VALUES (%s, %s, %s, %s, %s, %s)", (codigo, url_destino, origem, ref_tipo, ref_id, expira_em))
            return {'id': link_id, 'codigo': codigo}
        except Exception as e:
            if 'Duplicate' not in str(e):
                raise
    raise RuntimeError('Não consegui gerar um código curto único')


def endereco(dominio_base: str, codigo: str) -> str:
    """Como o link vai no texto: sem https:// (os celulares reconhecem 'dominio.com.br/m/abc' como link)."""
    return f"{re.sub(r'^https?://', '', dominio_base or '').rstrip('/')}/m/{codigo}"


def _registrar(codigo, link, robo):
    from database import db
    ip = (request.headers.get('X-Real-IP') or request.remote_addr or '')[:45]   # nginx manda X-Real-IP
    db.execute_query("INSERT INTO links_curtos_acessos (codigo_tentado, link_id, ip, user_agent, robo) "
                     "VALUES (%s, %s, %s, %s, %s)",
                     (codigo[:40], link['id'] if link else None, ip or None,
                      (request.headers.get('User-Agent') or '')[:300] or None, int(robo)))
    if link and not robo:
        db.execute_query("UPDATE links_curtos SET cliques_humanos = cliques_humanos + 1, "
                         "primeiro_clique_em = COALESCE(primeiro_clique_em, NOW()) WHERE id = %s", (link['id'],))


@bp.route('/m/<codigo>', methods=['GET', 'HEAD'])
def abrir(codigo):
    from database import db
    link = None
    try:
        if _CODIGO_VALIDO.match(codigo):
            link = db.execute_query("SELECT id, url_destino FROM links_curtos WHERE codigo = %s "
                                    "AND (expira_em IS NULL OR expira_em > NOW())", (codigo,), fetch_one=True)
        _registrar(codigo, link, eh_robo(request.headers.get('User-Agent'), request.method))
    except Exception:
        logger.exception(f'[LINK CURTO] Falha ao abrir /m/{codigo[:40]}')
    # Inexistente ou expirado: a página inicial do domínio, em vez de um 404 seco.
    return redirect(link['url_destino'] if link else '/', code=302)


def limpar_acessos(dias: int = 90) -> int:
    """IP é dado pessoal: apaga os acessos com mais de `dias` (chamado pela limpeza diária)."""
    from database import db
    return db.execute_query("DELETE FROM links_curtos_acessos WHERE criado_em < NOW() - INTERVAL %s DAY", (dias,),
                            return_rowcount=True) or 0
