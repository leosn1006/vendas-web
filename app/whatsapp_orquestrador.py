import logging
import random
from datetime import datetime
from whatspp_enviar_mensagem import enviar_mensagem_texto
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

        pedido, fluxo = buscar_pedido_e_fluxo(dados)
        logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 Pedido e fluxo determinados: {pedido}, {fluxo}" )

        tempo_espera = random.uniform(20, 40)
        logger.info(f"[ORQUESTRADOR-WEBHOOK] ⏳ Aguardando {tempo_espera:.1f}s antes de enviar para o fluxo...")
        if fluxo == 'enviar_introducao':
            logger.info(f"[ORQUESTRADOR-WEBHOOK] 📥 mandando para o fluxo de introdução: {mensagem_whatsapp}" )
            from tasks import fluxo_enviar_introducao
            fluxo_enviar_introducao.apply_async(args=[pedido, mensagem_whatsapp], countdown=tempo_espera)

        # Enviar resposta automática
        # resposta = responder_cliente(msg_enviado_cliente)
        # enviar_mensagem_texto(mensagem_whatsapp, resposta)

        return "Mensagem processada com sucesso!"
    except Exception as e:
        logger.error(f"[ORQUESTRADOR-WEBHOOK] ❌ Erro ao processar webhook: {e}")
        import traceback
        traceback.print_exc()
        raise e

def buscar_pedido_e_fluxo(dados):
    pedido = None
    fluxo = None
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
    pedido = get_ultimo_pedido_by_phone(numero_remetente, dados.get('produto'))
    if pedido is not None:

        logger.info(f"[ORQUESTRADOR] 👤 Cliente existente: {nome} (Pedido #{pedido['id']})")
        match dados.get('estado_id'):
            case 1: # Cliente acessou a página de vendas e clicou para enviar mensagem'
                fluxo = 'enviar_introducao'
            case 2: # Enviado mensagem de introdução
                fluxo = 'enviar_produto'
            case 3 | 4:  # Respondido introdução com interesse e #Respondido introdução sem interesse
                fluxo = 'agradecimento'
            case _:
                #TODO pensar nisso depois
                fluxo = 'enviar_introducao' # Fluxo padrão para estados desconhecidos
        return pedido, fluxo
    else:
        logger.info(f"[ORQUESTRADOR] 🆕 Novo cliente: {nome}")
        # Verifica se tem um pedido cadastrado com essa mensagem sugerida (última 1 hora)
        pedido = get_ultimo_pedido_por_mensagem_sugerida(msg_enviado_cliente)
        if pedido is not None:
            logger.info(f"[ORQUESTRADOR] 🔗 Associando contato ao pedido existente: {pedido['id']}")
            pedido = vincula_pedido_com_contato(pedido['id'], numero_remetente, nome, phone_number_id)
            if pedido is not None:
                logger.info(f"[ORQUESTRADOR] ✅ Pedido #{pedido.get('id')} atualizado com o contato {nome} ({numero_remetente})")
                return pedido, "enviar_introducao"
            else:
                #muito raro isso acontecer, mas pode ocorrer se o pedido for excluído ou atualizado por outro processo entre a consulta e a atualização. Nesse caso, o ideal seria criar um novo pedido sem associação, para não perder o cliente mesmo que o pedido não seja encontrado
                # gera um peido para não perder o cliente, mesmo que o pedido não seja encontrado
                logger.info(f"[ORQUESTRADOR] ℹ️ Incluindo pedido sem associação: {nome} ({numero_remetente}) - mensagem sugerida: '{msg_enviado_cliente}'")
                id_pedido = criar_pedido_sem_campanha(dados)
                pedido = get_pedido(id_pedido)
                return pedido, "enviar_introducao"
        else:
            # gera um peido para não perder o cliente, mesmo que o pedido não seja encontrado
            logger.info(f"[ORQUESTRADOR] ℹ️ Incluindo pedido sem associação: {nome} ({numero_remetente}) - mensagem sugerida: '{msg_enviado_cliente}'")
            id_pedido = criar_pedido_sem_campanha(dados)
            pedido = get_pedido(id_pedido)
            return pedido, "enviar_introducao"

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
    criar_pedido(pedido)
    return pedido
