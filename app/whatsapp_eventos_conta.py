import hashlib
import logging
import os

import redis as redis_lib

logger = logging.getLogger(__name__)

_redis = redis_lib.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

# Campos de webhook de nível-número e nível-conta (WABA/Business Manager), distintos de
# 'messages'. A bifurcação por field acontece em app.py, ANTES do enfileiramento, para que
# esses eventos rodem na fila 'normal' (tasks.processar_evento_conta_whatsapp), separada da
# fila 'urgente' usada por tasks.processar_webhook para o fluxo de vendas.
_EVENTOS_TELEFONE = {'phone_number_quality_update', 'phone_number_name_update'}
_EVENTOS_CONTA = {'account_update', 'account_review_update', 'account_alerts', 'business_capability_update'}
EVENTOS_CONTA_OU_TELEFONE = _EVENTOS_TELEFONE | _EVENTOS_CONTA


def classificar_webhook(body):
    """Retorna o conjunto de 'field' presentes em TODOS os entry/changes do payload (a Meta
    pode entregar mais de um por POST) — usado por app.py pra decidir pra qual(is) fila(s)
    enfileirar, sem se limitar a entry[0].changes[0]."""
    fields = set()
    for entry in (body.get('entry') or []):
        for change in (entry.get('changes') or []):
            field = change.get('field')
            if field:
                fields.add(field)
    return fields


def _resumir_evento_telefone(field, value):
    """Monta uma mensagem legível a partir do payload do evento. Cai no dump bruto só se o
    campo não for um dos dois tipos conhecidos."""
    if field == 'phone_number_quality_update':
        evento = value.get('event', '?')
        limite = value.get('current_limit')
        msg = f"Qualidade do número mudou: {evento}"
        if limite:
            msg += f" (novo limite de mensagens: {limite})"
        return msg
    if field == 'phone_number_name_update':
        decisao = value.get('decision', '?')
        nome = value.get('requested_verified_name') or value.get('display_phone_number') or ''
        msg = f"Nome de exibição: {decisao}"
        if nome:
            msg += f" ({nome})"
        return msg
    return f"{field}: {value}"


def _dedup_key(entry, field, change):
    """Chave de deduplicação por evento individual — a Meta reentrega webhooks (at-least-once),
    e sem isso cada reentrega vira uma linha duplicada em notificacoes_telefone/conta_whatsapp."""
    bruto = f"{entry.get('id')}:{field}:{entry.get('time')}:{change.get('value')}"
    return "wha:evt:" + hashlib.sha256(bruto.encode()).hexdigest()


def processar_evento_conta(mensagem_whatsapp):
    """Persiste todo evento de nível-número (qualidade, nome) ou nível-conta (WABA/BM) presente
    no payload — varre todos os entry/changes, não só o primeiro, pra não perder eventos
    entregues em lote junto com outros tipos de change (ex: uma mensagem de cliente). Deduplica
    via Redis. Chamada por tasks.processar_evento_conta_whatsapp (fila normal) — nunca pelo
    fluxo de mensagens/whatsapp_orquestrador.recebe_webhook."""
    from database import (get_telefone_produto_by_phone_number_id, criar_notificacao_telefone,
                           criar_notificacao_conta_whatsapp)

    for entry in (mensagem_whatsapp.get('entry') or []):
        for change in (entry.get('changes') or []):
            field = change.get('field')
            if field not in EVENTOS_CONTA_OU_TELEFONE:
                continue  # não é nosso — pode ser 'messages' num payload em lote, ignora em silêncio

            dedup_key = _dedup_key(entry, field, change)
            try:
                if not _redis.set(dedup_key, 1, nx=True, ex=300):
                    logger.info(f"[EVENTOS-CONTA] ⏭ Evento '{field}' duplicado (reentrega da Meta) — ignorado")
                    continue
            except Exception as redis_err:
                logger.warning(f"[EVENTOS-CONTA] ⚠️ Redis indisponível para dedup, processando sem garantia: {redis_err}")

            value = change.get('value', {}) or {}

            if field in _EVENTOS_TELEFONE:
                api_phone_id = value.get('metadata', {}).get('phone_number_id') or value.get('phone_number_id')
                telefone = get_telefone_produto_by_phone_number_id(api_phone_id) if api_phone_id else None
                if not telefone:
                    logger.warning(f"[EVENTOS-CONTA] ⚠️ Evento '{field}' para phone_number_id={api_phone_id!r} sem telefone cadastrado")
                    continue
                mensagem = _resumir_evento_telefone(field, value)
                criar_notificacao_telefone(telefone['id'], telefone['produto_id'], field, mensagem, payload_raw=change)
                logger.info(f"[EVENTOS-CONTA] 🔔 '{field}' persistido para telefone #{telefone['id']} ({telefone.get('telefone')})")
                continue

            if field in _EVENTOS_CONTA:
                waba_id = entry.get('id')  # id da WABA é o entry.id nesses eventos
                business_id = value.get('business_id') or (value.get('business') or {}).get('id')
                criar_notificacao_conta_whatsapp(field, waba_id=waba_id, business_id=business_id, payload_raw=change)
                logger.info(f"[EVENTOS-CONTA] 🔔 '{field}' persistido (waba_id={waba_id})")
