# worker para tratar as mensagens da fila Redis
import logging
import os
import redis as redis_lib
from celery import shared_task
from whatsapp import notificar_admin_erro_sistema

logger = logging.getLogger(__name__)

_redis = redis_lib.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

#TODO rever max_retries e countdown, para não ficar tentando para sempre em caso de erro persistente, e para não demorar muito para tentar novamente em caso de erro temporário
@shared_task(name="tasks.processar_webhook", bind=True, max_retries=0)
def processar_webhook(self, body):
    # Deduplicação: WhatsApp pode entregar o mesmo webhook mais de uma vez (at-least-once delivery)
    redis_key = None
    try:
        msg_id = body['entry'][0]['changes'][0]['value']['messages'][0]['id']
        redis_key = f"wha:msg:{msg_id}"
        if not _redis.set(redis_key, 1, nx=True, ex=300):
            logger.warning(f"[TASK-WEBHOOK] ⚠️ Webhook duplicado ignorado: {msg_id}")
            return
    except (KeyError, IndexError):
        pass  # sem message_id (status updates, notificações) → processa normalmente
    except Exception as redis_err:
        # Redis fora do ar não deve matar a task; processa sem garantia de dedup
        logger.warning(f"[TASK-WEBHOOK] ⚠️ Redis indisponível para dedup, processando sem garantia: {redis_err}")
        redis_key = None

    logger.info("=" * 120)
    logger.info(f"[TASK-WEBHOOK] 📦 Dados recebidos para processamento da mensagem webhook:  {body}")
    from whatsapp_orquestrador import recebe_webhook
    try:
        # ============================================================================================
        #processa a mensagem do webhook, que pode ser uma mensagem nova do cliente, ou uma resposta do cliente a uma mensagem enviada, ou outras interações. O processamento envolve extrair os dados relevantes da mensagem, identificar o pedido associado (se houver), determinar o fluxo de atendimento adequado (introdução, envio de produto, etc) e enfileirar a tarefa correspondente para cada fluxo.
        recebe_webhook(body)
        logger.info("[TASK-WEBHOOK] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except Exception as exc:
        # Libera a chave para permitir retry em caso de crash (acks_late=True)
        if redis_key:
            try:
                _redis.delete(redis_key)
            except Exception:
                pass
        _contato_val = body.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('contacts', [{}])[0]
        telefone = _contato_val.get('wa_id') or _contato_val.get('user_id', '?')
        logger.exception(f"[TASK-WEBHOOK] ❌ tel: {telefone} | body: {str(body)[:500]} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-WEBHOOK | tel: {telefone} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)



@shared_task(name="tasks.enviar_introducao_dinamico", bind=True, max_retries=0)
def fluxo_enviar_introducao_dinamico(self, pedido, mensagem_whatsapp=None, ordem=1, message_id=None):
    from database import listar_acoes_fluxo, salvar_mensagem_pedido, atualizar_estado_pedido
    from fluxos._executor_acao import executar_acao, filtrar_e_ordenar, calcular_delay, selecionar_variantes

    _TAG = "TASK-INTRODUCAO-DIN"
    produto_id = pedido['produto_id']
    pedido_id  = pedido['id']

    try:
        if ordem == 1:
            logger.info("=" * 120)
            logger.info(f"[{_TAG}] 📦 pedido #{pedido_id} | iniciando fluxo")
            dados_msg    = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]
            message_id   = dados_msg['id']
            mensagem_txt = dados_msg.get('text', {}).get('body', '') or ''
            salvar_mensagem_pedido(message_id, pedido_id, mensagem_txt, tipo_mensagem='recebida')
        else:
            logger.debug(f"[{_TAG}] ▶ pedido #{pedido_id} | retomando na ordem={ordem}")

        todas_acoes = listar_acoes_fluxo(produto_id, 'introducao')
        acoes = filtrar_e_ordenar(todas_acoes, ('sempre',))
        acoes = selecionar_variantes(acoes)

        if not acoes:
            raise ValueError(f"[{_TAG}] Nenhuma ação configurada para 'introducao' do produto {produto_id}")

        restantes = [a for a in acoes if a['ordem'] >= ordem]

        i = 0
        while i < len(restantes):
            acao = restantes[i]
            logger.debug(f"[{_TAG}] ▶ Executando #{acao['ordem']} [{acao['acao']}]")
            executar_acao(acao, pedido, message_id, pedido_id, tag=_TAG, aplicar_delay=False)
            i += 1

            if i < len(restantes):
                delay = calcular_delay(restantes[i])
                if delay > 0:
                    logger.debug(f"[{_TAG}] ⏳ Agendando #{restantes[i]['ordem']} em {delay:.1f}s")
                    fluxo_enviar_introducao_dinamico.apply_async(
                        kwargs={
                            'pedido':      pedido,
                            'ordem':       restantes[i]['ordem'],
                            'message_id':  message_id,
                        },
                        countdown=delay,
                    )
                    return

        atualizar_estado_pedido(pedido_id, 2)
        logger.info(f"[{_TAG}] ✅ Fluxo concluído. Estado pedido #{pedido_id} → 2.")
        logger.info("=" * 120)

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            from database import atualizar_estado_pedido
            atualizar_estado_pedido(pedido_id, 1)
            logger.warning(f"[{_TAG}] 🔓 Estado revertido → 1 para pedido #{pedido_id} após erro")
        msg_txt = '(sem texto)'
        if mensagem_whatsapp:
            msg_txt = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0].get('text', {}).get('body', '(sem texto)')
        logger.exception(f"[{_TAG}] ❌ pedido #{pedido_id} | tel: {pedido.get('contact_phone')} | msg: {str(msg_txt)[:500]} | Erro: {exc}")
        notificar_admin_erro_sistema(f"TASK-INTRODUCAO-DIN | pedido #{pedido_id} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(name="tasks.enviar_pedido_dinamico", bind=True, max_retries=0)
def fluxo_enviar_pedido_dinamico(self, pedido, mensagem_whatsapp=None, ordem=1, message_id=None, condicoes=None):
    from database import (
        listar_acoes_fluxo, salvar_mensagem_pedido, atualizar_estado_pedido,
        atualizar_pedido_com_interesse_produto, atualizar_pedido_com_data_envio_pedido,
    )
    from fluxos._executor_acao import executar_acao, filtrar_e_ordenar, calcular_delay, selecionar_variantes
    from agente_verifica_interesse import classificar_interesse_compra

    _TAG = "TASK-PEDIDO-DIN"
    produto_id = pedido['produto_id']
    pedido_id  = pedido['id']

    try:
        if ordem == 1:
            logger.info("=" * 120)
            logger.info(f"[{_TAG}] 📦 pedido #{pedido_id} | iniciando fluxo")
            dados_msg    = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]
            message_id   = dados_msg['id']
            mensagem_txt = dados_msg.get('text', {}).get('body', '') or ''
            salvar_mensagem_pedido(message_id, pedido_id, mensagem_txt, tipo_mensagem='recebida')

            logger.debug(f"[{_TAG}] 🤖 Classificando interesse...")
            interesse_raw  = classificar_interesse_compra(mensagem_txt)
            interesse      = interesse_raw.strip().rstrip('.!?').lower() == 'sim'
            condicao_ativa = 'interesse_sim' if interesse else 'interesse_nao'
            logger.debug(f"[{_TAG}] 🤖 Interesse: {interesse} → condicao='{condicao_ativa}' (IA: '{interesse_raw}')")
            atualizar_pedido_com_interesse_produto(pedido_id, interesse)
            condicoes = ['sempre', condicao_ativa]
        else:
            logger.debug(f"[{_TAG}] ▶ pedido #{pedido_id} | retomando na ordem={ordem}")

        todas_acoes = listar_acoes_fluxo(produto_id, 'pedido')
        acoes = filtrar_e_ordenar(todas_acoes, tuple(condicoes))
        acoes = selecionar_variantes(acoes)

        if not acoes:
            raise ValueError(f"[{_TAG}] Nenhuma ação configurada para 'pedido' do produto {produto_id}")

        restantes = [a for a in acoes if a['ordem'] >= ordem]

        i = 0
        while i < len(restantes):
            acao = restantes[i]
            logger.debug(f"[{_TAG}] ▶ Executando #{acao['ordem']} [{acao['acao']}] ({acao['condicao']})")
            executar_acao(acao, pedido, message_id, pedido_id, tag=_TAG, aplicar_delay=False)
            i += 1

            if i < len(restantes):
                delay = calcular_delay(restantes[i])
                if delay > 0:
                    logger.debug(f"[{_TAG}] ⏳ Agendando #{restantes[i]['ordem']} em {delay:.1f}s")
                    fluxo_enviar_pedido_dinamico.apply_async(
                        kwargs={
                            'pedido':     pedido,
                            'ordem':      restantes[i]['ordem'],
                            'message_id': message_id,
                            'condicoes':  condicoes,
                        },
                        countdown=delay,
                    )
                    return

        atualizar_estado_pedido(pedido_id, 3)
        atualizar_pedido_com_data_envio_pedido(pedido_id)
        logger.info(f"[{_TAG}] ✅ Fluxo concluído. Estado pedido #{pedido_id} → 3.")
        logger.info("=" * 120)

    except Exception as exc:
        if self.request.retries >= self.max_retries:
            from database import atualizar_estado_pedido
            atualizar_estado_pedido(pedido_id, 2)
            logger.warning(f"[{_TAG}] 🔓 Estado revertido → 2 para pedido #{pedido_id} após erro")
        msg_txt = '(sem texto)'
        if mensagem_whatsapp:
            msg_txt = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0].get('text', {}).get('body', '(sem texto)')
        logger.exception(f"[{_TAG}] ❌ pedido #{pedido_id} | tel: {pedido.get('contact_phone')} | msg: {str(msg_txt)[:500]} | Erro: {exc}")
        notificar_admin_erro_sistema(f"TASK-PEDIDO-DIN | pedido #{pedido_id} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)



@shared_task(name="tasks.responder_mensagem", bind=True, max_retries=2)
def fluxo_responder_mensagem(self, pedido, mensagem_whatsapp):
    logger.info("=" * 120)
    logger.info(f"[TASK-RESPONDER-MENSAGEM] 📦 Dados recebidos para responder mensagem: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
    from fluxos.fluxo_responder import executar
    try:
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-RESPONDER-MENSAGEM] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except Exception as exc:
        msg_txt = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0].get('text', {}).get('body', '(sem texto)')
        logger.exception(f"[TASK-RESPONDER-MENSAGEM] ❌ pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | msg: {str(msg_txt)[:500]} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-RESPONDER-MENSAGEM | pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise

@shared_task(name="tasks.enviar_resposta_cliente", bind=True, max_retries=2)
def fluxo_enviar_resposta_cliente(self, pedido, resposta_cliente, pedido_id):
    logger.info(f"[TASK-ENVIAR-RESPOSTA] 📤 pedido #{pedido_id} | tel: {pedido.get('contact_phone')}")
    from fluxos.fluxo_responder import enviar_resposta
    from whatsapp import ErroTransienteWhatsApp
    try:
        enviar_resposta(pedido, resposta_cliente, pedido_id)
        logger.info(f"[TASK-ENVIAR-RESPOSTA] ✅ pedido #{pedido_id}")
    except ErroTransienteWhatsApp as exc:
        logger.warning(f"[TASK-ENVIAR-RESPOSTA] ⚠️ Erro transiente, reagendando | pedido #{pedido_id} | Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        raise self.retry(exc=exc, countdown=60)
    except Exception as exc:
        logger.exception(f"[TASK-ENVIAR-RESPOSTA] ❌ pedido #{pedido_id} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-ENVIAR-RESPOSTA | pedido #{pedido_id} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise


@shared_task(name="tasks.conferir_comprovante_dinamico", bind=True, max_retries=0)
def fluxo_conferir_comprovante_dinamico(self, pedido, mensagem_whatsapp):
    logger.info("=" * 120)
    logger.info(f"[TASK-COMPROVANTE-DIN] 📦 Dados recebidos: \n Pedido: {pedido}")
    from fluxos.fluxo_comprovante_dinamico import executar
    try:
        executar(pedido, mensagem_whatsapp)
        logger.info(f"[TASK-COMPROVANTE-DIN] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            from database import atualizar_estado_pedido
            atualizar_estado_pedido(pedido.get('id'), 3)
            logger.warning(f"[TASK-COMPROVANTE-DIN] 🔓 Estado revertido → 3 para pedido #{pedido.get('id')} após erro")
        msg_txt = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0].get('text', {}).get('body', '(sem texto)')
        logger.exception(f"[TASK-COMPROVANTE-DIN] ❌ pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | msg: {str(msg_txt)[:500]} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-COMPROVANTE-DIN | pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(name="tasks.transcrever_audio", bind=True, max_retries=0)
def fluxo_transcrever_audio(self, pedido, mensagem_whatsapp, path_audio=None):
    logger.info("=" * 120)
    logger.info(f"[TASK-TRANSCRIBIR-AUDIO] 📦 Dados recebidos para transcrever áudio: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
    from fluxos.fluxo_transcrever import executar
    try:
        executar(pedido, mensagem_whatsapp, path_audio=path_audio)
        logger.info(f"[TASK-TRANSCRIBIR-AUDIO] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)
    except Exception as exc:
        msg = mensagem_whatsapp.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {}).get('messages', [{}])[0]
        audio_id = msg.get('audio', {}).get('id', '?')
        logger.exception(f"[TASK-TRANSCRIBIR-AUDIO] ❌ pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | audio_id: {audio_id} | Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        notificar_admin_erro_sistema(f"TASK-TRANSCRIBIR-AUDIO | pedido #{pedido.get('id')} | tel: {pedido.get('contact_phone')} | {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(name="tasks.followup_pagamento_dinamico", bind=True, max_retries=0)
def fluxo_followup_pagamento_dinamico(self):
    from fluxos.fluxo_followup_dinamico import executar
    try:
        executar()
        logger.info(f"[TASK-FOLLOWUP-DIN] ✅ rotina executada com sucesso!")
    except Exception as exc:
        logger.error(f"[TASK-FOLLOWUP-DIN] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()

@shared_task(name="tasks.followup_interesse_dinamico", bind=True, max_retries=0)
def fluxo_followup_interesse_dinamico(self):
    from fluxos.fluxo_followup_interesse_dinamico import executar
    try:
        executar()
        logger.info(f"[TASK-FOLLOWUP-INT] ✅ rotina executada com sucesso!")
    except Exception as exc:
        logger.error(f"[TASK-FOLLOWUP-INT] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()

@shared_task(name="tasks.followup_pagamento_web", bind=True, max_retries=0)
def fluxo_followup_pagamento_web(self):
    from fluxos.fluxo_followup_web import executar
    try:
        executar()
        logger.info(f"[TASK-FOLLOWUP-WEB] ✅ rotina executada com sucesso!")
    except Exception as exc:
        logger.error(f"[TASK-FOLLOWUP-WEB] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()

@shared_task(name="tasks.verificar_emails_clientes", bind=True, max_retries=0)
def verificar_emails_clientes(self):
    """Polling da caixa admin@lsnlivros.com.br — lê respostas de clientes a e-mails de pedidos
    web e aciona o agente de e-mail dedicado. Roda a cada 10min (ver celery_app.py)."""
    _TAG = "TASK-EMAIL-CONVERSAS"
    lock_key = "lock:email_conversas"
    if not _redis.set(lock_key, 1, nx=True, ex=590):  # TTL 9m50s — evita sobreposição entre rodadas de 10min
        logger.info(f"[{_TAG}] ⏭ Outra instância já em execução — ignorando")
        return
    try:
        from fluxos.fluxo_email_conversas import executar
        executar()
        logger.info(f"[{_TAG}] ✅ rotina executada com sucesso!")
    except Exception as exc:
        logger.error(f"[{_TAG}] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        _redis.delete(lock_key)


@shared_task(name="tasks.enviar_confirmacao_web", bind=True, max_retries=2)
def fluxo_enviar_confirmacao_web(self, pedido_id: int):
    logger.info("=" * 120)
    logger.info(f"[TASK-CONFIRMACAO-WEB] 🛒 Iniciando entrega web para pedido #{pedido_id}")
    from fluxos.fluxo_confirmacao_web_dinamico import executar
    try:
        executar(pedido_id)
        logger.info(f"[TASK-CONFIRMACAO-WEB] ✅ Entrega concluída para pedido #{pedido_id}")
        logger.info("=" * 120)
    except Exception as exc:
        logger.error(f"[TASK-CONFIRMACAO-WEB] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=1)
def processar_uploads_google_ads(self):
    from google.ads.googleads.client import GoogleAdsClient
    try:
        logger.info(f"[TASK-GOOGLE-ADS] 📦 Iniciando processamento de uploads para Google Ads...")
        from fluxos.fluxo_upload_google_ads import executar
        executar()
        logger.info(f"[TASK-GOOGLE-ADS] ✅ rotina executada com sucesso!")

    except Exception as exc:
        logger.error(f"[TASK-GOOGLE-ADS] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1} ")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        # Se a API cair ou houver erro de rede, tenta novamente em 10 min
        raise self.retry(exc=exc, countdown=600)

@shared_task(bind=True, max_retries=1)
def processar_uploads_google_sheets(self):
    try:
        logger.info("[TASK-GOOGLE-SHEETS] 📦 Iniciando exportação para Google Sheets...")
        from fluxos.fluxo_upload_google_ads import exportar_para_google_sheets
        exportar_para_google_sheets()
        logger.info("[TASK-GOOGLE-SHEETS] ✅ Rotina executada com sucesso!")
    except Exception as exc:
        logger.error(f"[TASK-GOOGLE-SHEETS] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()
        raise self.retry(exc=exc, countdown=600)


@shared_task(bind=True, max_retries=1)
def processar_orcamento_sheets(self, data_str=None):
    lock_key = "lock:orcamento_sheets"
    if not _redis.set(lock_key, 1, nx=True, ex=3300):  # TTL 55 min — evita sobreposição entre execuções horárias
        logger.info("[TASK-ORCAMENTO-SHEETS] ⏭ Outra instância já em execução — ignorando")
        return

    try:
        from datetime import datetime, timezone, timedelta
        _SP_TZ = timezone(timedelta(hours=-3))
        agora = datetime.now(_SP_TZ)

        if data_str:
            datas = [data_str]
        else:
            hoje  = agora.strftime('%Y-%m-%d')
            ontem = (agora - timedelta(days=1)).strftime('%Y-%m-%d')
            datas = [hoje]
            if agora.hour <= 4:  # Google Ads ainda apura o dia anterior até ~04h
                datas.append(ontem)

        from fluxos.fluxo_orcamento_sheets import processar_orcamento_sheets as _fn
        for data in datas:
            logger.info(f"[TASK-ORCAMENTO-SHEETS] 📊 Processando data={data}...")
            resultado = _fn(data)
            logger.info(f"[TASK-ORCAMENTO-SHEETS] ✅ {data}: {resultado}")
    except Exception as exc:
        logger.error(f"[TASK-ORCAMENTO-SHEETS] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()
        raise self.retry(exc=exc, countdown=600)
    finally:
        _redis.delete(lock_key)


def _extrair_waba_id(data):
    """health_status traz a cadeia de entidades (PHONE_NUMBER, WABA, BUSINESS, APP) —
    extrai o id da entidade WABA, se presente."""
    entidades = (data.get('health_status') or {}).get('entities', [])
    for e in entidades:
        if e.get('entity_type') == 'WABA':
            return e.get('id')
    return None


def _registrar_mudancas_estado(t, nova_qualidade, novo_status):
    """Grava em notificacoes_telefone só quando quality_rating ou status_api realmente
    mudaram em relação ao que já estava salvo — inclusive na primeira checagem
    (UNKNOWN/None → primeiro valor real), por decisão explícita do usuário."""
    from database import criar_notificacao_telefone

    velha_qualidade = t.get('quality_rating')
    if velha_qualidade != nova_qualidade:
        de = velha_qualidade or 'nunca checado'
        criar_notificacao_telefone(
            t['id'], t['produto_id'], 'quality_rating_change',
            f"Qualidade mudou de {de} para {nova_qualidade}",
            payload_raw={'de': velha_qualidade, 'para': nova_qualidade, 'origem': 'polling'}
        )

    velho_status = t.get('status_api')
    if novo_status and velho_status != novo_status:
        de = velho_status or 'nunca checado'
        criar_notificacao_telefone(
            t['id'], t['produto_id'], 'status_change',
            f"Status mudou de {de} para {novo_status}",
            payload_raw={'de': velho_status, 'para': novo_status, 'origem': 'polling'}
        )


def _checar_qualidade_telefone(t, _TAG, WHATSAPP_API_URL):
    """Consulta a Graph API pra um número e persiste o resultado. Roda em thread própria
    (chamada via ThreadPoolExecutor) — cada chamada usa sua própria conexão do pool do MySQL,
    então é segura em paralelo. Retorna True em caso de sucesso, False em falha."""
    import requests
    from database import (get_whatsapp_token, atualizar_qualidade_telefone,
                           registrar_erro_qualidade_telefone, normalizar_quality_rating)

    telefone_id = t['id']
    try:
        token = get_whatsapp_token(t['api_phone_number_id'])
    except ValueError as e:
        registrar_erro_qualidade_telefone(telefone_id, str(e)[:255])
        logger.warning(f"[{_TAG}] ⚠️ Telefone #{telefone_id} ({t['telefone']}): {e}")
        return False
    try:
        resp = requests.get(
            f"{WHATSAPP_API_URL}{t['api_phone_number_id']}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "quality_rating,status,name_status,health_status"},
            timeout=15,
        )
        if not resp.ok:
            registrar_erro_qualidade_telefone(telefone_id, f"HTTP {resp.status_code}: {resp.text[:200]}")
            logger.warning(f"[{_TAG}] ⚠️ Telefone #{telefone_id} ({t['telefone']}): HTTP {resp.status_code} — {resp.text[:200]}")
            return False

        data = resp.json()
        nova_qualidade = normalizar_quality_rating(data.get('quality_rating'))
        novo_status = data.get('status')
        waba_id = _extrair_waba_id(data)

        _registrar_mudancas_estado(t, nova_qualidade, novo_status)

        atualizar_qualidade_telefone(telefone_id, nova_qualidade, novo_status, data.get('name_status'), waba_id)
        return True
    except Exception as e:
        registrar_erro_qualidade_telefone(telefone_id, str(e)[:255])
        logger.warning(f"[{_TAG}] ⚠️ Telefone #{telefone_id} ({t['telefone']}): erro — {e}")
        return False


def _executar_checagem_qualidade(telefones, _TAG):
    """Roda _checar_qualidade_telefone em paralelo pra uma lista de números e loga o
    resultado. Compartilhado pela rodada horária (todos os números) e pela rodada sob
    demanda (só os números de um produto)."""
    from concurrent.futures import ThreadPoolExecutor
    from config import WHATSAPP_API_URL

    logger.info(f"[{_TAG}] 🔍 Checando qualidade de {len(telefones)} números...")

    # Chamadas de rede em paralelo (I/O-bound) — o pool de conexões do MySQL tem
    # pool_size=5, então limitamos a mesma quantidade de threads simultâneas.
    with ThreadPoolExecutor(max_workers=5) as pool:
        resultados = list(pool.map(lambda t: _checar_qualidade_telefone(t, _TAG, WHATSAPP_API_URL), telefones))

    ok = sum(1 for r in resultados if r)
    falhas = len(resultados) - ok
    logger.info(f"[{_TAG}] ✅ Concluído: {ok} ok, {falhas} falha(s) de {len(telefones)}")
    # Alerta só em falha generalizada (ex: WHATSAPP_API_URL errado, Graph API fora do ar) —
    # não a cada execução por causa de 1-2 tokens já conhecidos como quebrados (ex: placeholder
    # não preenchido), senão o alerta vira ruído e passa a ser ignorado.
    if telefones and falhas / len(telefones) >= 0.3:
        notificar_admin_erro_sistema(f"{_TAG} | {falhas} de {len(telefones)} número(s) com falha na checagem — pode ser problema sistêmico")
    return ok, falhas


@shared_task(name="tasks.verificar_qualidade_whatsapp", bind=True, max_retries=0)
def verificar_qualidade_whatsapp(self):
    """Checa quality_rating/status/name_status de todos os números cadastrados, via Graph API,
    e persiste em telefones_produto. Roda de hora em hora (min :20). Substitui a checagem
    manual via scripts/diagnostico_whatsapp_estado.py."""
    _TAG = "TASK-QUALIDADE-WPP"
    lock_key = "lock:qualidade_whatsapp"
    if not _redis.set(lock_key, 1, nx=True, ex=3300):  # TTL 55 min — evita sobreposição entre execuções horárias
        logger.info(f"[{_TAG}] ⏭ Outra instância já em execução — ignorando")
        return
    try:
        from database import listar_telefones_com_token
        _executar_checagem_qualidade(listar_telefones_com_token(), _TAG)
    except Exception as exc:
        logger.error(f"[{_TAG}] ❌ Erro geral: {exc}")
        import traceback
        traceback.print_exc()
        notificar_admin_erro_sistema(f"{_TAG} | erro geral: {type(exc).__name__}")
    finally:
        _redis.delete(lock_key)


@shared_task(name="tasks.verificar_qualidade_whatsapp_produto", bind=True, max_retries=0)
def verificar_qualidade_whatsapp_produto(self, produto_id):
    """Versão sob demanda de verificar_qualidade_whatsapp, escopada a um produto — disparada
    pelo botão 'Atualizar agora' em admin/numeros_whatsapp.html. Lock próprio (curto, só
    contra clique duplo) pra não disputar com a rodada horária global."""
    _TAG = "TASK-QUALIDADE-WPP-PRODUTO"
    lock_key = f"lock:qualidade_whatsapp:produto:{produto_id}"
    if not _redis.set(lock_key, 1, nx=True, ex=30):
        logger.info(f"[{_TAG}] ⏭ Já em execução pro produto #{produto_id} — ignorando clique duplicado")
        return
    try:
        from database import listar_telefones_com_token
        _executar_checagem_qualidade(listar_telefones_com_token(produto_id), _TAG)
    except Exception as exc:
        logger.error(f"[{_TAG}] ❌ Erro geral (produto #{produto_id}): {exc}")
        import traceback
        traceback.print_exc()
    finally:
        _redis.delete(lock_key)


@shared_task(name="tasks.processar_evento_conta_whatsapp", bind=True, max_retries=1)
def processar_evento_conta_whatsapp(self, body):
    """Persiste eventos de webhook de nível-número (qualidade, nome) e de nível-conta
    (WABA/Business Manager). Roteada na fila 'normal' — separada da fila 'urgente' usada
    por tasks.processar_webhook (fluxo de mensagens/vendas)."""
    try:
        from whatsapp_eventos_conta import processar_evento_conta
        processar_evento_conta(body)
    except Exception as exc:
        logger.error(f"[TASK-EVENTO-CONTA] ❌ Erro: {exc}")
        import traceback
        traceback.print_exc()
        if self.request.retries >= self.max_retries:
            notificar_admin_erro_sistema(f"TASK-EVENTO-CONTA | falha definitiva: {type(exc).__name__}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=0)
def processar_pagamentos_pix(self, tenant_slug: str = 'lsn-livros'):
    try:
        logger.info(f'[TASK-PIX-BB][{tenant_slug}] Iniciando coleta de PIX recebidos')
        from fluxos.fluxo_pix_bb import executar
        executar(tenant_slug=tenant_slug)
        logger.info(f'[TASK-PIX-BB][{tenant_slug}] ✅ Concluído')
    except Exception as exc:
        logger.error(f'[TASK-PIX-BB][{tenant_slug}] ❌ Erro: {exc}')
        import traceback
        traceback.print_exc()


@shared_task(bind=True, max_retries=0)
def processar_pagamentos_pix_fechamento(self, tenant_slug: str = 'lsn-livros'):
    """Busca PIX de ontem para cobrir o gap 23:15–23:59 não capturado na última execução do dia."""
    try:
        from datetime import datetime, timezone, timedelta
        from fluxos.fluxo_pix_bb import executar
        _SP_TZ = timezone(timedelta(hours=-3))
        ontem = (datetime.now(_SP_TZ) - timedelta(days=1)).strftime('%d/%m/%Y')
        logger.info(f'[TASK-PIX-BB-FECHAMENTO][{tenant_slug}] Buscando PIX de ontem ({ontem})')
        executar(ontem, tenant_slug=tenant_slug)
        logger.info(f'[TASK-PIX-BB-FECHAMENTO][{tenant_slug}] ✅ Concluído')
    except Exception as exc:
        logger.error(f'[TASK-PIX-BB-FECHAMENTO][{tenant_slug}] ❌ Erro: {exc}')
        import traceback
        traceback.print_exc()


@shared_task(bind=True, max_retries=0)
def verificar_pagamentos_pendentes(self):
    try:
        logger.info('[TASK-RESILIENCIA-PGTO] Iniciando sweep de pagamentos BB Pay pendentes')
        from fluxos.fluxo_verificar_pagamentos_pendentes import executar
        executar()
        logger.info('[TASK-RESILIENCIA-PGTO] ✅ Sweep concluído')
    except Exception as exc:
        logger.error(f'[TASK-RESILIENCIA-PGTO] ❌ Erro: {exc}')
        import traceback
        traceback.print_exc()


@shared_task(bind=True, max_retries=0)
def verificar_cartao_pendente(self):
    try:
        logger.info('[TASK-RESILIENCIA-CARTAO] Iniciando sweep de cartão Cielo pendente')
        from fluxos.fluxo_verificar_cartao_pendente import executar
        executar()
        logger.info('[TASK-RESILIENCIA-CARTAO] ✅ Sweep concluído')
    except Exception as exc:
        logger.error(f'[TASK-RESILIENCIA-CARTAO] ❌ Erro: {exc}')
        import traceback
        traceback.print_exc()


@shared_task(bind=True, max_retries=1)
def enviar_email_entrega(self, pedido_id: int):
    logger.info("=" * 120)
    logger.info(f"[TASK-EMAIL] 📧 Iniciando entrega por e-mail para pedido #{pedido_id}")
    from fluxos.entrega_pedido_email import executar
    try:
        executar(pedido_id)
        logger.info(f"[TASK-EMAIL] ✅ E-mail entregue para pedido #{pedido_id}")
        logger.info("=" * 120)
    except Exception as exc:
        logger.error(f"[TASK-EMAIL] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        import traceback
        traceback.print_exc()
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=60)


@shared_task(name='tasks.emitir_nfe', bind=True, max_retries=3)
def emitir_nfe(self, pagamento_pix_id: int, config_id: int | None = None):
    """Emite NF-e para um pagamento PIX. Retry com backoff exponencial."""
    _TAG = 'TASK-NFE'
    try:
        from fiscal.nfe_service import emitir_nfe as _emitir
        resultado = _emitir(pagamento_pix_id, config_id=config_id)
        status = resultado.get('status', '?')
        nfe_id = resultado.get('nfe_id')
        logger.info(f'[{_TAG}] PIX={pagamento_pix_id} nfe_id={nfe_id} → {status}')
    except (ValueError, RuntimeError) as exc:
        # Erros permanentes (config faltando, XSD inválido, PIX não encontrado)
        logger.error(f'[{_TAG}] ❌ Erro permanente PIX={pagamento_pix_id}: {exc}')
        notificar_admin_erro_sistema(f'TASK-NFE | PIX={pagamento_pix_id} | {type(exc).__name__}: {str(exc)[:200]}')
    except Exception as exc:
        tentativa = self.request.retries + 1
        countdown  = 60 * (2 ** self.request.retries)   # 60s → 120s → 240s
        logger.exception(
            f'[{_TAG}] ❌ PIX={pagamento_pix_id} | '
            f'Tentativa {tentativa}/{self.max_retries + 1} | retry em {countdown}s: {exc}'
        )
        if self.request.retries >= self.max_retries:
            notificar_admin_erro_sistema(f'TASK-NFE | PIX={pagamento_pix_id} | esgotou retries | {type(exc).__name__}')
        raise self.retry(exc=exc, countdown=countdown)


@shared_task(name='tasks.reprocessar_nfe_pendentes', bind=True, max_retries=0)
def reprocessar_nfe_pendentes(self, config_id: int | None = None, limite: int = 50):
    """Beat task — recupera PIX das últimas 24h sem NF-e, reagendando emissão."""
    _TAG = 'TASK-NFE-REPRO'
    try:
        from database import buscar_pagamentos_pix_sem_nfe
        ids = buscar_pagamentos_pix_sem_nfe(limite=limite, dias_atras=1, config_id=config_id)
        if not ids:
            logger.debug(f'[{_TAG}] Nenhum PIX pendente')
            return
        logger.info(f'[{_TAG}] {len(ids)} PIX pendente(s) → agendando emissão (config_id={config_id})')
        for pix_id in ids:
            emitir_nfe.apply_async(args=[pix_id], kwargs={'config_id': config_id})
    except Exception as exc:
        logger.error(f'[{_TAG}] ❌ Erro: {exc}')
        import traceback
        traceback.print_exc()
