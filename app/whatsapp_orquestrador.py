import logging
from whatspp_enviar_mensagem import enviar_mensagem_texto
from whatspp_enviar_introducao import enviar_introducao
from database import get_ultimo_pedido_by_phone, get_ultimo_pedido_por_mensagem_sugerida, vincula_pedido_com_contato
from agente_vendas_sem_gluten import responder_cliente

logger = logging.getLogger(__name__)

def extrair_dados_mensagem(mensagem_whatsapp):
    try:
        value = mensagem_whatsapp['entry'][0]['changes'][0]['value']

        # Verificar se tem mensagens
        if 'messages' not in value:
            return None

        mensagem = value['messages'][0]
        contato = value['contacts'][0]
        metadata = value.get('metadata', {})

        # Verificar se é mensagem de texto
        if mensagem['type'] != 'text':
            return None

        return {
            'numero_remetente': mensagem['from'],
            'id_conversa': mensagem['id'],
            'nome': contato['profile']['name'],
            'texto': mensagem['text']['body'],
            'phone_number_id': metadata.get('phone_number_id')
        }
    except (KeyError, IndexError) as e:
        return None

def recebe_webhook(mensagem_whatsapp):
    try:
        # Extrair dados da mensagem
        dados = extrair_dados_mensagem(mensagem_whatsapp)

        if dados is None:
            logger.info("[ORQUESTRADOR] ❌ Mensagem recebida, mas não é do tipo texto ou formato inválido.")
            return "Mensagem recebida, mas não processada"

        numero_remetente = dados['numero_remetente']
        id_conversa = dados['id_conversa']
        nome = dados['nome']
        msg_enviado_cliente = dados['texto']
        phone_number_id = dados['phone_number_id']

        logger.info(f"[ORQUESTRADOR] 📱 Mensagem de {nome} ({numero_remetente}): {msg_enviado_cliente}")

        # Verificar se já existe pedido para este telefone
        pedido = get_ultimo_pedido_by_phone(numero_remetente)

        if pedido is None:
            logger.info(f"[ORQUESTRADOR] 🆕 Novo cliente: {nome}")
            # Verifica se tem um pedido cadastrado com essa mensagem sugerida (última 1 hora)
            pedido = get_ultimo_pedido_por_mensagem_sugerida(msg_enviado_cliente)
            if pedido is not None:
                logger.info(f"[ORQUESTRADOR] 🔗 Associando contato ao pedido existente: {pedido['id']}")
                pedido =vincula_pedido_com_contato(pedido['id'], numero_remetente, nome, phone_number_id)
                if pedido is not None:
                    logger.info(f"[ORQUESTRADOR] ✅ Pedido #{pedido.get('id')} atualizado com contato {nome} ({numero_remetente})")
                    #TODO abrir uma thread para enviar mensagem de resposta automática, para não atrasar a resposta do webhook
                    enviar_introducao(pedido)
                    return "Webhook processado com sucesso!"
                else:
                    #TODO depois incluir cliente no pedido sem vinculdo de pedido, para não perder o cliente mesmo que o pedido não seja encontrado
                    logger.error(f"[ORQUESTRADOR] ❌ Falha ao atualizar pedido #{pedido['id']} com contato {nome} ({numero_remetente})")

            else:
                logger.info(f"[ORQUESTRADOR] ℹ️ Nenhum pedido encontrado para associar")
        else:
            logger.info(f"[ORQUESTRADOR] 👤 Cliente existente: {nome} (Pedido #{pedido['id']})")

        # Enviar resposta automática
        # resposta = responder_cliente(msg_enviado_cliente)
        # enviar_mensagem_texto(mensagem_whatsapp, resposta)

        return "Webhook processado com sucesso!"
    except Exception as e:
        logger.error(f"[ORQUESTRADOR] ❌ Erro ao processar webhook: {e}")
        import traceback
        traceback.print_exc()
        raise e
