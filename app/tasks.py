import json
import logging
import random
import time
from celery_app import celery_app
from whatsapp_orquestrador import recebe_webhook
from whatsapp import enviar_audio, marcar_como_lida, enviar_mensagem, enviar_mensagem_digitando, enviar_documento, enviar_imagem
from whatsapp_upload import receber_comprovante
from database import atualizar_estado_pedido, salvar_mensagem_pedido, atualizar_pedido_com_comprovante, atualizar_pedido_com_pagamento, atualizar_pedido_com_interesse_produto
from agente_vendas_sem_gluten import responder_cliente
from agente_valida_comprovante import validar_comprovante_com_ia

logger = logging.getLogger(__name__)

#TODO rever max_retries e countdown, para não ficar tentando para sempre em caso de erro persistente, e para não demorar muito para tentar novamente em caso de erro temporário
@celery_app.task(name="tasks.processar_webhook", bind=True, max_retries=0)
def processar_webhook(self, body):
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-WEBHOOK] 📦 Dados recebidos para processamento da mensagem webhook:  {body}")
        # ============================================================================================
        #processa a mensagem do webhook, que pode ser uma mensagem nova do cliente, ou uma resposta do cliente a uma mensagem enviada, ou outras interações. O processamento envolve extrair os dados relevantes da mensagem, identificar o pedido associado (se houver), determinar o fluxo de atendimento adequado (introdução, envio de produto, etc) e enfileirar a tarefa correspondente para cada fluxo.
        recebe_webhook(body)
        # ============================================================================================
        logger.info("[TASK-WEBHOOK] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[TASK] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.enviar_introducao", bind=True, max_retries=0)
