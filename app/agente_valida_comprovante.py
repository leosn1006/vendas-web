import os
import logging
import base64
from pathlib import Path
from openai import OpenAI

client = OpenAI()
logger = logging.getLogger(__name__)

def validar_comprovante_com_ia(caminho_arquivo):
    logger.info
    try:
        # 1. Lê o arquivo e converte para Base64
        logger.info(f"[AGENTE_COMPROVANTE] Iniciando leitura do arquivo para validação: {caminho_arquivo}")
        with open(caminho_arquivo, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode('utf-8')

        # 2. Identifica o MIME Type automaticamente
        ext = Path(caminho_arquivo).suffix.lower()
        if ext == ".pdf":
            mime_type = "application/pdf"
        elif ext in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif ext == ".png":
            mime_type = "image/png"
        else:
            mime_type = "application/octet-stream"

            apikey = os.getenv('OPENAI_API_KEY', '')

        # 3. Prompt de validação rigorosa
        prompt_texto = (
            "Analise este comprovante de Pix. "
            "Dados Obrigatórios: Destinatário deve ser 'Leonardo Santos Negreiros'. "
            "Status: Deve ser 'Concluído' ou 'Sucesso'. Rejeite agendamentos. "
            "Responda estritamente em JSON com este formato: "
            "{'valido': true/false, 'valor': float, 'destinatario_correto': true/false, 'motivo': 'motivo se falso'}"
        )

        # 4. Envio para a API do OpenAI com o arquivo como input multimodal
        # Nota: Para PDFs, a estrutura usa o campo 'input_file' ou similar dependendo da versão da lib
        # Abaixo formato padrão para multimodais:
        logger.info(f"[AGENTE_COMPROVANTE] Enviando arquivo para validação com IA: Tipo Mídia={mime_type}, Extensão={ext}, Pedido ID={caminho_arquivo}  ")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_texto},
                        {
                            "type": "image_url" if ext != ".pdf" else "file_input",
                            "image_url" if ext != ".pdf" else "file": {
                                "url" if ext != ".pdf" else "data": f"data:{mime_type};base64,{base64_data}"
                            }
                        }
                    ]
                }
            ],
            response_format={ "type": "json_object" }
        )
        resposta = response.choices[0].message.content
        logger.info(f"[AGENTE_COMPROVANTE] ✅ Resposta gerada: {resposta[:50]}...")
        return resposta

    except Exception as e:
        logger.error(f"[AGENTE_COMPROVANTE] ❌ Erro ao processar mensagem: {e}")
        import traceback
        traceback.print_exc()
        return "Desculpe, estou com dificuldades técnicas no momento. Por favor, tente novamente em alguns instantes. 🙏"
