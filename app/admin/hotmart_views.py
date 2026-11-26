"""Admin → Hotmart (só administradores): vendas de fora do Brasil, conciliação com a API de vendas, avisos para
conferir (com "Reprocessar") e o de-para oferta da Hotmart → plano nosso. Ver docs/HOTMART.md."""
import json
import logging

from flask import flash, redirect, render_template, request, url_for

from admin import admin_bp
from admin.auth import requer_admin

logger = logging.getLogger(__name__)

PERIODOS = (7, 30, 90, 365)
ABAS = ('vendas', 'conciliacao', 'conferir', 'ofertas')
STATUS_PAGO = ('APPROVED', 'COMPLETE')
STATUS_AGUARDANDO = ('PRINTED_BILLET', 'WAITING_PAYMENT')
STATUS_CANCELADO = ('CANCELLED', 'EXPIRED')
STATUS_DEVOLVIDO = ('REFUNDED', 'PARTIALLY_REFUNDED', 'CHARGEBACK', 'PROTESTED')
RESULTADOS_A_CONFERIR = ('sem_pedido', 'oferta_divergente', 'duplicado', 'erro')


def _lista_sql(valores):
    return ', '.join(f"'{v}'" for v in valores)      # constantes do módulo, nunca entrada do usuário


def _filtro(dias, produto_id):
    sql = ' AND COALESCE(ph.aprovado_em, ph.criado_em) >= NOW() - INTERVAL %s DAY'
    params = [dias]
    if produto_id:
        sql += ' AND p.produto_id = %s'
        params.append(produto_id)
    return sql, params


def _resumo(dias, produto_id):
    from database import db
    filtro, params = _filtro(dias, produto_id)
    pago = f"ph.status IN ({_lista_sql(STATUS_PAGO)})"
    resumo = db.execute_query(f"""
        SELECT COALESCE(SUM({pago}), 0) AS vendas,
               COALESCE(SUM(CASE WHEN {pago} THEN ph.valor_brl END), 0) AS total_brl,
               COALESCE(SUM(CASE WHEN {pago} THEN ph.liquido_brl END), 0) AS liquido_brl,
               AVG(CASE WHEN {pago} THEN ph.api_taxa_percentual END) AS taxa_media,
               COALESCE(SUM(ph.status IN ({_lista_sql(STATUS_AGUARDANDO)})), 0) AS aguardando,
               COALESCE(SUM(ph.status IN ({_lista_sql(STATUS_CANCELADO)})), 0) AS canceladas,
               COALESCE(SUM(ph.status IN ({_lista_sql(STATUS_DEVOLVIDO)})), 0) AS devolvidas,
               COALESCE(SUM(ph.divergencia IS NOT NULL), 0) AS divergentes
        FROM pagamento_hotmart ph LEFT JOIN pedidos p ON p.id = ph.pedido_id
        WHERE 1 = 1{filtro}""", tuple(params), fetch_one=True) or {}
    por_moeda = db.execute_query(f"""
        SELECT ph.moeda, SUM(COALESCE(ph.api_total, ph.valor_cheio, ph.valor)) AS total, COUNT(*) AS vendas
        FROM pagamento_hotmart ph LEFT JOIN pedidos p ON p.id = ph.pedido_id
        WHERE {pago}{filtro} GROUP BY ph.moeda ORDER BY total DESC""", tuple(params), fetch_all=True) or []
    return resumo, por_moeda


def _vendas(dias, produto_id, so_divergentes=False):
    from database import db
    filtro, params = _filtro(dias, produto_id)
    if so_divergentes:
        filtro += ' AND ph.divergencia IS NOT NULL'
    return db.execute_query(f"""
        SELECT ph.*, p.guid, p.estado_id AS pedido_estado, p.produto_id, pr.nome AS produto
        FROM pagamento_hotmart ph
        LEFT JOIN pedidos p ON p.id = ph.pedido_id
        LEFT JOIN produtos pr ON pr.id = p.produto_id
        WHERE 1 = 1{filtro}
        ORDER BY COALESCE(ph.aprovado_em, ph.criado_em) DESC LIMIT 300""", tuple(params), fetch_all=True) or []


def _execucoes():
    from database import db
    return db.execute_query("SELECT * FROM hotmart_conciliacoes ORDER BY id DESC LIMIT 10", fetch_all=True) or []


