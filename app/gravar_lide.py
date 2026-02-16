import logging
from flask import jsonify
from database import Pedido, criar_pedido

logger = logging.getLogger(__name__)

def persistir_lide(body):
    try:
        # Por exemplo, extrair os dados do body e usar uma função do database.py para salvar
        gclide = body.get('gclid', "")
        url = body.get('url', "")
        campaignid = body.get('campaignid', "")
        adgroupid = body.get('adgroupid', "")
        creative = body.get('creative', "")
        matchtype = body.get('matchtype', "")
        device = body.get('device', "")
        placement = body.get('placement', "")
        video_id = body.get('video_id', "")
        # preeche o dict Pedido com os dados necessários
        pedido = Pedido(
            produto_id= 1,
            valor_pago=0.00,
            estado_id=1,  # Estado Iniciado
            gclid=gclide,
            data_ultima_atualizacao=None,
            mensagem_sugerida="Eu quero saber mais sobre este produto!",
            emoji_sugerida="🤓",
            phone_number_id=None,
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
        return jsonify({'message': 'Lide gravado com sucesso!'}), 200
    except Exception as e:
        logger.critical(f"[LIDE] ❌ ERRO ao gravar lide: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Erro ao gravar lide'}), 500
