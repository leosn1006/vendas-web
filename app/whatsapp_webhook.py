import json
import logging
from whatspp_enviar_mensagem import enviar_mensagem_texto
from database import get_ultimo_pedido_by_phone, salvar_mensagem_pedido
from agente_vendas_sem_gluten import responder_cliente


logger = logging.getLogger(__name__)

def extrair_dados_mensagem(mensagem_whatsapp):
    """
    Extrai dados da mensagem do WhatsApp.

    Returns:
        dict com: numero_remetente, id_conversa, nome, texto (ou None se inválido)
    """
    try:
        value = mensagem_whatsapp['entry'][0]['changes'][0]['value']

        # Verificar se tem mensagens
        if 'messages' not in value:
            return None

        mensagem = value['messages'][0]
        contato = value['contacts'][0]

        # Verificar se é mensagem de texto
        if mensagem['type'] != 'text':
            return None

        return {
            'numero_remetente': mensagem['from'],
            'id_conversa': mensagem['id'],
            'nome': contato['profile']['name'],
            'texto': mensagem['text']['body']
        }
    except (KeyError, IndexError) as e:
        logger.error(f"Erro ao extrair dados da mensagem: {e}")
        return None

def recebe_webhook(mensagem_whatsapp):
    try:
        # Extrair dados da mensagem
        dados = extrair_dados_mensagem(mensagem_whatsapp)

        if dados is None:
            logger.info("[WEBHOOK] ❌ Mensagem recebida, mas não é do tipo texto ou formato inválido.")
            return "Mensagem recebida, mas não processada"

        numero_remetente = dados['numero_remetente']
        id_conversa = dados['id_conversa']
        nome = dados['nome']
        texto = dados['texto']

        logger.info(f"[WEBHOOK] 📱 Mensagem de {nome} ({numero_remetente}): {texto}")

        # Verificar se já existe pedido para este telefone
        ultimo_pedido = get_ultimo_pedido_by_phone(numero_remetente, texto)
        print(f"[WEBHOOK] 🔍 Último pedido encontrado: {ultimo_pedido}")


#        if ultimo_pedido is None:
# TODO criar pedido e achar cliente
#            # Cliente novo - criar primeiro pedido
#            logger.info(f"[WEBHOOK] 🆕 Novo cliente: {nome}")
#            pedido_id = criar_pedido(
#                mensagem_venda="Iniciado via WhatsApp",
#                produto_id=1,  # Produto padrão (ebook celiaco)
#                contact_name=nome,
#                contact_phone=numero_remetente
#            )
#            log.info(f"[WEBHOOK] ✅ Pedido {pedido_id} criado para {nome}")
#        else:
#            pedido_id = ultimo_pedido['id']
#            log.info(f"[WEBHOOK] 👤 Cliente existente: {nome} (Pedido #{pedido_id})")

        # Salvar mensagem no banco de dados
#        salvar_mensagem_pedido(
#            id_conversa,
#            pedido_id,
#            json.dumps(mensagem_whatsapp, ensure_ascii=False),
#            'recebida'
#        )

        # Enviar resposta automática
        resposta = responder_cliente(texto)
        enviar_mensagem_texto(mensagem_whatsapp, resposta)

        return "Webhook processado com sucesso!"

    except Exception as e:
        logger.error(f"[WEBHOOK] ❌ Erro ao processar webhook: {e}")
        import traceback
        traceback.print_exc()
        raise e
