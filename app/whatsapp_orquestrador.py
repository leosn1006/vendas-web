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

        if 'messages' not in value:
            return None

        mensagem = value['messages'][0]
        contato = value['contacts'][0]
        metadata = value.get('metadata', {})

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

    except (KeyError, IndexError):
        return None

def recebe_webhook(mensagem_whatsapp):
    # Import lazy — evita o import circular com tasks.py
    from tasks import fluxo_enviar_introducao

    try:
        dados = extrair_dados_mensagem(mensagem_whatsapp)
        pedido, fluxo = buscar_pedido_e_fluxo(dados)

        tempo_espera = random.uniform(20, 40)
        if fluxo == 'enviar_introducao':
            fluxo_enviar_introducao.apply_async(args=[pedido, mensagem_whatsapp], countdown=tempo_espera)

        return "Mensagem processada com sucesso!"

    except Exception as e:
        logger.error(f"[ORQUESTRADOR] ❌ Erro ao processar webhook: {e}")
        import traceback
        traceback.print_exc()
        raise e

def buscar_pedido_e_fluxo(dados):
    pedido = None
    fluxo = None

    if dados is None:
        logger.info("[ORQUESTRADOR] ❌ Mensagem recebida, mas não é do tipo texto ou formato inválido.")
        return None, None

    numero_remetente = dados['numero_remetente']
    nome             = dados['nome']
    msg_enviado_cliente = dados['texto']
    phone_number_id  = dados['phone_number_id']

    logger.info(f"[ORQUESTRADOR] 📱 Mensagem de {nome} ({numero_remetente}): {msg_enviado_cliente}")

    pedido = get_ultimo_pedido_by_phone(numero_remetente, dados.get('produto'))

    if pedido is not None:
        logger.info(f"[ORQUESTRADOR] 👤 Cliente existente: {nome} (Pedido #{pedido['id']})")
        match dados.get('estado_id'):
            case 1:
                fluxo = 'enviar_introducao'
            case 2:
                fluxo = 'enviar_produto'
            case 3 | 4:
                fluxo = 'agradecimento'
            case _:
                fluxo = 'enviar_introducao'
        return pedido, fluxo

    else:
        logger.info(f"[ORQUESTRADOR] 🆕 Novo cliente: {nome}")
        pedido = get_ultimo_pedido_por_mensagem_sugerida(msg_enviado_cliente)

        if pedido is not None:
            logger.info(f"[ORQUESTRADOR] 🔗 Associando contato ao pedido existente: {pedido['id']}")
            pedido = vincula_pedido_com_contato(pedido['id'], numero_remetente, nome, phone_number_id)

            if pedido is not None:
                logger.info(f"[ORQUESTRADOR] ✅ Pedido #{pedido.get('id')} vinculado a {nome}")
                return pedido, "enviar_introducao"

        # Pedido não encontrado ou falha ao vincular — cria novo para não perder o cliente
        logger.info(f"[ORQUESTRADOR] ℹ️ Criando pedido sem campanha: {nome} ({numero_remetente})")
        id_pedido = criar_pedido_sem_campanha(dados)
        pedido = get_pedido(id_pedido)
        return pedido, "enviar_introducao"

def criar_pedido_sem_campanha(dados):
    # Correção: timestamp_mysql era usado antes de ser definido
    try:
        timestamp_mysql = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        logger.error(f"Erro ao formatar data: {e}")
        timestamp_mysql = None

    pedido = Pedido(
        produto_id=dados.get('produto', 1),
        valor_pago=0.00,
        estado_id=1,
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
