import logging
import time
import random
from database import listar_acoes_fluxo, salvar_mensagem_pedido, atualizar_estado_pedido
from whatsapp import marcar_como_lida, enviar_mensagem_digitando, enviar_audio, enviar_imagem, enviar_mensagem, enviar_documento

logger = logging.getLogger(__name__)


def _executar_acao(acao, pedido, message_id_original, pedido_id):
    """Executa uma única ação do fluxo conforme configurado na tabela acoes_fluxo_produto."""
    tipo = acao['acao']

    # Aplica delay antes da ação (quando configurado)
    delay_ini = float(acao['delay_inicial'] or 0)
    delay_fim = float(acao['delay_final'] or 0)
    if delay_fim > 0:
        delay = random.uniform(delay_ini, delay_fim)
        logger.debug(f"[FLUXO-INTRODUCAO-DIN] ⏳ Aguardando {delay:.1f}s antes de '{tipo}'...")
        time.sleep(delay)

    if tipo == 'marcar_lida':
        marcar_como_lida(message_id_original)
        logger.debug("[FLUXO-INTRODUCAO-DIN] 👁 Mensagem marcada como lida.")

    elif tipo == 'digitando':
        enviar_mensagem_digitando(message_id_original)
        logger.debug("[FLUXO-INTRODUCAO-DIN] ⌨️ Status 'digitando' enviado.")

    elif tipo == 'enviar_audio':
        if not acao.get('url'):
            raise ValueError(f"[FLUXO-INTRODUCAO-DIN] ❌ Ação '{tipo}' sem URL configurada (id={acao['id']})")
        mid = enviar_audio(pedido, url_audio=acao['url'])
        salvar_mensagem_pedido(mid, pedido_id, f"[áudio enviado]", tipo_mensagem='enviada')
        logger.debug(f"[FLUXO-INTRODUCAO-DIN] 🎵 Áudio enviado: {acao['url'][:60]}...")

    elif tipo == 'enviar_imagem':
        if not acao.get('url'):
            raise ValueError(f"[FLUXO-INTRODUCAO-DIN] ❌ Ação '{tipo}' sem URL configurada (id={acao['id']})")
        mid = enviar_imagem(pedido, acao['url'])
        salvar_mensagem_pedido(mid, pedido_id, f"[imagem enviada]", tipo_mensagem='enviada')
        logger.debug(f"[FLUXO-INTRODUCAO-DIN] 🖼 Imagem enviada: {acao['url'][:60]}...")

    elif tipo == 'enviar_arquivo':
        if not acao.get('url'):
            raise ValueError(f"[FLUXO-INTRODUCAO-DIN] ❌ Ação '{tipo}' sem URL configurada (id={acao['id']})")
        mid = enviar_documento(
            pedido,
            url_documento=acao['url'],
            caption=acao.get('caption') or '',
            filename=acao.get('nome_arquivo') or 'arquivo',
        )
        salvar_mensagem_pedido(mid, pedido_id, f"[arquivo] {acao.get('nome_arquivo')}", tipo_mensagem='enviada')
        logger.debug(f"[FLUXO-INTRODUCAO-DIN] 📄 Arquivo enviado: {acao.get('nome_arquivo')}")

    elif tipo == 'enviar_mensagem':
        if not acao.get('mensagem'):
            raise ValueError(f"[FLUXO-INTRODUCAO-DIN] ❌ Ação '{tipo}' sem mensagem configurada (id={acao['id']})")
        mid = enviar_mensagem(pedido, acao['mensagem'])
        salvar_mensagem_pedido(mid, pedido_id, acao['mensagem'], tipo_mensagem='enviada')
        logger.debug(f"[FLUXO-INTRODUCAO-DIN] 💬 Mensagem enviada: {str(acao['mensagem'])[:60]}...")

    else:
        logger.warning(f"[FLUXO-INTRODUCAO-DIN] ⚠️ Tipo de ação desconhecido ignorado: '{tipo}'")


def executar(pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[FLUXO-INTRODUCAO-DIN] 🎬 Iniciando fluxo dinâmico de introdução para pedido #{pedido.get('id')}")

        produto_id   = pedido['produto_id']
        pedido_id    = pedido['id']
        message_id   = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        mensagem_txt = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']

        # Grava mensagem recebida
        salvar_mensagem_pedido(message_id, pedido_id, mensagem_txt, tipo_mensagem='recebida')

        # Busca ações configuradas para este produto/fluxo — apenas condicao='sempre'
        todas_acoes = listar_acoes_fluxo(produto_id, 'introducao')
        acoes = [a for a in todas_acoes if a['condicao'] == 'sempre']

        if not acoes:
            raise ValueError(
                f"[FLUXO-INTRODUCAO-DIN] ❌ Nenhuma ação configurada para o fluxo 'introducao' "
                f"do produto {produto_id}. Configure-as no admin em Fluxos > Introdução."
            )

        logger.debug(f"[FLUXO-INTRODUCAO-DIN] 📋 {len(acoes)} ação(ões) encontrada(s).")

        # Executa cada ação em ordem
        for acao in acoes:
            logger.debug(f"[FLUXO-INTRODUCAO-DIN] ▶ Executando ação #{acao['ordem']} [{acao['acao']}]")
            _executar_acao(acao, pedido, message_id, pedido_id)

        # Avança estado do pedido para 'introducao_enviada' (2)
        atualizar_estado_pedido(pedido_id, 2)
        logger.info(f"[FLUXO-INTRODUCAO-DIN] ✅ Fluxo concluído. Estado do pedido #{pedido_id} atualizado para 2.")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[FLUXO-INTRODUCAO-DIN] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc
