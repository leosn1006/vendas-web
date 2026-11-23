"""Webhook da Hotmart: POST /hotmart/webhook (cadastrado no painel da Hotmart, versão 2.0.0). A Hotmart não assina o
corpo: a proteção é o hottok no cabeçalho X-HOTMART-HOTTOK (HOTMART_HOTTOK no .env)."""
import hmac
import logging

from flask import Blueprint, abort, jsonify, request

from hotmart import config, servico

logger = logging.getLogger(__name__)
bp = Blueprint('hotmart', __name__)


@bp.post('/hotmart/webhook')
def webhook():
    if not config.HOTTOK:
        abort(404)
    if not hmac.compare_digest(request.headers.get('X-HOTMART-HOTTOK', ''), config.HOTTOK):
        logger.warning(f'[HOTMART] ⚠️ Webhook com hottok inválido (IP {request.remote_addr})')
        return jsonify(ok=False), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, erro='JSON inválido'), 400
    try:
        resultado = servico.processar(payload)
    except Exception:
        logger.exception('[HOTMART] ❌ Erro ao processar o aviso — a Hotmart vai reenviar')
        return jsonify(ok=False), 500
    return jsonify(ok=True, resultado=resultado), 200
