import os
import logging
import base64
import io
from pathlib import Path
from openai import OpenAI
from pdf2image import convert_from_path
from PIL import Image

client = OpenAI()
logger = logging.getLogger(__name__)

def validar_comprovante_com_ia(caminho_arquivo):
    try:
        # Converte caminho relativo para absoluto (o path vem como "storage/comprovantes/...")
        if not Path(caminho_arquivo).is_absolute():
            base_path = Path(__file__).parent.absolute()  # /app
            caminho_arquivo = str(base_path / caminho_arquivo)

        logger.info(f"[AGENTE_COMPROVANTE] Iniciando leitura do arquivo para validação: {caminho_arquivo}")

        # 1. Identifica a extensão do arquivo
        ext = Path(caminho_arquivo).suffix.lower()

        # 2. Converte para imagem (se for PDF) ou lê diretamente
        if ext == ".pdf":
            logger.info(f"[AGENTE_COMPROVANTE] Convertendo PDF para imagem...")
            # Converte a primeira página do PDF para imagem
            images = convert_from_path(caminho_arquivo, first_page=1, last_page=1, dpi=200)
            image = images[0]

            # Converte a imagem PIL para base64
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            base64_data = base64.b64encode(buffered.getvalue()).decode('utf-8')
            mime_type = "image/png"
        elif ext in [".jpg", ".jpeg", ".png"]:
            # Lê a imagem diretamente
            with open(caminho_arquivo, "rb") as f:
                base64_data = base64.b64encode(f.read()).decode('utf-8')

            if ext in [".jpg", ".jpeg"]:
                mime_type = "image/jpeg"
            else:
                mime_type = "image/png"
        else:
            raise ValueError(f"Formato de arquivo não suportado: {ext}")

        # 3. Prompt de validação rigorosa
        prompt_sistema = (
            "Você é um assistente de automação comercial responsável por validar comprovantes de pagamento PIX "
            "recebidos de clientes que compraram produtos digitais. Sua função é extrair informações do comprovante "
            "para confirmar se o pagamento foi concluído corretamente. Esta é uma operação legítima de verificação "
            "comercial para liberação de produtos digitais."
        )

        prompt_usuario = (
            "Analise este comprovante de pagamento PIX e extraia as seguintes informações:\n\n"
            "1. Nome do destinatário\n\n"
            "2. Valor transação (remova R$)\n\n"
            "3. Nome do banco pagador (Se possível extrair)\n\n"
            "4. Nome do pagador do pagador (Se possível extrair)\n\n"
            "5. Data do pagamento (Se possível extrair)\n\n"
            "6. Responda em JSON com este formato exato:\n\n"
            '{  "destinatario": "nome do destinatario", "valor": 0.0, "nome_banco": "nome do banco", "nome_pagador": "nome do pagador", "data_pagamento": "YYYY-MM-DD HH:MM:SS" }\n\n'
        )

        # 4. Envio para a API do OpenAI com a imagem em base64
        logger.info(f"[AGENTE_COMPROVANTE] Enviando imagem para validação com IA: Tipo={mime_type}, Original={ext}")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": prompt_sistema
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_usuario},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_data}"
                            }
                        }
                    ]
                }
            ],
            response_format={ "type": "json_object" }
        )

        logger.info(f"[AGENTE_COMPROVANTE] Response recebido - Finish reason: {response.choices[0].finish_reason}")

        # Verifica se houve refusal da OpenAI
        refusal = getattr(response.choices[0].message, 'refusal', None)
        if refusal:
            logger.warning(f"[AGENTE_COMPROVANTE] ⚠️ OpenAI recusou processar: {refusal}")
            return '{"recusado": true, "valor": 0.0, "destinatario": "", "motivo": "Sistema de validação recusou processar o comprovante"}'

        resposta = response.choices[0].message.content

        if not resposta:
            logger.warning(f"[AGENTE_COMPROVANTE] ⚠️ Resposta vazia da API. Finish reason: {response.choices[0].finish_reason}")
            return '{"recusado": true, "valor": 0.0, "destinatario": "", "motivo": "Erro ao processar imagem - resposta vazia da IA"}'

        logger.info(f"[AGENTE_COMPROVANTE] ✅ Resposta gerada: {resposta}")
        return resposta

    except Exception as e:
        logger.error(f"[AGENTE_COMPROVANTE] ❌ Erro ao processar mensagem: {e}")
        import traceback
        traceback.print_exc()
        return '{"recusado": true, "valor": 0.0, "destinatario": "", "motivo": "Erro técnico ao validar comprovante"}'
