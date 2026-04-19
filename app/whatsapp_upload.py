import os
import requests
import time
import logging
from datetime import datetime
from pathlib import Path
from config import WHATSAPP_API_URL

logger = logging.getLogger(__name__)

# Configurações de Segurança
EXTENSOES_PERMITIDAS = {'.pdf', '.jpg', '.jpeg', '.png', '.ogg', '.opus'}  # Extensões permitidas
MIMES_PERMITIDOS = {'application/pdf', 'image/jpeg', 'image/png', 'audio/ogg', 'audio/ogg; codecs=opus', 'audio/opus'}  # MIMEs permitidos
TAMANHO_MAX_MB = 25

def receber_comprovante(tipo_midia, url, mime_type, filename, pedido_id ):
    """
    Dados_whatsapp: dicionário contendo a chave 'document' ou 'image'
    pedido_id: ID do pedido no seu sistema
    access_token: Seu Token do WhatsApp Business API
    """
    logger.info(f"[WHATSAPP-UPLOAD] Iniciando processo de upload do comprovante: Tipo Mídia={tipo_midia}, URL={url}, MIME={mime_type}, Pedido ID={pedido_id}")
    access_token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')
    # 1. Extração segura dos dados do JSON do WhatsApp
    # tipo_midia = "document" if "document" in dados_whatsapp else "image"
    info = tipo_midia

    #url = info.get("url")
    mime_original = mime_type
    # Pega a extensão do filename original do zap
    if filename is not None:
        extensao_original = Path(filename).suffix.lower()
    else:
        extensao_original = None

    if not url or not mime_original:
        logger.error(f"[WHATSAPP-UPLOAD] ❌ Dados inválidos enviados pelo WhatsApp: URL={url}, MIME={mime_original}, Pedido ID={pedido_id}")
        return None

    # 2. Sanitização: Validação de Tipo (MIME e Extensão) (só vem nome do arquivo para documento, para imagem não vem nome do arquivo, então força extensão .jpg para imagens sem extensão)
    if mime_original not in MIMES_PERMITIDOS or (tipo_midia=='document' and extensao_original not in EXTENSOES_PERMITIDAS):
        logger.error(f"[WHATSAPP-UPLOAD] ❌  Tipo de arquivo não permitido: MIME={mime_original}, Extensão={extensao_original}, Pedido ID={pedido_id}")
        print(f"Bloqueado: Tipo de arquivo não permitido ({mime_original})")
        return None

    # 3. Preparação do Caminho (Estrutura: storage/comprovantes/ano/mes/dia/pedido_id_timestamp.extensão)
    base_path = Path(__file__).parent.absolute()
    agora = datetime.now()
    diretorio_destino = base_path / "storage" / "comprovantes" / str(agora.year) / f"{agora.month:02d}" / f"{agora.day:02d}"
    diretorio_destino.mkdir(parents=True, exist_ok=True)

    # 4. Nomeação Segura (Ignora o nome original do usuário para evitar ataques)
    # Se for imagem e não tiver extensão no nome, força .jpg
    extensao_final = extensao_original if extensao_original else (".pdf" if "pdf" in mime_original else ".jpg")
    timestamp = int(time.time())
    nome_arquivo = f"pedido_{pedido_id}_{timestamp}{extensao_final}"
    caminho_final = diretorio_destino / nome_arquivo

    try:
        logger.info(f"[WHATSAPP-UPLOAD] Iniciando download do comprovante: URL={url}, MIME={mime_original}, Pedido ID={pedido_id}")
        # 5. Download Seguro (Com Header de Autorização do Facebook/WhatsApp)
        headers = {"Authorization": f"Bearer {access_token}"}
        resposta = requests.get(url, headers=headers, stream=True, timeout=20)
        resposta.raise_for_status()

        # 6. Validação de Tamanho Real
        tamanho = int(resposta.headers.get('Content-Length', 0))
        if tamanho > TAMANHO_MAX_MB * 1024 * 1024:
            logger.error(f"[WHATSAPP-UPLOAD] ❌ Arquivo excede o limite de tamanho: Tamanho={tamanho} bytes, Pedido ID={pedido_id}")
            print("Arquivo excede o limite de tamanho.")
            return None

        # 7. Escrita no Disco
        logger.info(f"[WHATSAPP-UPLOAD] Iniciando escrita do comprovante no disco: Caminho={caminho_final}, Pedido ID={pedido_id}")
        with open(caminho_final, 'wb') as f:
            for chunk in resposta.iter_content(chunk_size=8192):
                f.write(chunk)

        # Retorna o path relativo para o MySQL
        logger.info(f"[WHATSAPP-UPLOAD] 📄 Comprovante salvo com sucesso: {caminho_final}")
        return str(caminho_final.relative_to(base_path))

    except Exception as e:
        logger.error(f"[WHATSAPP-UPLOAD] ❌ Erro ao processar o upload do comprovante: {e}")
        return None


