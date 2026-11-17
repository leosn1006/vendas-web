import logging
import json
from datetime import datetime, timedelta
from database import (
    listar_acoes_fluxo, salvar_mensagem_pedido,
    atualizar_pedido_com_comprovante, atualizar_pedido_com_pagamento,
    atualizar_estado_pedido, get_produto_by_id, get_pedido, tentar_travar_fluxo,
)
from whatsapp_upload import receber_comprovante
from whatsapp import criar_notificacao_admin
from agente_valida_comprovante import validar_comprovante_com_ia
from fluxos._executor_acao import executar_acao, filtrar_e_ordenar, selecionar_variantes

logger = logging.getLogger(__name__)

_TAG = "FLUXO-COMPROVANTE-DIN"


from estados_pedido import (ESTADO_COMPROVANTE_EM_ANALISE, pode_informar_pagamento, pedido_esta_pago,
                            valor_pago as _valor_pago_pedido)


def _estado_ao_sair_da_trava(estado_anterior, pago: bool) -> int:
    """Estado para onde o pedido volta ao sair do 13. Regra única para todas as saídas (comprovante repetido,
    mídia não suportada, erro, "já paguei"): estado anterior conhecido → ele; desconhecido (None/13) → 0 se pago,
    senão 3. Antes cada saída tinha um padrão (0 numa, 3 noutra) e mídia não suportada podia virar "pago" com 0."""
    if estado_anterior in (None, ESTADO_COMPROVANTE_EM_ANALISE):
        return 0 if pago else 3
    return estado_anterior


def _devolver_estado_anterior(pedido: dict):
    """O orquestrador trava o pedido no estado 13 ("Comprovante em análise") ANTES de enfileirar este fluxo.
    Quando o fluxo sai sem concluir (comprovante repetido de um pedido que já estava pago, mídia não suportada), o
    pedido precisa voltar ao estado em que estava: sem isso ele fica em 13 para sempre — pago, mas fora da contagem
    de estado 0 e da exportação de conversões ao Google Ads (que só pega estados 0 e 1000).

    `pedido` é o dict que o orquestrador leu ANTES de travar, então `estado_id` é o estado anterior."""
    estado = _estado_ao_sair_da_trava(pedido.get('estado_id'), pedido_esta_pago(pedido))
    atualizar_estado_pedido(pedido['id'], estado)
    logger.info(f"[{_TAG}] 🔓 Pedido #{pedido['id']} devolvido ao estado {estado} (fluxo encerrado sem novo pagamento)")


