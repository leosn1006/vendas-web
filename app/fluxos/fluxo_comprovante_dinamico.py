import logging
import json
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

        comprovante_valido = (pix_esperado in destinatario_extraido) # and (valor_pago >= valor_minimo)
        condicao_ativa     = 'pagamento_valido' if comprovante_valido else 'pagamento_invalido'

        logger.debug(f"[{_TAG}] 🤖 Válido: {comprovante_valido} → condicao='{condicao_ativa}' "
                     f"(valor={valor_pago:.2f} mín={valor_minimo:.2f}, dest='{destinatario_extraido}')")

        # ── Persistência de pagamento (só se válido) ───────────────────────
        if comprovante_valido:
            atualizar_pedido_com_pagamento(
                pedido_id,
                valor_pago=valor_pago,
                nome_banco=resultado.get('nome_banco'),
                nome_pagador=resultado.get('nome_pagador'),
                data_pagamento=resultado.get('data_pagamento'),
            )

        # ── Executa ações dinâmicas ───────────────────────────────────────
        todas_acoes = listar_acoes_fluxo(produto_id, 'comprovante')
        acoes       = filtrar_e_ordenar(todas_acoes, ('sempre', condicao_ativa))

        if not acoes:
            raise ValueError(
                f"[{_TAG}] ❌ Nenhuma ação configurada para o fluxo 'comprovante' "
                f"do produto {produto_id}. Configure no admin em Fluxos > Comprovante."
            )

        logger.debug(f"[{_TAG}] 📋 {len(acoes)} ação(ões) na sequência ({condicao_ativa}).")

        for acao in acoes:
            logger.debug(f"[{_TAG}] ▶ #{acao['ordem']} [{acao['acao']}] ({acao['condicao']})")
            executar_acao(acao, pedido, message_id, pedido_id, tag=_TAG)

        logger.info(f"[{_TAG}] ✅ Fluxo concluído para pedido #{pedido_id} — {condicao_ativa}.")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[{_TAG}] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc
