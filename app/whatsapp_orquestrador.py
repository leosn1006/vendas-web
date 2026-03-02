import logging
import random
from celery_app import celery_app
from datetime import datetime
from database import (get_ultimo_pedido_by_phone, get_ultimo_pedido_por_mensagem_sugerida,
                      vincula_pedido_com_contato, Pedido, criar_pedido, get_pedido,
                      get_produto_by_phone_number_id)
from agente_resposta_produto import responder_cliente

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

        # Verificar se é mensagem de texto ou documento
        if mensagem['type'] != 'text' and mensagem['type'] != 'document' and mensagem['type'] != 'image'and mensagem['type'] != 'audio':
            return None

        display_phone = metadata.get('display_phone_number')
        produto_db = get_produto_by_phone_number_id(display_phone) if display_phone else None
        produto = produto_db['id'] if produto_db else 1
        return {
            'numero_remetente': mensagem['from'],
            'id_conversa': mensagem['id'],
            'nome': contato['profile']['name'],
            'texto': mensagem['text']['body'] if mensagem['type'] == 'text' else None,
            'documento': mensagem['document']['url'] if mensagem['type'] == 'document' else None,
            'phone_number_id': metadata.get('phone_number_id'),
            'whatsapp_campanha': metadata.get('display_phone_number'),
            'produto': produto
        }

    except (KeyError, IndexError) as e:
        return None

def recebe_webhook(mensagem_whatsapp):
    try:
        logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 Recebendo webhook do WhatsApp: {mensagem_whatsapp}" )
        # Extrair dados da mensagem
        dados = extrair_dados_mensagem(mensagem_whatsapp)
        logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 Dados extraídos da mensagem: {dados}" )
        if dados is None:
            logger.info("[ORQUESTRADOR-WEBHOOK] ⚠️ Mensagem recebida, mas não é do tipo texto ou formato inválido.")
            return "Mensagem recebida, mas não processada"

        pedido = buscar_pedido(dados)

        logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 Enfileira da fila correta: {pedido}" )
        # enfileira na fila conrreta de acordo com o estado do pedido.
        tempo_espera = random.uniform(20, 40)
        # se for um audio, manda direto para o fluxo de transcrever, independente do estado do pedido, para evitar erros de transcrição de outros tipos de mídia e lá será redirecionado para o fluxo correto
        if mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['type'] == 'audio':
            logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de transcrever áudio: {mensagem_whatsapp}" )
            celery_app.send_task("tasks.transcrever_audio", args=[pedido, mensagem_whatsapp],countdown=tempo_espera)
            return "Mensagem de áudio recebida e enviada para transcrição"

        match pedido.get('estado_id'):
            case 1: # Cliente acessou a página de vendas e clicou para enviar mensagem ou veio direto pelo whatsapp sem passar pela página de vendas, ou seja, estado inicial do pedido'
                logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de introdução dinâmico")
                celery_app.send_task("tasks.enviar_introducao_dinamico", args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
            case 2: # cliente respondendo a introdução, se quer ou não receber o produto
                logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de pedido dinâmico")
                celery_app.send_task("tasks.enviar_pedido_dinamico", args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
            case _:
                tipo_msg = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['type']
                if tipo_msg == 'text':
                    logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de responder cliente")
                    celery_app.send_task("tasks.responder_mensagem", args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
                elif tipo_msg in ('document', 'image'):
                    logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de conferir comprovante dinâmico")
                    celery_app.send_task("tasks.conferir_comprovante_dinamico", args=[pedido, mensagem_whatsapp], countdown=tempo_espera)

        return "Mensagem processada com sucesso!"

    except Exception as e:
        logger.error(f"[ORQUESTRADOR-WEBHOOK] ❌ Erro ao processar webhook: {e}")
        import traceback
        traceback.print_exc()
        raise e

def buscar_pedido(dados):
    pedido = None

    if dados is None:
        logger.info("[ORQUESTRADOR]  Mensagem recebida, mas não é do tipo texto ou formato inválido.")
        return "Mensagem recebida, mas não processada"

    numero_remetente = dados['numero_remetente']
    id_conversa = dados['id_conversa']
    nome = dados['nome']
    msg_enviado_cliente = dados['texto']
    phone_number_id = dados['phone_number_id']

    logger.info(f"[ORQUESTRADOR] 📱 Mensagem de {nome} ({numero_remetente}): {msg_enviado_cliente}")

    # Verificar se já existe pedido para este telefone
    pedido = get_ultimo_pedido_by_phone(numero_remetente, dados.get('produto'))
    if pedido is not None:
        logger.info(f"[ORQUESTRADOR] 👤 Cliente existente: {nome} (Pedido #{pedido['id']})")
        return pedido
    else:
        logger.info(f"[ORQUESTRADOR] 🆕 Novo cliente: {nome}")
        # Verifica se tem um pedido cadastrado com essa mensagem sugerida (última 1 hora)
        pedido = get_ultimo_pedido_por_mensagem_sugerida(msg_enviado_cliente)
        if pedido is not None:
            logger.info(f"[ORQUESTRADOR] 🔗 Associando contato ao pedido existente: {pedido['id']}")
            pedido = vincula_pedido_com_contato(pedido['id'], numero_remetente, nome, phone_number_id)
            if pedido is not None:
                logger.info(f"[ORQUESTRADOR] ✅ Pedido #{pedido.get('id')} atualizado com o contato {nome} ({numero_remetente})")
                return pedido
            else:
                # muito raro isso acontecer, mas pode ocorrer se o pedido for excluído ou atualizado por outro processo entre a consulta e a atualização. Nesse caso, o ideal seria criar um novo pedido sem associação, para não perder o cliente mesmo que o pedido não seja encontrado
                # gera um peido para não perder o cliente, mesmo que o pedido não seja encontrado
                logger.info(f"[ORQUESTRADOR] ℹ️ Incluindo pedido sem associação restrito: {nome} ({numero_remetente}) - mensagem sugerida: '{msg_enviado_cliente}'")
                id_pedido = criar_pedido_sem_campanha(dados)
                pedido = get_pedido(id_pedido)
                return pedido
        else:
            # gera um peido para não perder o cliente, mesmo que o pedido não seja encontrado
            logger.info(f"[ORQUESTRADOR] ℹ️ Incluindo pedido sem associação: {nome} ({numero_remetente}) - mensagem sugerida: '{msg_enviado_cliente}'")
            id_pedido = criar_pedido_sem_campanha(dados)
            pedido = get_pedido(id_pedido)
            return pedido

def criar_pedido_sem_campanha(dados):

    timestamp_mysql = None
    try: # Pega o momento atual
        agora = datetime.now()
        # Formata para o padrão MySQL
        timestamp_mysql = agora.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.error(f"Erro ao formatar data: {e}")
        timestamp_mysql = None

    pedido = Pedido(
            produto_id= dados.get('produto', 1), # Produto padrão se não encontrar campanha
            valor_pago=0.00,
            estado_id=1,  # Estado Iniciado
            gclid=None,
            data_ultima_atualizacao=None,
            mensagem_sugerida=None,
            emoji_sugerida=None,
            phone_number_id=dados.get('phone_number_id'),
            contact_phone=dados.get('numero_remetente'),
            contact_name=dados.get('nome'),
            data_pedido=timestamp_mysql,
            campaignid=None,
            adgroupid=None,
            creative=None,
            matchtype=None,
            device=None,
            placement=None,
            video_id=None
        )

    return criar_pedido(pedido)
