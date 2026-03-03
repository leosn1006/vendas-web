import logging
import json
from datetime import datetime
from database import (
    listar_acoes_fluxo, salvar_mensagem_pedido,
    atualizar_pedido_com_comprovante, atualizar_pedido_com_pagamento,
    get_produto_by_id,
)
from whatsapp_upload import receber_comprovante
from agente_valida_comprovante import validar_comprovante_com_ia
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar

logger = logging.getLogger(__name__)

_TAG = "FLUXO-COMPROVANTE-DIN"


def _to_float(valor, default=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return default


def _resolver_data_pagamento(data_pagamento_raw, data_contato_site):
    """
    Garante que data_pagamento seja posterior a data_contato_site (exigência do Google Ads).
    Fallback para datetime.now() se a data extraída for inválida ou anterior ao contato.
    """
    agora = datetime.now()

    if not data_pagamento_raw:
        return agora

    try:
        if isinstance(data_pagamento_raw, datetime):
            dp = data_pagamento_raw
        else:
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    dp = datetime.strptime(str(data_pagamento_raw).strip(), fmt)
                    break
                except ValueError:
                    continue
            else:
                return agora
    except Exception:
        return agora

    try:
        if isinstance(data_contato_site, datetime):
            dc = data_contato_site
        elif data_contato_site:
            dc = datetime.fromisoformat(str(data_contato_site))
        else:
            return dp  # sem referência, usa o que a IA extraiu
    except Exception:
        return dp

    if dp > dc:
        return dp

    logger.info(f"[{_TAG}] ⚠️ data_pagamento ({dp}) <= data_contato_site ({dc}) — usando datetime.now()")
    return agora


def executar(pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[{_TAG}] 🎬 Iniciando fluxo dinâmico de comprovante para pedido #{pedido.get('id')}")

        produto_id = pedido['produto_id']
        pedido_id  = pedido['id']
        dados_msg  = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]
        message_id = dados_msg['id']
        tipo       = dados_msg['type']  # 'image' ou 'document'

        # ── Download do comprovante ────────────────────────────────────────
        if tipo == 'image':
            url      = dados_msg['image']['url']
            mime     = dados_msg['image']['mime_type']
            filename = 'imagem_comprovante'
        elif tipo == 'document':
            url      = dados_msg['document']['url']
            mime     = dados_msg['document']['mime_type']
            filename = dados_msg['document'].get('filename') or 'documento_comprovante'
        else:
            raise ValueError(f"[{_TAG}] Tipo de mídia não suportado: {tipo}")

        path_comprovante = receber_comprovante(tipo, url, mime, filename, pedido_id)

        # Persiste caminho do comprovante e a mensagem recebida
        atualizar_pedido_com_comprovante(pedido_id, path_comprovante)
        salvar_mensagem_pedido(message_id, pedido_id, f"Comprovante recebido: {filename}", tipo_mensagem='recebida')

        # ── Validação com IA ──────────────────────────────────────────────
        logger.debug(f"[{_TAG}] 🤖 Validando comprovante com IA...")
        resultado_json = validar_comprovante_com_ia(path_comprovante)
        resultado      = json.loads(resultado_json)
        logger.debug(f"[{_TAG}] 🤖 Resultado: {resultado}")

        valor_pago            = _to_float(resultado.get('valor'), 0.0)
        destinatario_extraido = str(resultado.get('destinatario') or '').strip().lower()

        produto      = get_produto_by_id(produto_id)
        pix_esperado = str(produto.get('pix_destinatario_esperado') or '').strip().lower()
        valor_minimo = _to_float(produto.get('valor_minimo_pagamento'), 0.0)

        tokens_esperados   = pix_esperado.split()
        comprovante_valido = bool(tokens_esperados) and all(
            token in destinatario_extraido for token in tokens_esperados
        ) # and (valor_pago >= valor_minimo)
        logger.debug(f"[{_TAG}] 🤖 Válido: {comprovante_valido} "
                     f"(valor={valor_pago:.2f} mín={valor_minimo:.2f}, dest='{destinatario_extraido}')")

        # ── Persistência de pagamento (sempre) ────────────────────────────
        preco_produto = _to_float(produto.get('preco'), 0.0)
        if not comprovante_valido and valor_pago == 0.0:
            valor_pago = preco_produto
            logger.info(f"[{_TAG}] ⚠️ Valor não extraído — usando preço do produto R$ {valor_pago:.2f}")

        atualizar_pedido_com_pagamento(
            pedido_id,
            valor_pago=valor_pago,
            nome_banco=resultado.get('nome_banco'),
            nome_pagador=resultado.get('nome_pagador'),
            data_pagamento=_resolver_data_pagamento(
                resultado.get('data_pagamento'),
                pedido.get('data_contato_site'),
            ),
        )

        # ── Notificações ao admin ─────────────────────────────────────────
        from whatsapp import notificar_admin_pedido
        if comprovante_valido:
            if preco_produto > 0 and valor_pago > preco_produto * 3:
                notificar_admin_pedido(pedido, (
                    f"⚠️ *Pagamento alto* — Pedido #{pedido_id}\n\n"
                    f"Cliente: #{pedido_id} — {pedido.get('contact_name')} ({pedido.get('contact_phone')})\n"
                    f"Valor pago: *R$ {valor_pago:.2f}* | Preço produto: R$ {preco_produto:.2f}\n"
                    f"Pagador: {resultado.get('nome_pagador') or '—'}\n"
                    f"Banco: {resultado.get('nome_banco') or '—'}"
                ))
                logger.info(f"[{_TAG}] 📲 Admin notificado — pagamento alto (R$ {valor_pago:.2f})")
        else:
            razoes = []
            if not (bool(tokens_esperados) and all(t in destinatario_extraido for t in tokens_esperados)):
                razoes.append(
                    f"Destinatário esperado: *{pix_esperado or '—'}*\n"
                    f"Destinatário extraído: *{destinatario_extraido or '—'}*"
                )
            if resultado.get('valor') in (None, '', 0, '0'):
                razoes.append("Valor não identificado no comprovante")
            notificar_admin_pedido(pedido, (
                f"⚠️ *Comprovante não validado* — Pedido #{pedido_id}\n\n"
                f"Cliente: #{pedido_id} — {pedido.get('contact_name')} ({pedido.get('contact_phone')})\n"
                f"Valor pago (usado): *R$ {valor_pago:.2f}*\n\n"
                + ("\n".join(razoes) if razoes else "Motivo não identificado")
            ))
            logger.info(f"[{_TAG}] 📲 Admin notificado — comprovante não validado")

        # ── Executa ações dinâmicas (sempre fluxo feliz para o cliente) ───
        todas_acoes = listar_acoes_fluxo(produto_id, 'comprovante')
        acoes       = filtrar_e_ordenar(todas_acoes, ('sempre', 'pagamento_valido'))

        if not acoes:
            raise ValueError(
                f"[{_TAG}] ❌ Nenhuma ação configurada para o fluxo 'comprovante' "
                f"do produto {produto_id}. Configure no admin em Fluxos > Comprovante."
            )

        status_validacao = 'valido' if comprovante_valido else 'nao_validado'
        logger.debug(f"[{_TAG}] 📋 {len(acoes)} ação(ões) na sequência ({status_validacao}).")

        for acao in acoes:
            logger.debug(f"[{_TAG}] ▶ #{acao['ordem']} [{acao['acao']}] ({acao['condicao']})")
            executar_acao(acao, pedido, message_id, pedido_id, tag=_TAG)

        logger.info(f"[{_TAG}] ✅ Fluxo concluído para pedido #{pedido_id} — {status_validacao}.")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[{_TAG}] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc
