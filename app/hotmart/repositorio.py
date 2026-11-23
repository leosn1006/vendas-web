"""SQL da Hotmart: avisos recebidos, a compra (uma linha por transação), as ofertas e o que muda no pedido."""
import json
from decimal import Decimal

ESTADO_AGUARDANDO = 1010
ESTADO_CANCELADO = 1011


def _db():
    from database import db
    return db


# ── avisos ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def registrar_evento(evento_id: str, transacao, evento, payload: dict) -> bool:
    """Grava o aviso como 'processando'. True = é para processar: aviso novo, um que deu erro (a Hotmart reenviou
    depois de um 500) ou um que ficou 'processando' por mais de 2 min (o processo caiu no meio). Um reenvio que chega
    enquanto o primeiro ainda roda volta False — os dois nunca rodam juntos (o UPDATE é atômico)."""
    texto = json.dumps(payload, ensure_ascii=False, default=str)
    inseriu = _db().execute_query(
        """INSERT IGNORE INTO pagamento_hotmart_eventos (evento_id, transacao, evento, payload, resultado)
           VALUES (%s, %s, %s, %s, 'processando')""",
        (evento_id, transacao, evento, texto), return_rowcount=True)
    if inseriu:
        return True
    retomou = _db().execute_query(
        """UPDATE pagamento_hotmart_eventos SET resultado = 'processando', recebido_em = NOW()
           WHERE evento_id = %s
             AND (resultado = 'erro' OR resultado IS NULL
                  OR (resultado = 'processando' AND recebido_em < NOW() - INTERVAL 2 MINUTE))""",
        (evento_id,), return_rowcount=True)
    return bool(retomou)


def marcar_resultado_evento(evento_id: str, resultado: str, detalhe: str = '') -> None:
    _db().execute_query(
        "UPDATE pagamento_hotmart_eventos SET resultado = %s, detalhe = %s WHERE evento_id = %s",
        (resultado, (detalhe or '')[:255], evento_id))


# ── compra ─────────────────────────────────────────────────────────────────────────────────────────────────────────

_CAMPOS = ('transacao', 'pedido_id', 'produto_id_hotmart', 'oferta', 'status', 'ultimo_evento', 'tipo_pagamento',
           'pais', 'email_comprador', 'valor', 'moeda', 'valor_cheio', 'taxa_hotmart', 'moeda_taxa', 'liquido',
           'moeda_liquido', 'taxa_brl', 'fonte_taxa', 'valor_brl', 'liquido_brl', 'order_bump',
           'transacao_principal', 'nota_fiscal_por', 'modelo_fiscal', 'aprovado_em', 'garantia_ate',
           'previsao_repasse')
# Na atualização, o que já foi gravado vale mais que um aviso sem o campo (ex.: o CANCELED não traz approved_date).
_MANTER_SE_NULO = set(_CAMPOS) - {'transacao', 'status', 'ultimo_evento', 'order_bump'}


def salvar_pagamento(dados: dict) -> None:
    colunas = ', '.join(_CAMPOS)
    marcadores = ', '.join(['%s'] * len(_CAMPOS))
    atualiza = ', '.join(
        f'{c} = COALESCE(VALUES({c}), {c})' if c in _MANTER_SE_NULO else f'{c} = VALUES({c})'
        for c in _CAMPOS if c != 'transacao')
    _db().execute_query(
        f"INSERT INTO pagamento_hotmart ({colunas}) VALUES ({marcadores}) ON DUPLICATE KEY UPDATE {atualiza}",
        tuple(dados.get(c) for c in _CAMPOS))


def marcar_liberado(transacao: str) -> None:
    _db().execute_query(
        "UPDATE pagamento_hotmart SET liberado_em = COALESCE(liberado_em, NOW()) WHERE transacao = %s", (transacao,))


def ultima_taxa(moeda: str) -> Decimal | None:
    linha = _db().execute_query(
        """SELECT taxa_brl FROM pagamento_hotmart
           WHERE moeda = %s AND taxa_brl IS NOT NULL AND fonte_taxa <> 'pendente'
           ORDER BY atualizado_em DESC LIMIT 1""", (moeda,), fetch_one=True)
    return linha['taxa_brl'] if linha else None


def oferta(codigo: str) -> dict | None:
    if not codigo:
        return None
    return _db().execute_query(
        "SELECT codigo, produto_id, plano_id, ativo FROM hotmart_ofertas WHERE codigo = %s", (codigo,), fetch_one=True)


# ── pedido ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def pedido_por_guid(guid: str) -> dict | None:
    import database
    return database.get_pedido_by_guid(guid)


def confirmar_pedido(pedido_id: int, valor, nome: str, valor_liquido, data_repasse) -> bool:
    """O mesmo 1000 do PIX e do cartão (compare-and-swap: só o primeiro aviso confirma)."""
    import database
    return database.confirmar_pagamento_web(
        pedido_id=pedido_id, valor=float(valor or 0), nome_pagador=nome or '',
        valor_liquido=float(valor_liquido) if valor_liquido is not None else None,
        data_repasse=data_repasse.isoformat() if data_repasse else None,
        metodo_pagamento='hotmart')


# Estados web em que um pedido da Hotmart pode estar antes de pagar (chegou na landing/checkout, criado, aguardando,
# cancelado). Nunca: pago (0/1000), WhatsApp (3, 4...), contribuição (1008/1009), cartão/PIX do nosso checkout.
ESTADOS_ANTES_DO_PAGAMENTO = (1001, 1003, 1004, ESTADO_AGUARDANDO, ESTADO_CANCELADO)


def mudar_estado_se_nao_pago(pedido_id: int, estado: int) -> bool:
    """Aguardando (1010) ou cancelado (1011), só num pedido web da Hotmart ainda não pago."""
    estados = ', '.join(str(e) for e in ESTADOS_ANTES_DO_PAGAMENTO)
    linhas = _db().execute_query(
        f"""UPDATE pedidos SET estado_id = %s, metodo_pagamento = 'hotmart', data_ultima_atualizacao = CURRENT_TIMESTAMP
            WHERE id = %s AND fluxo_inicial = 'web' AND estado_id IN ({estados})""",
        (estado, pedido_id), return_rowcount=True)
    return bool(linhas)


def fonte_taxa_gravada(transacao: str) -> str | None:
    linha = _db().execute_query(
        "SELECT fonte_taxa FROM pagamento_hotmart WHERE transacao = %s", (transacao,), fetch_one=True)
    return linha['fonte_taxa'] if linha else None


def corrigir_valor_pendente(pedido_id: int, valor_brl, liquido_brl) -> bool:
    """Pedido pago sem cotação (fonte 'pendente'): o aviso seguinte que tiver cotação grava os reais de verdade."""
    if valor_brl is None:
        return False
    linhas = _db().execute_query(
        """UPDATE pedidos SET valor_pago = %s, valor_liquido_pagamento = COALESCE(%s, valor_liquido_pagamento),
                  data_ultima_atualizacao = CURRENT_TIMESTAMP
           WHERE id = %s AND estado_id = 1000 AND metodo_pagamento = 'hotmart'""",
        (float(valor_brl), float(liquido_brl) if liquido_brl is not None else None, pedido_id), return_rowcount=True)
    return bool(linhas)