def fluxo_enviar_introducao(self, pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-INTRODUCAO] 📦 Dados recebidos para introdução: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.info("[TASK-INTRODUCAO] 🎬 Iniciando fluxo de introdução...")
        # ============================================================================================
        #grava mensagem recebida
        pedido_id = pedido['id']
        mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        message_id_original = message_id
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        logger.info(f"[TASK-INTRODUCAO] 📥 Marcando mensagem como lida no WhatsApp do cliente...")
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        marcar_como_lida(message_id)
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.info(f"[TASK-INTRODUCAO] 🤖 Enviando status de digitando para o cliente...")
        enviar_mensagem_digitando(message_id)
        # ============================================================================================
        # Enviar áudio de introdução inicial, depois de um tempo de espera aleatório para simular o tempo que o atendente levaria para ler a mensagem e preparar a resposta. O áudio pode ser personalizado com base no produto ou campanha, ou pode ser um áudio genérico de boas-vindas e introdução.
        #TODO depois pegar pro produto
        delay = random.uniform(8, 10)
        logger.info(f"[TASK-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
        time.sleep(delay)
        url_audio_inicial = "https://lneditor.com.br/static/audios/introducao-paes.ogg"
        message_id = enviar_audio(pedido, url_audio=url_audio_inicial)
        #gravar mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_audio_inicial
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.info(f"[TASK-INTRODUCAO] 🤖 Enviando status de digitando 2 para o cliente...")
        enviar_mensagem_digitando(message_id_original)
        # ============================================================================================
        # Enviar áudio de introdução final
        delay = random.uniform(5.0, 8.0)
        logger.info(f"[TASK-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio explicativo...")
        time.sleep(delay)
        url_audio_explicativo = "https://lneditor.com.br/static/audios/introducao-explicativa-paes.ogg"
        message_id = enviar_audio(pedido, url_audio=url_audio_explicativo)
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_audio_explicativo
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.info(f"[TASK-INTRODUCAO] 🤖 Enviando status de digitando 3 para o cliente...")
        enviar_mensagem_digitando(message_id_original)
        # ============================================================================================
        #envia imagem complementar
        delay = random.uniform(5.0, 8.0)
        logger.info(f"[TASK-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar imagem complementar...")
        time.sleep(delay)
        url_imagem_complementar = "https://lneditor.com.br/static/images/paes-foto-semanal.jpg"
        message_id = enviar_imagem(pedido, url_imagem_complementar)
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_imagem_complementar
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.info(f"[TASK-INTRODUCAO] 🤖 Enviando status de digitando 4 para o cliente...")
        enviar_mensagem_digitando(message_id_original)
        # ============================================================================================
        # enviar mensagem de texto explicativa complementar, para reforçar a mensagem do áudio, e para ficar registrado no histórico do pedido o conteúdo da mensagem, para controle e para o caso de o cliente não ouvir o áudio
        delay = random.uniform(5.0, 8.0)
        logger.info(f"[TASK-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem explicativa complementar...")
        time.sleep(delay)
        msg_explicativa = """*Esses são alguns pães que fiz na última semana 😋*
        Posso te enviar o livrinho agora?"""
        message_id_resposta = enviar_mensagem(pedido, msg_explicativa)
        #grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = msg_explicativa
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # atualiza estado do pedido para 'introducao_enviada' (2) no banco de dados, para controlar o fluxo e histórico do pedido
        logger.info("[TASK-INTRODUCAO] ✅ atualizando estado do pedido como 'introducao_enviada' (2) no banco de dados...")
        atualizar_estado_pedido(pedido['id'], 2)
        # ============================================================================================
        logger.info("[TASK-INTRODUCAO] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[TASK-INTRODUCAO] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)

@celery_app.task(name="tasks.enviar_pedido", bind=True, max_retries=0)
def fluxo_enviar_pedido(self, pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-PEDIDO] 📦 Dados recebidos para pedido: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.info("[TASK-PEDIDO] 🎬 Iniciando fluxo de pedido...")
        # ============================================================================================
        #grava mensagem recebida
        logger.info(f"[TASK-PEDIDO] 📥 Gravando mensagem recebida no banco de dados...")
        pedido_id = pedido['id']
        mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        logger.info(f"[TASK-PEDIDO] 📥 Marcando mensagem como lida no WhatsApp do cliente...")
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        marcar_como_lida(message_id)
        # ============================================================================================
        #verifica se a mensagem é interessada ou não no produto
        logger.info(f"[TASK-PEDIDO] 📥 Mensagem marcada como lida: {mensagem}")
        mensagem_cliente = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        pergunta = f"""Você acabou de enviar no WhatsApp do cliente um audio com a descrição do produto e ela te respondeu a mensagem '{mensagem_cliente}'
        Pela mensagem dele, o cliente está demonstrando interesse no produto? Responda apenas com 'sim' ou 'não'.
            """
        interesse_positivo = responder_cliente(pergunta)
        # Limpar resposta do modelo (remover pontuação e espaços)
        interesse_positivo_limpo = interesse_positivo.strip().rstrip('.!?').lower()
        logger.info(f"[TASK-PEDIDO] 🤖 Feedback do modelo sobre interesse do cliente: {interesse_positivo} (limpo: {interesse_positivo_limpo})")
        # ============================================================================================
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.info(f"[TASK-PEDIDO] 🤖 Enviando status de digitando para o cliente...")
        enviar_mensagem_digitando(message_id)
        # ============================================================================================
        # envia mensagem do produto
        delay   = random.uniform(9.0, 12.0)
        logger.info(f"[TASK-PEDIDO] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem do produto...")
        time.sleep(delay)
        if interesse_positivo_limpo == 'sim':
            # ========================================================================================
            # atualiar interesse_produto como True no banco de dados, para controle e histórico do pedido
            logger.info(f"[TASK-PEDIDO] ✅ Atualizando interesse_produto como True no banco de dados...")
            atualizar_pedido_com_interesse_produto(pedido_id, True)
            # ========================================================================================
            logger.info(f"[TASK-PEDIDO] 🤖 Enviando mensagem do produto para o cliente...")
            msg_pedido_inicial = "Suas receitinhas estão aqui, é só clicar abaixo ⬇"
            message_id_resposta = enviar_mensagem(pedido, msg_pedido_inicial)
            # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = msg_pedido_inicial
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        else:
               # ========================================================================================
            # atualiar interesse_produto como False no banco de dados, para controle e histórico do pedido
            logger.info(f"[TASK-PEDIDO] ✅ Atualizando interesse_produto como False no banco de dados...")
            atualizar_pedido_com_interesse_produto(pedido_id, False)
            # ========================================================================================
            logger.info(f"[TASK-PEDIDO] 🤖 Enviando mensagem do produto para o cliente...")
            msg_pedido_inicial = "Queremos o seu melhor, então receba esse presente totalmente sem custo, é só clicar abaixo que é seu ⬇"
            message_id_resposta = enviar_mensagem(pedido, msg_pedido_inicial)
            # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = msg_pedido_inicial
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        #envia pdf do produto
        logger.info(f"[TASK-PEDIDO] 🤖 Enviando documento do produto para o cliente...")
        url_documento = "https://lneditor.com.br/static/arquivos/paes-sem-gluten.pdf"
        message_id_resposta = enviar_documento(pedido, url_documento=url_documento)
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = url_documento
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        delay = random.uniform(10, 15)
        logger.info(f"[TASK-INTRODUCAO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
        time.sleep(delay)

        if interesse_positivo_limpo == 'sim':
            # =======================================================================================
            logger.info(f"[TASK-PEDIDO] 🤖 Enviando mensagem de pedido entregue")
            url_audio_pedido_entregue = "https://lneditor.com.br/static/audios/paes-pedido-entregue.ogg"
            delay = random.uniform(2.0, 5.0)
            logger.info(f"[TASK-PEDIDO] ⏳ Aguardando {delay:.1f}s antes de enviar áudio inicial...")
            time.sleep(delay)
            message_id = enviar_audio(pedido, url_audio=url_audio_pedido_entregue)
            #gravar mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = url_audio_pedido_entregue
            salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='enviada')
        else:
            # ========================================================================================
            msg_pedido_entregue = "Se você gostou do presente, você pode nos ajudar ajudar com R$10,00 ou mais. Essa ajuda iré permitir que outras pessoas conheçam essas receitas sem glutén e possam ter uma vida mais gostosa e saudável também ❤️ Para contribuir, vou mandar os dados do Pix ⬇"
            message_id_resposta = enviar_mensagem(pedido, msg_pedido_entregue)
            # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = msg_pedido_entregue
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar dados do Pix para contribuição
        delay = random.uniform(5, 9)
        logger.info(f"[TASK-PEDIDO] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem de dados do Pix para contribuição...")
        time.sleep(delay)
        logger.info(f"[TASK-PEDIDO] 🤖 Enviando mensagem de dados do Pix para o cliente...")
        msg_contribuicao = """
            *Informações do PIX*:

        - 💸 *Valor*: R$10, 12, 15, 20
        - 📱 *Chave Pix* (e-mail): admin@lneditor.com.br
        - 👤 *Nome*: Leonardo Santos Negreiros

        Para facilitar, vou te enviar a chave Pix separada, assim é só copiar e colar:
        """
        message_id_resposta = enviar_mensagem(pedido, msg_contribuicao  )
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = msg_contribuicao
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar dados do Pix para contribuição
        logger.info(f"[TASK-PEDIDO] 🤖 Enviando mensagem de dados do Pix para o cliente...")
        msg_pix = "admin@lneditor.com.br"
        message_id_resposta = enviar_mensagem(pedido, msg_pix)
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = msg_pix
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        # enviar mensagem da surpresa se enviar comprovante
        logger.info(f"[TASK-PEDIDO] 🤖 Enviando mensagem de surpresa para o cliente...")
        msg_surpresa = "🎁 *Surpresinha especial* para quem realizar o pagamento e enviar o comprovante!"
        message_id_resposta = enviar_mensagem(pedido, msg_surpresa)
        mensagem = msg_surpresa
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        #atualiza estado do pedido para 'pedido_enviado' (3) no banco de dados, para controlar o fluxo e histórico do pedido
        logger.info("[TASK-PEDIDO] ✅ atualizando estado do pedido como 'pedido_enviado' (3) no banco de dados...")
        atualizar_estado_pedido(pedido_id, 3)
        # ============================================================================================
        logger.info("[TASK-PEDIDO] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[TASK-PEDIDO] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)

@celery_app.task(name="tasks.responder_mensagem", bind=True, max_retries=0)
def fluxo_responder_mensagem(self, pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-RESPONDER-MENSAGEM] 📦 Dados recebidos para responder mensagem: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.info("[TASK-RESPONDER-MENSAGEM] 🎬 Iniciando fluxo de responder mensagem...")
        # ============================================================================================
        #grava mensagem recebida
        pedido_id = pedido['id']
        mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        marcar_como_lida(message_id)
        # ============================================================================================
        # responder mensagem do cliente
        #verifica se a mensagem é interessada ou não no produto
        # TODO busca chave Pix pelo produto, para não ficar hardcodado
        logger.info(f"[TASK-RESPONDER-MENSAGEM] 📥 Mensagem marcada como lida: {mensagem}")
        mensagem_cliente = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        pergunta = f"""
            Role: Você é a Luiza, uma vendedora atenciosa e cordial. Sua missão é dar continuidade ao atendimento de um cliente no WhatsApp que já recebeu um áudio explicativo, o e-book (PDF), dados para pagamento e que ele receberá um e-book surpresa caso envie o comprovante de pagamento.
            Diretrizes de Resposta:
                Se o cliente mostrar interesse em pagar ou pedir o Pix: Forneça a chave Pix admin@lneditor.com.br e reforce que o valor mínimo sugerido é de R$ 10,00, mas ele pode contribuir com mais se desejar.
                Se o cliente enviar o comprovante (ou disser que pagou): Agradeça com entusiasmo e informe que está enviando o E-book Surpresa em instantes.
                Se o cliente pedir reembolso: Responda educadamente que a solicitação será analisada e que a equipe de suporte entrará em contato diretamente com ele em breve.
                Sobre o E-book: Se ele tiver dúvidas de como acessar, lembre-o que o arquivo PDF já está na conversa e basta clicar para abrir.

            Restrições:
                Responda de forma sucinta (formato WhatsApp).
                Use emojis moderadamente para ser amigável.
                Não adicione explicações extras para mim, responda apenas com a fala da Luiza.

            Pergunta do cliente: '{mensagem_cliente}'
            """
        resposta_cliente = responder_cliente(pergunta)
        # Limpar resposta do modelo (remover pontuação e espaços)
        logger.info(f"[TASK-RESPONDER-MENSAGEM] 🤖 Resposta do modelo sobre a pergunta: {resposta_cliente} ")
        # envia digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
        logger.info(f"[TASK-RESPONDER-MENSAGEM] 🤖 Enviando resposta para o cliente: {resposta_cliente}")
        enviar_mensagem_digitando(message_id)
        delay = random.uniform(5.0, 8.0)
        logger.info(f"[TASK-RESPONDER-MENSAGEM] ⏳ Aguardando {delay:.1f}s antes de enviar resposta para o cliente...")
        time.sleep(delay)
        message_id_resposta = enviar_mensagem(pedido, resposta_cliente)
        # grava mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
        mensagem = resposta_cliente
        salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # atualizar_estado_pedido(pedido['id'], 2)
        # ============================================================================================
        logger.info("[TASK-RESPONDER-MENSAGEM] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[TASK-RESPONDER-MENSAGEM] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.conferir_comprovante", bind=True, max_retries=0)
def fluxo_conferir_comprovante(self, pedido, mensagem_whatsapp):
    try:
        logger.info("=" * 120)
        logger.info(f"[TASK-CONFERIR-COMPROVANTE] 📦 Dados recebidos para responder mensagem: \n Pedido: {pedido},  \n Mensagem WhatsApp: {mensagem_whatsapp}")
        logger.info("[TASK-CONFERIR-COMPROVANTE] 🎬 Iniciando fluxo de conferir comprovante...")
        # ============================================================================================
        #grava mensagem recebida
        pedido_id = pedido['id']
        # mensagem = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['text']['body']
        message_id = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]['id']
        # salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        #marcar mensagem como lida, para não ficar com aquela notificação de mensagem nova no WhatsApp do cliente
        logger.info(f"[TASK-CONFERIR-COMPROVANTE] 📥 Marcando mensagem como lida no WhatsApp do cliente...")
        marcar_como_lida(message_id)
        # ============================================================================================
        # recuperar comprovante e persistir
        logger.info(f"[TASK-CONFERIR-COMPROVANTE] 📥 Recebendo comprovante enviado pelo cliente...")
        dados = mensagem_whatsapp['entry'][0]['changes'][0]['value']['messages'][0]
        tipo = dados['type'] # image
        if tipo == 'image':
            url = dados['image']['url']
            mime = dados['image']['mime_type']
            filename = None
        else:
            url = dados['document']['url']
            mime = dados['document']['mime_type']
            filename = dados['document']['filename']

        path_comprovante = receber_comprovante(tipo, url, mime, filename, pedido_id)
        # ============================================================================================
        # Salvar caminho do comprovante no banco de dados, associado ao pedido, para histórico e controle
        logger.info(f"[TASK-CONFERIR-COMPROVANTE] 📥 Atualizando pedido com caminho do comprovante no banco de dados...")
        atualizar_pedido_com_comprovante(pedido_id, path_comprovante)
        # ============================================================================================
        #salvar mensagem do comprovante recebido no banco de dados, associada ao pedido, para histórico e controle
        mensagem = f"Comprovante recebido: {filename}"
        salvar_mensagem_pedido(message_id, pedido_id, mensagem, tipo_mensagem='recebida')
        # ============================================================================================
        # validar comprovante com IA
        logger.info(f"[TASK-CONFERIR-COMPROVANTE] 📥 Validando comprovante com IA...")
        resultado_validacao_json = validar_comprovante_com_ia(path_comprovante)
        resultado_validacao = json.loads(resultado_validacao_json)
        logger.info(f"[TASK-CONFERIR-COMPROVANTE] 📥 Resultado da validação: {resultado_validacao}")
        if resultado_validacao['valido'] and resultado_validacao['destinatario_correto']:
            # =======================================================================================
            #salvar no banco de dados que o pedido foi pago, para controle e histórico
            logger.info(f"[TASK-CONFERIR-COMPROVANTE] 📥 Atualizando pedido com pagamento no banco de dados...")
            atualizar_pedido_com_pagamento(pedido_id, resultado_validacao['valor'])
            # =======================================================================================
            # enviar digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
            logger.info(f"[TASK-CONFERIR-COMPROVANTE] 🤖 Enviando digitando para o cliente...")
            enviar_mensagem_digitando(message_id)
            # =======================================================================================
            # enviar mensagem de confirmação de pagamento e entrega do e-book surpresa
            delay = random.uniform(5.0, 8.0)
            logger.info(f"[TASK-CONFERIR-COMPROVANTE] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem de confirmação de pagamento para o cliente...")
            time.sleep(delay)
            logger.info(f"[TASK-CONFERIR-COMPROVANTE] 🤖 Enviando mensagem de confirmação de pagamento para o cliente...")
            url_surpresa = "https://lneditor.com.br/static/audios/surpresa-pago.ogg"
            enviar_documento(pedido, url_documento="https://lneditor.com.br/static/arquivos/ebook-surpresa.pdf")
        else:
            # enviar digitando para o celular do cliente, para simular que o atendente está digitando uma resposta
            logger.info(f"[TASK-CONFERIR-COMPROVANTE] 🤖 Enviando digitando para o cliente...")
            enviar_mensagem_digitando(message_id)
            # =======================================================================================
            # enviar mensagem de comprovante inválido, e solicitar que envie um comprovante válido para receber o e-book surpresa
            delay = random.uniform(5.0, 8.0)
            logger.info(f"[TASK-CONFERIR-COMPROVANTE] ⏳ Aguardando {delay:.1f}s antes de enviar mensagem de comprovante inválido para o cliente...")
            time.sleep(delay)
            logger.info(f"[TASK-CONFERIR-COMPROVANTE] 🤖 Enviando mensagem de comprovante inválido para o cliente...")
            msg_comprovante_invalido = "O comprovante enviado não é válido. Por favor, verifique se o pagamento foi realizado corretamente, se o valor é igual ou superior a R$10,00 e se a chave Pix é correta "
            message_id_resposta = enviar_mensagem(pedido, msg_comprovante_invalido)
            # ============================================================================================
            # salva mensagem enviada no banco de dados, associada ao pedido, para histórico e controle
            mensagem = msg_comprovante_invalido
            salvar_mensagem_pedido(message_id_resposta, pedido_id, mensagem, tipo_mensagem='enviada')
        # ============================================================================================
        logger.info("[TASK-CONFERIR-COMPROVANTE] ✅ Mensagem processada com sucesso!")
        logger.info("=" * 120)

    except Exception as exc:
        logger.error(f"[TASK-CONFERIR-COMPROVANTE] ❌ Erro: {exc}. Tentativa {self.request.retries + 1} de {self.max_retries + 1}")
        logger.info("=" * 120)
        raise self.retry(exc=exc, countdown=30)
