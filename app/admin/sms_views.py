"""Admin → SMS enviados (só administradores): se o SMS está valendo a pena (enviados, entregues, clicaram, pagaram
depois, custo) e os acessos ao link curto, para avaliar com dados o risco de alguém chutar códigos (docs/SMS.md)."""
from flask import render_template, request

from admin import admin_bp
from admin.auth import requer_admin

PERIODOS = (1, 7, 30, 90)
# Celular brasileiro como o quiz/checkout gravam (com o 55; o quiz antigo gravou só DDD + número).
_TEM_CELULAR = "(m.whatsapp REGEXP '^55[0-9]{2}9[0-9]{8}$' OR m.whatsapp REGEXP '^[0-9]{2}9[0-9]{8}$')"


def _filtro(produto_id, coluna='e.produto_id'):
    return (f' AND {coluna} = %s', (produto_id,)) if produto_id else ('', ())


def _resumo(dias, produto_id):
    from database import db
    filtro, params = _filtro(produto_id)
    return db.execute_query(f"""
        SELECT COUNT(*) AS registrados,
               COALESCE(SUM(e.enviado_em IS NOT NULL), 0) AS enviados,
               COALESCE(SUM(e.status = 'entregue'), 0) AS entregues,
               COALESCE(SUM(e.status = 'falhou'), 0) AS falharam,
               COALESCE(SUM(e.status = 'ignorado_dev'), 0) AS ignorados_dev,
               COALESCE(SUM(CASE WHEN e.enviado_em IS NOT NULL THEN e.partes END), 0) AS partes,
               COUNT(DISTINCT CASE WHEN e.enviado_em IS NOT NULL THEN e.telefone END) AS pessoas,
               COUNT(DISTINCT CASE WHEN l.cliques_humanos > 0 THEN e.telefone END) AS clicaram,
               COUNT(DISTINCT CASE WHEN e.ref_tipo = 'musica' AND e.enviado_em IS NOT NULL THEN e.ref_id END)
                   AS musicas,
               COUNT(DISTINCT CASE WHEN e.ref_tipo = 'musica' AND m.liberada_em > e.enviado_em THEN e.ref_id END)
                   AS musicas_pagas
        FROM sms_envios e
        LEFT JOIN links_curtos l ON l.id = e.link_id
        LEFT JOIN musicas m ON e.ref_tipo = 'musica' AND m.id = e.ref_id
        WHERE e.criado_em >= NOW() - INTERVAL %s DAY{filtro}""", (dias, *params), fetch_one=True) or {}


def _comparacao_musica(dias, produto_id):
    """Músicas que chegaram na prévia no período: com celular (recebem SMS) x sem celular, e quantas pagaram."""
    from database import db
    filtro, params = _filtro(produto_id, 'm.produto_id')
    return db.execute_query(f"""
        SELECT {_TEM_CELULAR} AS com_celular, COUNT(*) AS musicas, COALESCE(SUM(m.liberada_em IS NOT NULL), 0) AS pagas
        FROM musicas m
        WHERE m.criado_em >= NOW() - INTERVAL %s DAY AND m.rascunho_de IS NULL AND m.status = 'previa_pronta'{filtro}
        GROUP BY com_celular ORDER BY com_celular DESC""", (dias, *params), fetch_all=True) or []


def _envios(dias, produto_id):
    from database import db
    filtro, params = _filtro(produto_id)
    return db.execute_query(f"""
        SELECT e.id, e.criado_em, e.enviado_em, e.entregue_em, e.origem, e.etapa, e.ref_tipo, e.ref_id, e.telefone,
               e.texto, e.status, e.erro, e.partes, p.nome AS produto, l.cliques_humanos, l.primeiro_clique_em,
               (e.ref_tipo = 'musica' AND m.liberada_em > e.enviado_em) AS pagou, m.liberada_em
        FROM sms_envios e
        LEFT JOIN produtos p ON p.id = e.produto_id
        LEFT JOIN links_curtos l ON l.id = e.link_id
        LEFT JOIN musicas m ON e.ref_tipo = 'musica' AND m.id = e.ref_id
        WHERE e.criado_em >= NOW() - INTERVAL %s DAY{filtro}
        ORDER BY e.id DESC LIMIT 300""", (dias, *params), fetch_all=True) or []


def _acessos(dias):
    """Acessos ao /m/ por dia e os IPs que mais tentam código inexistente (sinal de alguém chutando)."""
    from database import db
    por_dia = db.execute_query("""
        SELECT DATE(criado_em) AS dia, COUNT(*) AS total,
               COALESCE(SUM(link_id IS NOT NULL AND robo = 0), 0) AS humanos,
               COALESCE(SUM(robo = 1), 0) AS robos,
               COALESCE(SUM(link_id IS NULL), 0) AS inexistentes
        FROM links_curtos_acessos WHERE criado_em >= NOW() - INTERVAL %s DAY
        GROUP BY DATE(criado_em) ORDER BY dia DESC""", (dias,), fetch_all=True) or []
    ips = db.execute_query("""
        SELECT ip, COUNT(*) AS inexistentes, COUNT(DISTINCT codigo_tentado) AS codigos, MAX(criado_em) AS ultimo,
               MAX(user_agent) AS user_agent
        FROM links_curtos_acessos WHERE criado_em >= NOW() - INTERVAL %s DAY AND link_id IS NULL
        GROUP BY ip ORDER BY inexistentes DESC LIMIT 10""", (dias,), fetch_all=True) or []
    return por_dia, ips


@admin_bp.get('/sms')
@requer_admin
def sms_enviados():
    from database import db
    from sms import config
    from sms.servico import mascarar
    dias = request.args.get('dias', 7, type=int)
    dias = dias if dias in PERIODOS else 7
    produto_id = request.args.get('produto_id', type=int)
    produtos = db.execute_query("SELECT DISTINCT p.id, p.nome FROM sms_envios e JOIN produtos p ON p.id = e.produto_id "
                                "ORDER BY p.nome", fetch_all=True) or []
    resumo = _resumo(dias, produto_id)
    acessos_dia, ips = _acessos(dias)
    return render_template('admin/sms.html', dias=dias, periodos=PERIODOS, produto_id=produto_id, produtos=produtos,
                           resumo=resumo, custo=float(resumo.get('partes') or 0) * config.CUSTO_UNITARIO,
                           custo_unitario=config.CUSTO_UNITARIO, comparacao=_comparacao_musica(dias, produto_id),
                           envios=_envios(dias, produto_id), acessos_dia=acessos_dia, ips=ips, mascarar=mascarar)
