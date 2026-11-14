"""Webhook de entrega da Comtele: POST /sms/comtele/status/<segredo> (configurado no painel deles). A Comtele não
assina o aviso: o segredo no caminho (SMS_WEBHOOK_SEGREDO) é a proteção."""
import hmac
import logging

from flask import Blueprint, abort, request

from sms import config, servico

logger = logging.getLogger(__name__)
bp = Blueprint('sms', __name__)


@bp.post('/sms/comtele/status/<segredo>')
def status_comtele(segredo):
    if not config.WEBHOOK_SEGREDO or not hmac.compare_digest(segredo, config.WEBHOOK_SEGREDO):
        abort(404)
    dados = request.get_json(silent=True)
    if dados is None:
        dados = request.form.to_dict()
    for aviso in (dados if isinstance(dados, list) else [dados]):
        try:
            if isinstance(aviso, dict):
                servico.registrar_entrega(aviso)
        except Exception:
            logger.exception(f'[SMS] Falha ao aplicar o aviso de entrega {aviso}')
    return '', 200
