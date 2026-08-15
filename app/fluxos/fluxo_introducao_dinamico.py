import logging
from database import listar_acoes_fluxo, salvar_mensagem_pedido, atualizar_estado_pedido
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar, selecionar_variantes

logger = logging.getLogger(__name__)

_TAG = "FLUXO-INTRODUCAO-DIN"


def executar(pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[{_TAG}] 🎬 Iniciando fluxo dinâmico de introdução para pedido #{pedido.get('id')}")

        produto_id   = pedido['produto_id']
        pedido_id    = pedido['id']
        dados_msg    = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]
        message_id   = dados_msg['id']
        mensagem_txt = dados_msg.get('text', {}).get('body', '') or ''

        # Grava mensagem recebida
        salvar_mensagem_pedido(message_id, pedido_id, mensagem_txt, tipo_mensagem='recebida')

        # Busca e filtra ações (introducao só tem 'sempre')
        todas_acoes = listar_acoes_fluxo(produto_id, 'introducao')
        acoes = filtrar_e_ordenar(todas_acoes, ('sempre',))
        acoes = selecionar_variantes(acoes)

        if not acoes:
            raise ValueError(
                f"[{_TAG}] ❌ Nenhuma ação configurada para o fluxo 'introducao' "
                f"do produto {produto_id}. Configure no admin em Fluxos > Introdução."
            )

        logger.debug(f"[{_TAG}] 📋 {len(acoes)} ação(ões) encontrada(s).")

        for acao in acoes:
            logger.debug(f"[{_TAG}] ▶ Executando ação #{acao['ordem']} [{acao['acao']}]")
            executar_acao(acao, pedido, message_id, pedido_id, tag=_TAG)

        # Avança estado do pedido para 'introducao_enviada' (2)
        atualizar_estado_pedido(pedido_id, 2)
        logger.info(f"[{_TAG}] ✅ Fluxo concluído. Estado do pedido #{pedido_id} → 2.")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[{_TAG}] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc
