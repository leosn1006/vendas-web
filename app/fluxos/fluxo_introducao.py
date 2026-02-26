import logging
import time
import random
from database import salvar_mensagem_pedido, atualizar_estado_pedido, get_produto_by_id
from whatsapp import enviar_audio, enviar_imagem, enviar_mensagem, enviar_mensagem_digitando, marcar_como_lida


logger = logging.getLogger(__name__)


def _campos_produto_faltando(produto: dict | None) -> list[str]:
    campos_obrigatorios = [
        'url_audio_introducao',
        'url_audio_explicativo',
        'url_imagem_complementar',
        'mensagem_introducao',
    ]

    if not produto:
        return campos_obrigatorios

    return [
        campo for campo in campos_obrigatorios
        if not str(produto.get(campo) or '').strip()
    ]

def executar(pedido, mensagem_whatsapp):
    try:
        logger.debug("[FLUXO-INTRODUCAO] 🎬 Iniciando fluxo de introdução...")
        produto = get_produto_by_id(pedido.get('produto_id'))
        campos_faltando = _campos_produto_faltando(produto)

        if campos_faltando:
            raise ValueError(
                f"[FLUXO-INTRODUCAO] Configuração do produto {pedido.get('produto_id')} incompleta. "
                f"Campos obrigatórios ausentes: {', '.join(campos_faltando)}"
            )

        url_audio_inicial = produto['url_audio_introducao']
        url_audio_explicativo = produto['url_audio_explicativo']
        url_imagem_complementar = produto['url_imagem_complementar']
        msg_explicativa = produto['mensagem_introducao']

        pedido_id = pedido['id']
        mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        message_id_original = message_id
        # ============================================================================================
        logger.debug(f"[FLUXO-INTRODUCAO] 📥 Recebida nova mensagem do cliente: {mensagem}")
        #grava mensagem recebida
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        logger.debug(f"[FLUXO-INTRODUCAO] 📥 Marcando mensagem como lida no WhatsApp do cliente...")
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        marcar_como_lida(message_id)
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-INTRODUCAO] 🤖 Enviando status de digitando para o cliente...")
        enviar_mensagem_digitando(message_id)
        # ============================================================================================
        # Enviar áudio de introdução inicial, parametrizado por produto
        delay = random.uniform(8, 10)
        logger.debug(f"[FLUXO-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
        time.sleep(delay)
        message_id = enviar_audio(pedido, url_audio=url_audio_inicial)
        # ============================================================================================
        #gravar mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        logger.debug(f"[FLUXO-INTRODUCAO] 💾 Salvando mensagem de áudio de introdução inicial no banco de dados...")
        mensagem = "Segue o audio com uma explicação inicial do produto"
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-INTRODUCAO] 🤖 Enviando status de digitando 2 para o cliente...")
        enviar_mensagem_digitando(message_id_original)
        # ============================================================================================
        # Enviar áudio de introdução final
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio explicativo...")
        time.sleep(delay)
        message_id = enviar_audio(pedido, url_audio=url_audio_explicativo)
        #============================================================================================
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = "Segue uma explicação detalhada do produto e seus diferenciais"
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-INTRODUCAO] 🤖 Enviando status de digitando 3 para o cliente...")
        enviar_mensagem_digitando(message_id_original)
        # ============================================================================================
        #envia imagem complementar
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar imagem complementar...")
        time.sleep(delay)
        message_id = enviar_imagem(pedido, url_imagem_complementar)
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = "Segue uma imagem complementar do produto"
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.debug(f"[FLUXO-INTRODUCAO] 🤖 Enviando status de digitando 4 para o cliente...")
        enviar_mensagem_digitando(message_id_original)
        # ============================================================================================
        # enviar mensagem de texto explicativa complementar, para reforçar a mensagem do áudio, e para ficar registrado no histórico do pedido o conteúdo da mensagem, para controle e para o caso de o cliente não ouvir o áudio
        delay = random.uniform(5.0, 8.0)
        logger.debug(f"[FLUXO-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem explicativa complementar...")
        time.sleep(delay)
        message_id_resposta = enviar_mensagem(pedido, msg_explicativa)
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = msg_explicativa
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # atualiza estado do pedido para 'introducao_enviada' (2) no banco de dados, para controlar o fluxo e histórico do pedido
        logger.debug("[FLUXO-INTRODUCAO] ✅ atualizando estado do pedido como 'introducao_enviada' (2) no banco de dados...")
        atualizar_estado_pedido(pedido['id'], 2)
        # ============================================================================================
        logger.debug("[FLUXO-INTRODUCAO] ✅ Mensagem processada com sucesso!")
        logger.debug("=" * 120)

    except Exception as exc:
        raise Exception(f"[FLUXO-INTRODUCAO] ❌ \n Erro: {exc}")
