import logging
import os
from urllib.parse import urlparse, parse_qs
from agente_gera_mensagem_inicial import gera_mensagem_inicial_randomicamente
from flask import jsonify, request
from database import Pedido, criar_pedido, gravar_clique_pedido, selecionar_telefone_produto
from meta_clique import clique_meta, ip_e_navegador, registrar_campanha_meta

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FALLBACK_TELEFONE = {
    1: "556981058726",
    6: "556181256294",
    7: "556182364563",
    8: "556182412066",
    9: "556182402494",
    10: "556182410466",
    11: "556182419301",
    12: "556182419539",
}

def _gravar_clique_lead(pedido_id, fbc):
    """fbc, IP e navegador do lead. Uma falha aqui nunca impede a resposta com o número do WhatsApp."""
    try:
        ip, navegador = ip_e_navegador(request)
        gravar_clique_pedido(pedido_id, ip=ip, navegador=navegador, fbc=fbc)
    except Exception as e:
        logger.error(f"[LEAD] ❌ Erro ao gravar o clique do pedido #{pedido_id}: {e}")


def atribuicao_do_clique(body: dict) -> dict:
    """De onde veio o clique em "Quero receber": url da landing, domínio, gclid/wbraid/gbraid, campanha e o
    clique da Meta (`clique`: None ou {'campaignid', 'fbclid', 'fbc'}). Usado pelo lead do WhatsApp e pelo
    pedido da contribuição no site (web/contribuicao.py) — o mesmo clique, a mesma atribuição."""
    gclid = body.get('gclid', "") or ""
    url = body.get('url', "") or request.referrer or ""
    _qparams = parse_qs(urlparse(url).query)
    campaignid = body.get('campaignid', "") or ""
    clique = clique_meta({**{k: v[0] for k, v in _qparams.items()}, **({'gclid': gclid} if gclid else {})})
    if clique:
        campaignid = clique['campaignid']
    return {
        'url': url,
        'dns_origem': urlparse(url).netloc or None,
        'gclid': gclid,
        'wbraid': _qparams.get('wbraid', [''])[0],
        'gbraid': _qparams.get('gbraid', [''])[0],
        'campaignid': campaignid,
        'adgroupid': body.get('adgroupid', "") or "",
        'creative': body.get('creative', "") or "",
        'matchtype': body.get('matchtype', "") or "",
        'device': body.get('device', "") or "",
        'placement': body.get('placement', "") or "",
        'video_id': body.get('video_id', "") or "",
        'clique': clique,
    }


def persistir_lead(body):
    try:
        logger.info(f"[LEAD] 📦 Dados recebidos para criar lead: {body}")
        atrib = atribuicao_do_clique(body)
        url = atrib['url']
        clique = atrib['clique']
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
        elif "tempero" in url:
            produto = 11
        elif "fatia" in url:
            produto = 12
        else:
            produto = 1  # produto padrão para campanhas desconhecidas

        # logger.info(f"[LEAD] 🔍 URL recebida: '{url}' → produto determinado: {produto}")

        texto = gera_mensagem_inicial_randomicamente(produto)

        telefone = selecionar_telefone_produto(produto)
        if not telefone:
            logger.warning(f"[LEAD] ⚠️ Nenhum telefone cadastrado para produto {produto}, usando fallback")
        whatsapp_numero = telefone['telefone'] if telefone else FALLBACK_TELEFONE.get(produto, "")
        api_phone_id = telefone.get('api_phone_number_id') if telefone else None

        pedido = Pedido(
            produto_id=produto,
            valor_pago=0.00,
            estado_id=1,  # Estado Iniciado
            gclid=atrib['gclid'],
            wbraid=atrib['wbraid'],
            gbraid=atrib['gbraid'],
            data_ultima_atualizacao=None,
            mensagem_sugerida=texto,
            emoji_sugerida="",
            phone_number_id=api_phone_id or os.getenv('WHATSAPP_PHONE_NUMBER_ID', ''),
            contact_phone=None,
            contact_name=None,
            data_pedido=None,
            campaignid=atrib['campaignid'],
            adgroupid=atrib['adgroupid'],
            creative=atrib['creative'],
            matchtype=atrib['matchtype'],
            device=atrib['device'],
            placement=atrib['placement'],
            video_id=atrib['video_id'],
            dns_origem=atrib['dns_origem'],
        )
        pedido_id = criar_pedido(pedido)
        _gravar_clique_lead(pedido_id, clique['fbc'] if clique else None)
        from web.contribuicao import registrar_braco_wpp  # A/B da contribuição: este lead é do braço WhatsApp
        registrar_braco_wpp(pedido_id, produto)
        if clique:
            registrar_campanha_meta(produto, clique['campaignid'], venda_web=False)
        # logger.info(f"[LEAD] ✅ Lead gravado com gclid: {gclid}")
        resposta = {
            "whatsapp_numero": whatsapp_numero,
            "emojiEscolhido" : "",
            "mensagemBaseWA" : texto
        }
        # logger.info(f"[LEAD] ✅ Resposta gerada: {resposta}")
        return jsonify(resposta), 200
    except Exception as e:
        logger.exception(f"[LEAD] ❌ ERRO ao gravar lead: {e}")
        return jsonify({'error': 'Erro ao gravar lead'}), 500