def _to_float(valor, default=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return default


# Relógio do servidor vs. horário do comprovante: aceita uma pequena adiantada sem tratar como "futuro".
_TOLERANCIA_RELOGIO = timedelta(minutes=10)


def _trocar_dia_e_mes(dt: datetime):
    """2026-11-05 -> 2026-05-11. None se não dá (dia > 12 não pode virar mês)."""
    if dt.day > 12:
        return None
    try:
        return dt.replace(month=dt.day, day=dt.month)
    except ValueError:
        return None


def _resolver_data_pagamento(data_pagamento_raw, data_contato_site, agora=None):
    """
    Devolve a data de pagamento a gravar, garantindo que ela seja posterior a data_contato_site (exigência do
    Google Ads) E que não esteja no futuro.

    A IA lê comprovantes brasileiros (dd/mm) e devolve AAAA-MM-DD; quando o dia é <= 12 ela às vezes inverte
    dia e mês (11/05 vira 2026-11-05). Antes só se conferia "posterior ao contato", então essa data futura
    passava (51 pedidos em produção, ex.: contato 11/05 às 02:03, "pago" em 05/11 às 02:10). Agora, data no
    futuro tenta a troca de dia e mês; se a trocada for plausível (depois do contato e não futura), usa ela;
    senão usa o momento atual (ex.: PIX agendado, ou dia > 12 que não é troca).

    Fallback para o momento atual também se a data extraída for inválida ou anterior ao contato.
    `agora` é opcional só para os testes.
    """
    agora = agora or datetime.now()

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

    dc = None
    try:
        if isinstance(data_contato_site, datetime):
            dc = data_contato_site
        elif data_contato_site:
            dc = datetime.fromisoformat(str(data_contato_site))
    except Exception:
        dc = None  # sem referência confiável: só o limite superior vale

    limite = agora + _TOLERANCIA_RELOGIO

    def plausivel(d):
        return d <= limite and (dc is None or d > dc)

    if plausivel(dp):
        return dp

    if dp > limite:
        trocada = _trocar_dia_e_mes(dp)
        if trocada and plausivel(trocada):
            logger.info(f"[{_TAG}] ⚠️ data_pagamento no futuro ({dp}) — dia e mês invertidos pela IA, usando {trocada}")
            return trocada
        logger.info(f"[{_TAG}] ⚠️ data_pagamento no futuro ({dp}) e sem troca plausível — usando datetime.now()")
        return agora

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
            _devolver_estado_anterior(pedido)
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
            _devolver_estado_anterior(pedido)
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

        confirmar_pagamento(
            pedido, message_id, valor_pago, resultado,
            data_pagamento=_resolver_data_pagamento(
                resultado.get('data_pagamento'),
                pedido.get('data_contato_site'),
            ),
            preco_produto=preco_produto,
            comprovante_valido=comprovante_valido,
        )
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[{_TAG}] ❌ Erro: {exc}")
        logger.info("=" * 120)
        raise exc


def confirmar_pagamento(pedido, message_id, valor_pago, resultado, data_pagamento,
                        preco_produto, comprovante_valido=True):
    """Grava o pagamento (leva o pedido ao estado 0), avisa o admin se o valor for alto e executa as ações do
    fluxo 'comprovante' do produto (agradecimento, bônus...). Usado pelo comprovante (imagem/documento) e pelo
    pagamento informado por texto ("já fiz o Pix")."""
    pedido_id  = pedido['id']
    produto_id = pedido['produto_id']

    atualizar_pedido_com_pagamento(
        pedido_id,
        valor_pago=valor_pago,
        nome_banco=resultado.get('nome_banco'),
        nome_pagador=resultado.get('nome_pagador'),
        data_pagamento=data_pagamento,
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

    logger.info(f"[{_TAG}] ✅ Pagamento confirmado para pedido #{pedido_id} — {status_validacao}.")


def destravar_apos_erro(pedido_id, estado_anterior):
    """Tira o pedido do 13 depois de um erro no fluxo de pagamento (imagem ou "já paguei"). Se o pagamento já foi
    gravado (erro depois, ex.: no envio do bônus), fica pago (0); senão volta ao estado em que estava antes da trava
    (3 ou 4, preservando o ponto do follow-up). Antes a task do comprovante sempre voltava para 3, inclusive pedido
    pago, que saía da contagem e do ROI.

    Se nem a leitura do pedido funcionar (banco fora), não arrisca: volta ao estado anterior (3 se desconhecido); o
    pior caso é um pedido pago fora do 0, que a conferência de pagos presos pega (skill analise-funil-whatsapp)."""
    try:
        pago = _valor_pago_pedido(get_pedido(pedido_id)) > 0
    except Exception as exc:
        logger.warning(f"[{_TAG}] ⚠️ pedido #{pedido_id} — falha ao reler após erro ({exc}); assumindo não pago")
        pago = False
    # pagamento gravado nesta execução (erro depois, no bônus) → 0; senão a regra comum de saída da trava
    novo_estado = 0 if pago else _estado_ao_sair_da_trava(estado_anterior, pago)
    atualizar_estado_pedido(pedido_id, novo_estado)
    logger.warning(f"[{_TAG}] 🔓 pedido #{pedido_id} destravado → {novo_estado} após erro")


# O valor informado por texto vai direto para valor_pago (Financeiro, ROI, pedido_itens) sem comprovante. Acima de
# N vezes o preço é mais provável erro de leitura ("fiz o pix de 1990" = horário) do que contribuição: usa o preço.
_MULTIPLO_MAXIMO_VALOR_INFORMADO = 5


def _valor_informado(valor, preco_produto, pedido_id) -> float:
    valor_pago = _to_float(valor, 0.0)
    if valor_pago <= 0.0:
        return preco_produto
    if preco_produto > 0 and valor_pago > preco_produto * _MULTIPLO_MAXIMO_VALOR_INFORMADO:
        logger.warning(f"[{_TAG}] ⚠️ pedido #{pedido_id} — valor informado R$ {valor_pago:.2f} acima de "
                       f"{_MULTIPLO_MAXIMO_VALOR_INFORMADO}x o preço; gravando o preço R$ {preco_produto:.2f}")
        return preco_produto
    return valor_pago


def executar_pagamento_informado(pedido, message_id, valor=None):
    """A cliente disse por texto que já pagou ("já fiz o Pix", "paguei 20") e não mandou imagem. Decisão de
    negócio (nov/2026): não pedir comprovante ao público 35+; vale como comprovante.

    O responder agenda esta função com atraso e SEM travar: se a imagem do comprovante chegar nesse meio-tempo,
    ela trava o pedido no 13 primeiro e tem prioridade (valor, banco e pagador lidos do arquivo). Aqui o pedido é
    relido; só segue se ainda estiver aguardando pagamento e conseguir a trava → 13."""
    pedido_id = pedido['id']
    logger.info(f"[{_TAG}] 💬 Pagamento informado por texto — pedido #{pedido_id} (valor citado: {valor})")

    # Trava a partir do estado atual. Se ele mudar entre a leitura e a trava (follow-up 3 → 4), relê e tenta de novo.
    for _ in range(2):
        atual = {**pedido, **(get_pedido(pedido_id) or {})}
        estado_anterior = atual.get('estado_id')
        if not pode_informar_pagamento(atual):
            logger.info(f"[{_TAG}] ⚠️ pedido #{pedido_id} — já pago ou fora de 'aguardando pagamento' "
                        f"(estado {estado_anterior}), pagamento informado ignorado")
            return
        if tentar_travar_fluxo(pedido_id, estado_atual=estado_anterior, estado_travado=ESTADO_COMPROVANTE_EM_ANALISE):
            break
    else:
        logger.warning(f"[{_TAG}] 🔒 pedido #{pedido_id} — não conseguiu travar, pagamento informado ignorado")
        return

    try:
        produto       = get_produto_by_id(atual['produto_id'])
        preco_produto = _to_float(produto.get('preco'), 0.0)
        valor_pago    = _valor_informado(valor, preco_produto, pedido_id)

        confirmar_pagamento(
            atual, message_id, valor_pago, {},
            data_pagamento=datetime.now(),
            preco_produto=preco_produto,
        )
    except Exception:
        destravar_apos_erro(pedido_id, estado_anterior)
        raise