def _a_conferir():
    from database import db
    eventos = db.execute_query(f"""
        SELECT id, evento_id, transacao, evento, resultado, detalhe, recebido_em, payload
        FROM pagamento_hotmart_eventos WHERE resultado IN ({_lista_sql(RESULTADOS_A_CONFERIR)})
        ORDER BY id DESC LIMIT 100""", fetch_all=True) or []
    for e in eventos:
        try:
            payload = json.loads(e['payload']) if isinstance(e['payload'], (str, bytes)) else e['payload']
            e['payload_txt'] = json.dumps(payload, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            e['payload_txt'] = str(e['payload'])
    sem_cotacao = db.execute_query("""
        SELECT transacao, pedido_id, valor, moeda, criado_em FROM pagamento_hotmart
        WHERE fonte_taxa = 'pendente' ORDER BY id DESC LIMIT 50""", fetch_all=True) or []
    return eventos, sem_cotacao


def _ofertas():
    from database import db
    ofertas = db.execute_query("""
        SELECT o.*, pr.nome AS produto, pl.nome AS plano, pl.slug
        FROM hotmart_ofertas o
        LEFT JOIN produtos pr ON pr.id = o.produto_id
        LEFT JOIN produto_planos pl ON pl.id = o.plano_id
        ORDER BY pr.nome, pl.nome, o.codigo""", fetch_all=True) or []
    planos = db.execute_query("""
        SELECT pl.id, pl.nome, pl.slug, pr.id AS produto_id, pr.nome AS produto
        FROM produto_planos pl JOIN produtos pr ON pr.id = pl.produto_id
        WHERE (pr.ativo = 1 AND pl.ativo = 1) OR pl.id IN (SELECT plano_id FROM hotmart_ofertas)
        ORDER BY pr.nome, pl.nome""", fetch_all=True) or []
    # O plano atual de cada oferta está sempre na lista (mesmo inativo): salvar só a descrição não muda o plano.
    return ofertas, planos


def _contar_a_conferir() -> int:
    """Para o selo do menu: avisos a conferir + vendas com divergência."""
    from database import db
    linha = db.execute_query(f"""
        SELECT (SELECT COUNT(*) FROM pagamento_hotmart_eventos WHERE resultado IN ({_lista_sql(RESULTADOS_A_CONFERIR)}))
             + (SELECT COUNT(*) FROM pagamento_hotmart WHERE divergencia IS NOT NULL) AS n""", fetch_one=True)
    return int((linha or {}).get('n') or 0)


MOEDAS = ('MXN', 'USD', 'EUR', 'BRL', 'COP', 'CLP', 'ARS', 'PEN', 'GBP', 'INR', 'NGN')
_PRECO_MAXIMO = 1_000_000


def _preco(texto):
    """'149', '149,00', '1.149' ou '1.149,90' (milhar com ponto) → Decimal; vazio, inválido, NaN/infinito, ≤ 0 ou
    acima do teto → None."""
    import re
    from decimal import Decimal, InvalidOperation
    texto = (texto or '').strip().replace(' ', '')
    if not texto or not re.fullmatch(r'[0-9.,]+', texto):
        return None
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', texto):     # 1.149 = mil cento e quarenta e nove
        texto = texto.replace('.', '')
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        return None
    if not valor.is_finite() or valor <= 0 or valor > _PRECO_MAXIMO:
        return None
    return valor.quantize(Decimal('0.01'))


def _post_confiavel() -> bool:
    """O projeto não tem token CSRF: o POST tem de vir do próprio site (mesmo padrão dos apps das clientes)."""
    from apps._nucleo.auth import origem_confiavel
    if origem_confiavel():
        return True
    flash('Ação recusada: recarregue a página e tente de novo.', 'danger')
    return False


@admin_bp.get('/hotmart')
@requer_admin
def hotmart():
    from database import db
    from hotmart import api
    aba = request.args.get('aba', 'vendas')
    aba = aba if aba in ABAS else 'vendas'
    dias = request.args.get('dias', 30, type=int)
    dias = dias if dias in PERIODOS else 30
    produto_id = request.args.get('produto_id', type=int)
    produtos = db.execute_query("""
        SELECT DISTINCT pr.id, pr.nome FROM pagamento_hotmart ph
        JOIN pedidos p ON p.id = ph.pedido_id JOIN produtos pr ON pr.id = p.produto_id ORDER BY pr.nome""",
                                fetch_all=True) or []
    contexto = dict(aba=aba, dias=dias, periodos=PERIODOS, produto_id=produto_id, produtos=produtos,
                    api_configurada=api.configurada(), a_conferir=_contar_a_conferir())
    if aba == 'vendas':
        contexto['resumo'], contexto['por_moeda'] = _resumo(dias, produto_id)
        contexto['vendas'] = _vendas(dias, produto_id)
    elif aba == 'conciliacao':
        contexto['execucoes'] = _execucoes()
        contexto['vendas'] = _vendas(dias, produto_id, so_divergentes=True)
    elif aba == 'conferir':
        contexto['eventos'], contexto['sem_cotacao'] = _a_conferir()
    else:
        contexto['ofertas'], contexto['planos'] = _ofertas()
    return render_template('admin/hotmart.html', **contexto)


@admin_bp.post('/hotmart/conciliar')
@requer_admin
def hotmart_conciliar():
    from hotmart import api
    if not api.configurada():
        flash('A API da Hotmart não está configurada (HOTMART_CLIENT_ID, _SECRET e _TOKEN no .env do app e do '
              'worker-baixa): a conciliação não roda.', 'danger')
    elif _post_confiavel():
        # No worker, não na página: são dezenas de chamadas à API (passaria do tempo limite do Gunicorn).
        try:
            import celery_app  # noqa: F401 — configura o broker
            from hotmart import tarefas
            tarefas.conciliar.delay('botao')
            flash('Conciliação iniciada. Leva cerca de 1 minuto: atualize a página para ver o resultado abaixo.',
                  'success')
        except Exception as e:
            logger.error(f'[HOTMART] ❌ Não foi possível agendar a conciliação: {e}')
            flash(f'Não foi possível iniciar a conciliação: {e}', 'danger')
    return redirect(url_for('admin.hotmart', aba='conciliacao'))


@admin_bp.post('/hotmart/eventos/<int:evento_db_id>/reprocessar')
@requer_admin
def hotmart_reprocessar(evento_db_id):
    if _post_confiavel():
        from hotmart import servico
        try:
            resultado = servico.reprocessar(evento_db_id)
            flash(f'Aviso reprocessado: {resultado}.', 'success' if resultado == 'ok' else 'warning')
            logger.info(f'[HOTMART] Aviso {evento_db_id} reprocessado pelo admin: {resultado}')
        except Exception as e:
            flash(f'Não foi possível reprocessar: {e}', 'danger')
    return redirect(url_for('admin.hotmart', aba='conferir'))


@admin_bp.post('/hotmart/eventos/<int:evento_db_id>/resolvido')
@requer_admin
def hotmart_resolvido(evento_db_id):
    """Tira o aviso de "Para conferir" sem reaplicar (ex.: pagamento duplicado já reembolsado na Hotmart)."""
    if _post_confiavel():
        from hotmart import repositorio
        if repositorio.marcar_resolvido(evento_db_id):
            flash('Aviso marcado como resolvido.', 'success')
            logger.info(f'[HOTMART] Aviso {evento_db_id} marcado como resolvido pelo admin')
        else:
            flash('Este aviso não está mais para conferir.', 'warning')
    return redirect(url_for('admin.hotmart', aba='conferir'))


@admin_bp.post('/hotmart/ofertas')
@requer_admin
def hotmart_salvar_oferta():
    if _post_confiavel():
        from database import db
        codigo = (request.form.get('codigo') or '').strip()
        plano_id = request.form.get('plano_id', type=int)
        plano = db.execute_query("SELECT id, produto_id FROM produto_planos WHERE id = %s", (plano_id,),
                                 fetch_one=True) if plano_id else None
        uso = request.form.get('uso') or None
        uso = uso if uso in ('botao', 'popup') else None
        produto_hotmart = request.form.get('produto_hotmart', type=int)
        preco = _preco(request.form.get('preco'))
        moeda = (request.form.get('moeda') or '').strip().upper() or None
        ativo = 1 if request.form.get('ativo', '1') == '1' else 0
        if not codigo or len(codigo) > 40 or not plano:
            flash('Informe o código da oferta (o "off=" do link da Hotmart) e o plano.', 'danger')
        elif (request.form.get('preco') or '').strip() and not preco:
            flash('Preço inválido: use, por exemplo, 149 ou 149,90.', 'danger')
        elif moeda and moeda not in MOEDAS:
            flash(f'Moeda desconhecida: use uma de {", ".join(MOEDAS)}.', 'danger')
        elif uso and not (produto_hotmart and preco and moeda):
            flash('Oferta usada no botão ou no popup precisa do ID do produto na Hotmart, do preço e da moeda.',
                  'danger')
        else:
            # Um botão por plano e um popup por produto: a oferta ATIVA que entra no lugar tira a anterior (uma
            # desativada não, senão o plano sumiria da prévia).
            if uso == 'botao' and ativo:
                db.execute_query("UPDATE hotmart_ofertas SET uso = NULL WHERE plano_id = %s AND uso = 'botao' "
                                 "AND codigo <> %s", (plano['id'], codigo))
            elif uso == 'popup' and ativo:
                db.execute_query("UPDATE hotmart_ofertas SET uso = NULL WHERE produto_id = %s AND uso = 'popup' "
                                 "AND codigo <> %s", (plano['produto_id'], codigo))
            db.execute_query("""
                INSERT INTO hotmart_ofertas (codigo, produto_id, plano_id, descricao, ativo, produto_hotmart, preco,
                                             moeda, uso)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE produto_id = VALUES(produto_id), plano_id = VALUES(plano_id),
                                        descricao = VALUES(descricao), ativo = VALUES(ativo),
                                        produto_hotmart = VALUES(produto_hotmart), preco = VALUES(preco),
                                        moeda = VALUES(moeda), uso = VALUES(uso)""",
                             (codigo, plano['produto_id'], plano['id'], (request.form.get('descricao') or '')[:120],
                              ativo, produto_hotmart, preco, moeda, uso))
            flash(f'Oferta {codigo} salva.', 'success')
    return redirect(url_for('admin.hotmart', aba='ofertas'))
