import logging
import os
from urllib.parse import urlparse
from agente_gera_mensagem_inicial import gera_mensagem_inicial_randomicamente
from flask import jsonify, request
from database import Pedido, criar_pedido, selecionar_telefone_produto

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FALLBACK_TELEFONE = {
    1: "556182155687",
    6: "556181256294",
    7: "556182364563",
    8: "556198824782",
    10: "556184022952",
}

def persistir_lead(body):
    try:
        logger.info(f"[LEAD] 📦 Dados recebidos para criar lead: {body}")
        gclid = body.get('gclid', "")
        url = body.get('url', "") or request.referrer or ""
        dns_origem = urlparse(url).netloc or None
        campaignid = body.get('campaignid', "")
        adgroupid = body.get('adgroupid', "")
        creative = body.get('creative', "")
        matchtype = body.get('matchtype', "")
        device = body.get('device', "")
        placement = body.get('placement', "")
        video_id = body.get('video_id', "")
        if "paes-sem-gluten" in url:
            produto = 1
        elif "pascoa-lucrativa" in url:
            produto = 6
        elif "pudim" in url:
            produto = 8
        elif "sobremesa" in url:
            produto = 9
        elif "bem-estar" in url:
            produto = 7
        elif "sem-acucar" in url:
            produto = 10
        else:
            produto = 1  # produto padrão para campanhas desconhecidas

        # logger.info(f"[LEAD] 🔍 URL recebida: '{url}' → produto determinado: {produto}")

        texto, emoji = gera_mensagem_inicial_randomicamente(produto)

        telefone = selecionar_telefone_produto(produto)
        if not telefone:
            logger.warning(f"[LEAD] ⚠️ Nenhum telefone cadastrado para produto {produto}, usando fallback")
        whatsapp_numero = telefone['telefone'] if telefone else FALLBACK_TELEFONE.get(produto, "")
        api_phone_id = telefone.get('api_phone_number_id') if telefone else None

        pedido = Pedido(
            produto_id=produto,
            valor_pago=0.00,
            estado_id=1,  # Estado Iniciado
            gclid=gclid,
            data_ultima_atualizacao=None,
            mensagem_sugerida=texto,
            emoji_sugerida=emoji,
            phone_number_id=api_phone_id or os.getenv('WHATSAPP_PHONE_NUMBER_ID', ''),
            contact_phone=None,
            contact_name=None,
            data_pedido=None,
            campaignid=campaignid,
            adgroupid=adgroupid,
            creative=creative,
            matchtype=matchtype,
            device=device,
            placement=placement,
            video_id=video_id,
            dns_origem=dns_origem,
        )
        criar_pedido(pedido)
        # logger.info(f"[LEAD] ✅ Lead gravado com gclid: {gclid}")
        resposta = {
            "whatsapp_numero": whatsapp_numero,
            "emojiEscolhido" : emoji,
            "mensagemBaseWA" : texto
        }
        # logger.info(f"[LEAD] ✅ Resposta gerada: {resposta}")
        return jsonify(resposta), 200
    except Exception as e:
        logger.exception(f"[LEAD] ❌ ERRO ao gravar lead: {e}")
        return jsonify({'error': 'Erro ao gravar lead'}), 500
