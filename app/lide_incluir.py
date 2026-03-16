import logging
import os
from agente_gera_mensagem_inicial import gera_mensagem_inicial_randomicamente
from flask import jsonify, request
from database import Pedido, criar_pedido, listar_telefones_produto

logger = logging.getLogger(__name__)

def persistir_lide(body):
    try:
        logger.info(f"[LIDE] 📦 Dados recebidos para criar lide: {body}")
        # Por exemplo, extrair os dados do body e usar uma função do database.py para salvar
        gclide = body.get('gclid', "")
        url = body.get('url', "") or request.referrer or ""
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
        else:
            produto = 1  # produto padrão para campanhas desconhecidas, pode ser ajustado para criar regras específicas por URL ou campanha

        logger.info(f"[LIDE] 🔍 URL recebida: '{url}' → produto determinado: {produto}")

        texto, emoji = gera_mensagem_inicial_randomicamente(produto)

        telefones = listar_telefones_produto(produto)
        whatsapp_numero = telefones[0]['telefone'] if telefones else "5561982155687"
        api_phone_id = telefones[0].get('api_phone_number_id') if telefones else None

        # preeche o dict Pedido com os dados necessários
        pedido = Pedido(
            produto_id=produto,
            valor_pago=0.00,
            estado_id=1,  # Estado Iniciado
            gclid=gclide,
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
            video_id=video_id
        )
        criar_pedido(pedido)
        print(f"[LIDE] ✅ Lide gravado com gclid: {gclide}")
        resposta = {
            "whatsapp_numero": whatsapp_numero,
            "emojiEscolhido" : emoji,
            "mensagemBaseWA" : texto
        }
        print(f"[LIDE] ✅ Resposta gerada: {resposta}")
        return jsonify(resposta), 200
    except Exception as e:
        logger.critical(f"[LIDE] ❌ ERRO ao gravar lide: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Erro ao gravar lide'}), 500
