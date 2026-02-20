import logging
import random
from datetime import datetime
from database import get_ultimo_pedido_by_phone, get_ultimo_pedido_por_mensagem_sugerida, vincula_pedido_com_contato, Pedido, criar_pedido, get_pedido
from agente_vendas_sem_gluten import responder_cliente
from config import CAMPANHA_WHATSAPP

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

        produto = CAMPANHA_WHATSAPP.get(metadata.get('display_phone_number'), 1)
        return {
            'numero_remetente': mensagem['from'],
            'id_conversa': mensagem['id'],
            'nome': contato['profile']['name'],
            'texto': mensagem['text']['body'],
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
        match pedido.get('estado_id'):
            case 1: # Cliente acessou a página de vendas e clicou para enviar mensagem ou veio direto pelo whatsapp sem passar pela página de vendas, ou seja, estado inicial do pedido'
                logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de introdução: {mensagem_whatsapp}" )
                from tasks import fluxo_enviar_introducao
                fluxo_enviar_introducao.apply_async(args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
            case 2: # cliente respondendo a introdução, se quer ou não receber o produto
                logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de enviar pedido: {mensagem_whatsapp}" )
                from tasks import fluxo_enviar_pedido
                fluxo_enviar_pedido.apply_async(args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
            case 3 | 4:  # Respondido introdução com interesse e #Respondido introdução sem interesse
                if mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['type'] == 'text':
                    logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de responder cliente: {mensagem_whatsapp}" )
                    #from tasks import fluxo_responder_cliente
                    # fluxo_responder_cliente.apply_async(args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
                elif mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['type'] == 'document':
                    logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de responder cliente com documento: {mensagem_whatsapp}" )
                    #from tasks import fluxo_responder_cliente_com_documento
                    #fluxo_conferir_comprovante.apply_async(args=[pedido, mensagem_whatsapp], countdown=tempo_espera)
            case _:
                #TODO pensar nisso depois
                logger.info(f"[ORQUESTRADOR-WEBHOOK] ⚠️ fluxo não previsto para a mensagem: Estado do pedido: {pedido.get('estado_id')}" )

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
