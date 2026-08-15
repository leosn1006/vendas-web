import logging
import json
from datetime import datetime
from database import (
    listar_acoes_fluxo, salvar_mensagem_pedido,
    atualizar_pedido_com_comprovante, atualizar_pedido_com_pagamento,
    get_produto_by_id,
)
from whatsapp_upload import receber_comprovante
from whatsapp import criar_notificacao_admin
from agente_valida_comprovante import validar_comprovante_com_ia
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar, selecionar_variantes

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
            logger.warning(f"[{_TAG}] ⚠️ pedido #{pedido_id} — tipo de mídia não suportado: {tipo}")
            return

        path_comprovante = receber_comprovante(tipo, url, mime, filename, pedido_id, phone_number_id=pedido.get('phone_number_id'))

        # Persiste caminho do comprovante e a mensagem recebida
        atualizar_pedido_com_comprovante(pedido_id, path_comprovante)
        salvar_mensagem_pedido(message_id, pedido_id, f"Comprovante recebido: {filename}", tipo_mensagem='recebida')

        produto       = get_produto_by_id(produto_id)
        preco_produto = _to_float(produto.get('preco'), 0.0)

        # ── Validação com IA ──────────────────────────────────────────────
        ja_pago = _to_float(pedido.get('valor_pago'), 0.0) > 0.0

        if path_comprovante is None:
            logger.warning(f"[{_TAG}] ⚠️ pedido #{pedido_id} — sem comprovante disponível, seguindo fluxo (R$ {preco_produto:.2f})")
            resultado          = {}
            comprovante_valido = True
            valor_pago         = preco_produto
        elif ja_pago:
            # Pedido já confirmado: comprovante salvo acima para auditoria, mas não
            # reexecutamos o fluxo para evitar reenviar arquivo e mensagens de confirmação.
            logger.info(f"[{_TAG}] ⚠️ pedido #{pedido_id} — já possui pagamento registrado, encerrando")
            return
        else:
            logger.debug(f"[{_TAG}] 🤖 Validando comprovante com IA...")
            resultado_json = validar_comprovante_com_ia(path_comprovante)
            try:
                resultado = json.loads(resultado_json)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"[{_TAG}] ⚠️ pedido #{pedido_id} — JSON inválido da IA, aceito automaticamente")
                resultado          = {}
                comprovante_valido = True
                valor_pago         = preco_produto
            else:
                logger.debug(f"[{_TAG}] 🤖 Resultado: {resultado}")
                if resultado.get('recusado'):
                    logger.warning(f"[{_TAG}] ⚠️ pedido #{pedido_id} — IA recusou processar imagem, aceito automaticamente (R$ {preco_produto:.2f})")
                    resultado          = {}
                    comprovante_valido = True
                    valor_pago         = preco_produto
                else:
                    valor_pago            = _to_float(resultado.get('valor'), 0.0)
                    destinatario_extraido = str(resultado.get('destinatario') or '').strip().lower()
                    comprovante_valido    = True  # validação de destinatário desabilitada por enquanto
                    if valor_pago == 0.0:
                        valor_pago = preco_produto
                        logger.info(f"[{_TAG}] ⚠️ Valor não extraído — usando preço do produto R$ {valor_pago:.2f}")
                    logger.debug(f"[{_TAG}] 🤖 Comprovante aceito (dest='{destinatario_extraido}', valor={valor_pago:.2f})")

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
        if preco_produto > 0 and valor_pago > preco_produto * 3:
            criar_notificacao_admin(
                pedido_id,
                produto_id,
                'pagamento_alto',
                f"Pagamento alto — Pedido #{pedido_id}\n"
                f"Cliente: {pedido.get('contact_name')} ({pedido.get('contact_phone')})\n"
                f"Valor pago: R$ {valor_pago:.2f} | Preço produto: R$ {preco_produto:.2f}\n"
                f"Pagador: {resultado.get('nome_pagador') or '—'}\n"
                f"Banco: {resultado.get('nome_banco') or '—'}",
            )
            logger.info(f"[{_TAG}] 📋 Notificação criada — pagamento alto (R$ {valor_pago:.2f})")

        # ── Executa ações dinâmicas ───────────────────────────────────────
        todas_acoes = listar_acoes_fluxo(produto_id, 'comprovante')
        condicoes   = ('sempre', 'pagamento_valido') if comprovante_valido else ('sempre', 'pagamento_invalido')
        acoes       = filtrar_e_ordenar(todas_acoes, condicoes)
        acoes       = selecionar_variantes(acoes)

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