def receber_audio(tipo_midia, id_audio, mime_type, pedido_id):
    logger.debug(f"[WHATSAPP-UPLOAD-AUDIO] Iniciando processo de upload do comprovante: Tipo Mídia={tipo_midia}, ID={id_audio}, MIME={mime_type}, Pedido ID={pedido_id}")
    access_token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')
    # 1. Extração segura dos dados do JSON do WhatsApp
    mime_original = mime_type

    if not id_audio or not mime_original:
        raise Exception(f"[WHATSAPP-UPLOAD-AUDIO] ❌ Dados inválidos para baixar áudio: ID={id_audio}, MIME={mime_original}, Pedido ID={pedido_id}")

    # 2. Sanitização: Validação de Tipo (MIME e Extensão) (só vem nome do arquivo para documento, para imagem não vem nome do arquivo, então força extensão .jpg para imagens sem extensão)
    if mime_original not in MIMES_PERMITIDOS:
        raise Exception(f"[WHATSAPP-UPLOAD-AUDIO] ❌  Tipo de arquivo não permitido: MIME={mime_original}, Pedido ID={pedido_id}")

    # 3. Preparação do Caminho (Estrutura: storage/comprovantes/ano/mes/dia/pedido_id_timestamp.extensão)
    base_path = Path(__file__).parent.absolute()
    agora = datetime.now()
    diretorio_destino = base_path / "storage" / "audios" / str(agora.year) / f"{agora.month:02d}" / f"{agora.day:02d}"
    diretorio_destino.mkdir(parents=True, exist_ok=True)

    # 4. Nomeação Segura (Ignora o nome original do usuário para evitar ataques)
    # WhatsApp envia áudios como .ogg (compativel com OpenAI Whisper)
    extensao_final = ".ogg"
    nome_arquivo = f"pedido_{pedido_id}_{id_audio}{extensao_final}"
    caminho_final = diretorio_destino / nome_arquivo

    try:
        logger.debug(f"[WHATSAPP-UPLOAD-AUDIO] Obtendo URL de download do áudio: ID={id_audio}, Pedido ID={pedido_id}")
        # 5. Primeiro obtém a URL de download do WhatsApp API
        url_metadata = f"{WHATSAPP_API_URL}{id_audio}"
        headers = {"Authorization": f"Bearer {access_token}"}
        resposta_metadata = requests.get(url_metadata, headers=headers, timeout=20)
        resposta_metadata.raise_for_status()

        # Extrai a URL real do arquivo de áudio
        metadata = resposta_metadata.json()
        url_download = metadata.get('url')

        if not url_download:
            raise Exception(f"[WHATSAPP-UPLOAD-AUDIO] ❌ URL de download não encontrada na resposta da API: {metadata}")

        logger.debug(f"[WHATSAPP-UPLOAD-AUDIO] Iniciando download do áudio: URL={url_download}, Pedido ID={pedido_id}")
        # 6. Agora faz o download do arquivo
        resposta = requests.get(url_download, headers=headers, stream=True, timeout=20)
        resposta.raise_for_status()

        # 7. Escrita no Disco
        logger.debug(f"[WHATSAPP-UPLOAD-AUDIO] Iniciando escrita do comprovante no disco: Caminho={caminho_final}, Pedido ID={pedido_id}")
        with open(caminho_final, 'wb') as f:
            for chunk in resposta.iter_content(chunk_size=8192):
                f.write(chunk)

        # Retorna o path relativo para o MySQL
        logger.debug(f"[WHATSAPP-UPLOAD-AUDIO] 🎤 Audio salvo com sucesso: {caminho_final}")
        return str(caminho_final.relative_to(base_path))

    except Exception as e:
        raise Exception(f"[WHATSAPP-UPLOAD-AUDIO] ❌ Erro ao processar o upload do audio: {e}")
