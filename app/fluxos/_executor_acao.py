"""
Executor genérico de ações de fluxo dinâmico.

Cada ação está representada por um dict com os campos da tabela acoes_fluxo_produto:
  tipo  (acao), url, mensagem, caption, nome_arquivo, delay_inicial, delay_final

O delay é aplicado ANTES da ação (via sleep ou countdown Celery).
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
    ErroTransienteWhatsApp,
)
from database import salvar_mensagem_pedido, selecionar_e_avancar_variante

logger = logging.getLogger(__name__)


def _executar_com_retry(fn, tag: str, max_tentativas: int = 2, delay_s: float = 8.0):
    for tentativa in range(max_tentativas):
        try:
            return fn()
        except ErroTransienteWhatsApp as e:
            if tentativa < max_tentativas - 1:
                logger.warning(f"[{tag}] ⚠️ Erro transiente (tentativa {tentativa + 1}/{max_tentativas}), aguardando {delay_s:.0f}s: {e}")
                time.sleep(delay_s)
            else:
                raise


def calcular_delay(acao: dict) -> float:
    """Sorteia o delay da ação (0.0 se não configurado)."""
    delay_ini = float(acao.get('delay_inicial') or 0)
    delay_fim = float(acao.get('delay_final')   or 0)
    if delay_fim <= 0:
        return 0.0
    return random.uniform(delay_ini, delay_fim)


def executar_acao(acao: dict, pedido: dict, message_id_original: str, pedido_id: int, tag: str = "FLUXO-DIN", aplicar_delay: bool = True):
    """
    Executa uma única ação de fluxo.

    Args:
        acao: linha da tabela acoes_fluxo_produto
        pedido: dict do pedido atual
        message_id_original: ID da mensagem recebida (para marcar_lida / digitando)
        pedido_id: ID do pedido (para salvar_mensagem_pedido)
        tag: prefixo para os logs (ex: 'FLUXO-PEDIDO-DIN')
        aplicar_delay: False quando o delay já foi consumido como countdown Celery
    """
    grupo_variantes = acao.get('_variantes_grupo')
    if grupo_variantes and pedido.get('phone_number_id'):
        # Resolve a variante de verdade (atômico, com lock) só agora, no momento
        # exato do envio — ver selecionar_variantes() para o motivo de não fazer
        # isso antecipadamente na montagem da lista.
        escolhida_numero = selecionar_e_avancar_variante(
            pedido['phone_number_id'], acao['produto_id'], acao['fluxo'],
            acao['condicao'], acao['ordem'], grupo_variantes
        )
        acao = next(v for v in grupo_variantes if v['variante'] == escolhida_numero)

    tipo = acao['acao']

    if aplicar_delay:
        delay = calcular_delay(acao)
        if delay > 0:
            logger.debug(f"[{tag}] ⏳ Aguardando {delay:.1f}s antes de '{tipo}'...")
            time.sleep(delay)

    if tipo == 'marcar_lida':
        try:
            marcar_como_lida(message_id_original, pedido.get('phone_number_id'))
            logger.debug(f"[{tag}] 👁 Mensagem marcada como lida.")
        except Exception as exc_lida:
            logger.warning(f"[{tag}] ⚠️ Falha ao marcar como lida (não crítico): {exc_lida}")

    elif tipo == 'digitando':
        try:
            enviar_mensagem_digitando(message_id_original, pedido.get('phone_number_id'))
            logger.debug(f"[{tag}] ⌨️ Status 'digitando' enviado.")
        except Exception as exc_digitando:
            logger.warning(f"[{tag}] ⚠️ Falha ao enviar digitando (não crítico): {exc_digitando}")

    elif tipo == 'enviar_audio':
        _exige_campo(acao, 'url', tag)
        mid = _executar_com_retry(lambda: enviar_audio(pedido, url_audio=acao['url']), tag)
        salvar_mensagem_pedido(mid, pedido_id, "[áudio enviado]", tipo_mensagem='enviada')
        logger.debug(f"[{tag}] 🎵 Áudio enviado.")

    elif tipo == 'enviar_imagem':
        _exige_campo(acao, 'url', tag)
        mid = _executar_com_retry(lambda: enviar_imagem(pedido, acao['url']), tag)
        salvar_mensagem_pedido(mid, pedido_id, "[imagem enviada]", tipo_mensagem='enviada')
        logger.debug(f"[{tag}] 🖼 Imagem enviada.")

    elif tipo == 'enviar_arquivo':
        _exige_campo(acao, 'url', tag)
        mid = _executar_com_retry(lambda: enviar_documento(
            pedido,
            url_documento=acao['url'],
            caption=acao.get('caption') or '',
            filename=acao.get('nome_arquivo') or 'arquivo',
        ), tag)
        salvar_mensagem_pedido(mid, pedido_id, f"[arquivo] {acao.get('nome_arquivo')}", tipo_mensagem='enviada')
        logger.debug(f"[{tag}] 📄 Arquivo enviado: {acao.get('nome_arquivo')}")

    elif tipo == 'enviar_mensagem':
        _exige_campo(acao, 'mensagem', tag)
        mid = _executar_com_retry(lambda: enviar_mensagem(pedido, acao['mensagem']), tag)
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
        mid = _executar_com_retry(lambda: enviar_produto_whatsapp(
            pedido,
            template_name=acao['mensagem'],
            language=acao.get('caption') or 'pt_BR',
            doc_url=acao['url'],
            doc_filename=acao['nome_arquivo'],
            body_params=body_params,
        ), tag)
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


def selecionar_variantes(acoes: list) -> list:
    """
    Colapsa grupos de variantes (mesmo produto_id+fluxo+condicao+ordem) em 1 linha
    "placeholder" por passo — usa a variante de menor número apenas para fins de
    montagem da lista (cálculo do delay de agendamento do próximo passo, e o
    bookkeeping de retomada via Celery, que depende de existir só 1 linha por
    'ordem'). A escolha REAL, atômica e com rodízio, só acontece dentro de
    executar_acao() no momento exato do envio (ver database.selecionar_e_avancar_variante).

    Importante: esta função NÃO toca no banco. Fluxos com múltiplos passos
    (introducao, pedido) reconstroem `acoes` do zero a cada retomada agendada via
    apply_async — se a escolha real (com avanço de cursor) acontecesse aqui, o
    cursor avançaria uma vez por retomada, não uma vez por envio real. Como o
    número de retomadas de um fluxo é fixo, isso "cancelava" o rodízio sempre que
    esse número era par (ex: 4 retomadas com 2 variantes = 0 avanços líquidos —
    todo mundo recebia sempre a mesma variante). Por isso o avanço de verdade
    precisa ficar amarrado à execução real da ação, que só acontece 1 vez por
    passo em todo o fluxo, não importa quantas vezes a task seja retomada.

    Chamada logo após filtrar_e_ordenar() e ANTES de qualquer lógica de retomada
    (ex: filtro `ordem >= X` do reagendamento Celery em tasks.py) — garante que o
    restante do código continue vendo no máximo 1 ação por passo.
    """
    grupos = {}
    for a in acoes:
        grupos.setdefault((a['ordem'], a['condicao']), []).append(a)

    resultado = []
    for variantes in grupos.values():
        if len(variantes) == 1:
            resultado.append(variantes[0])
            continue

        variantes = sorted(variantes, key=lambda v: v['variante'])
        placeholder = dict(variantes[0])
        placeholder['_variantes_grupo'] = variantes
        resultado.append(placeholder)

    return resultado


def _exige_campo(acao: dict, campo: str, tag: str):
    if not acao.get(campo):
        raise ValueError(
            f"[{tag}] ❌ Ação '{acao['acao']}' (id={acao['id']}) sem '{campo}' configurado. "
            f"Configure no admin em Fluxos."
        )
