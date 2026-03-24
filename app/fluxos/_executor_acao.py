"""
Executor genérico de ações de fluxo dinâmico.

Cada ação está representada por um dict com os campos da tabela acoes_fluxo_produto:
  tipo  (acao), url, mensagem, caption, nome_arquivo, delay_inicial, delay_final

O delay é aplicado ANTES de executar a ação.
O message_id_original é sempre o ID da mensagem recebida do cliente (usado em
marcar_lida e digitando — nunca o ID de mensagens enviadas).
"""
import logging
import random
import time
from whatsapp import (
    marcar_como_lida, enviar_mensagem_digitando,
    enviar_audio, enviar_imagem, enviar_mensagem, enviar_documento,
    enviar_produto_whatsapp,
)
from database import salvar_mensagem_pedido

logger = logging.getLogger(__name__)


def executar_acao(acao: dict, pedido: dict, message_id_original: str, pedido_id: int, tag: str = "FLUXO-DIN"):
    """
    Executa uma única ação de fluxo.

    Args:
        acao: linha da tabela acoes_fluxo_produto
        pedido: dict do pedido atual
        message_id_original: ID da mensagem recebida (para marcar_lida / digitando)
        pedido_id: ID do pedido (para salvar_mensagem_pedido)
        tag: prefixo para os logs (ex: 'FLUXO-PEDIDO-DIN')
    """
    tipo      = acao['acao']
    delay_ini = float(acao.get('delay_inicial') or 0)
    delay_fim = float(acao.get('delay_final')   or 0)

    # Aplica delay antes da ação
    if delay_fim > 0:
        delay = random.uniform(delay_ini, delay_fim)
        logger.debug(f"[{tag}] ⏳ Aguardando {delay:.1f}s antes de '{tipo}'...")
        time.sleep(delay)

    if tipo == 'marcar_lida':
        marcar_como_lida(message_id_original, pedido.get('phone_number_id'))
        logger.debug(f"[{tag}] 👁 Mensagem marcada como lida.")

    elif tipo == 'digitando':
        try:
            enviar_mensagem_digitando(message_id_original, pedido.get('phone_number_id'))
            logger.debug(f"[{tag}] ⌨️ Status 'digitando' enviado.")
        except Exception as exc_digitando:
            logger.warning(f"[{tag}] ⚠️ Falha ao enviar digitando (não crítico): {exc_digitando}")

    elif tipo == 'enviar_audio':
        _exige_campo(acao, 'url', tag)
        mid = enviar_audio(pedido, url_audio=acao['url'])
        salvar_mensagem_pedido(mid, pedido_id, "[áudio enviado]", tipo_mensagem='enviada')
        logger.debug(f"[{tag}] 🎵 Áudio enviado.")

    elif tipo == 'enviar_imagem':
        _exige_campo(acao, 'url', tag)
        mid = enviar_imagem(pedido, acao['url'])
        salvar_mensagem_pedido(mid, pedido_id, "[imagem enviada]", tipo_mensagem='enviada')
        logger.debug(f"[{tag}] 🖼 Imagem enviada.")

    elif tipo == 'enviar_arquivo':
        _exige_campo(acao, 'url', tag)
        mid = enviar_documento(
            pedido,
            url_documento=acao['url'],
            caption=acao.get('caption') or '',
            filename=acao.get('nome_arquivo') or 'arquivo',
        )
        salvar_mensagem_pedido(mid, pedido_id, f"[arquivo] {acao.get('nome_arquivo')}", tipo_mensagem='enviada')
        logger.debug(f"[{tag}] 📄 Arquivo enviado: {acao.get('nome_arquivo')}")

    elif tipo == 'enviar_mensagem':
        _exige_campo(acao, 'mensagem', tag)
        mid = enviar_mensagem(pedido, acao['mensagem'])
        salvar_mensagem_pedido(mid, pedido_id, acao['mensagem'], tipo_mensagem='enviada')
        logger.debug(f"[{tag}] 💬 Mensagem enviada: {str(acao['mensagem'])[:60]}...")

    elif tipo == 'enviar_produto_whatsapp':
        _exige_campo(acao, 'mensagem', tag)      # nome do template
        _exige_campo(acao, 'url', tag)           # URL do documento (header)
        _exige_campo(acao, 'nome_arquivo', tag)  # filename do documento
        # Monta parâmetros do body do template:
        # 1º: nome do cliente
        # 2º: param1 configurado (ex: nome do produto)
        # 3º: número do pedido formatado como #0001, #0123, #1234
        body_params = [
            pedido.get('contact_name', ''),
            acao.get('param1') or '',
            f"#{pedido_id:04d}",
        ]
        mid = enviar_produto_whatsapp(
            pedido,
            template_name=acao['mensagem'],
            language=acao.get('caption') or 'pt_BR',
            doc_url=acao['url'],
            doc_filename=acao['nome_arquivo'],
            body_params=body_params,
        )
        salvar_mensagem_pedido(mid, pedido_id, f"[template] {acao['mensagem']}", tipo_mensagem='enviada')
        logger.debug(f"[{tag}] 📦 Template '{acao['mensagem']}' enviado para {pedido.get('contact_phone')}")

    else:
        logger.warning(f"[{tag}] ⚠️ Tipo de ação desconhecido ignorado: '{tipo}'")


def filtrar_e_ordenar(todas_acoes: list, condicoes: tuple) -> list:
    """
    Filtra as ações pelas condições aceitas e ordena por ordem crescente.

    Args:
        todas_acoes: lista completa retornada por listar_acoes_fluxo()
        condicoes: tupla de condicoes aceitas, ex: ('sempre',) ou ('sempre', 'interesse_sim')

    Returns:
        lista ordenada por 'ordem'
    """
    return sorted(
        [a for a in todas_acoes if a['condicao'] in condicoes],
        key=lambda x: x['ordem']
    )


def _exige_campo(acao: dict, campo: str, tag: str):
    if not acao.get(campo):
        raise ValueError(
            f"[{tag}] ❌ Ação '{acao['acao']}' (id={acao['id']}) sem '{campo}' configurado. "
            f"Configure no admin em Fluxos."
        )
