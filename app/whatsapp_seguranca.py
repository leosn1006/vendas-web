"""
Módulo de segurança para validação de webhooks e autenticação.
"""
import os
import hmac
import hashlib
import json
import logging
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)


class WhatsAppSecurity:
    """
    Classe responsável pela validação de segurança do WhatsApp Business API.
    """

    def __init__(self):
        """
        Inicializa a classe com as credenciais do WhatsApp Business API.
        """
        self.verify_token = os.getenv('WHATSAPP_VERIFY_TOKEN', 'seu-verify-token-aqui')
        self.app_secret = os.getenv('WHATSAPP_APP_SECRET', 'seu-app-secret-aqui')
        self.access_token = os.getenv('WHATSAPP_ACCESS_TOKEN', '')

    # Mapa temporário: display_phone_number → nome da env var com o app_secret
    # Necessário quando cada número pertence a uma Meta App distinta (app secrets diferentes).
    _PHONE_SECRET_MAP = {
        '556182393719': 'WHATSAPP_APP_SECRET_LSN',
    }

    def _secret_para_payload(self, payload: bytes) -> str:
        """Retorna o WHATSAPP_APP_SECRET correto para o telefone do body."""
        try:
            body = json.loads(payload)
            phone = body['entry'][0]['changes'][0]['value']['metadata']['display_phone_number']
            env_key = self._PHONE_SECRET_MAP.get(phone)
            if env_key:
                secret = os.getenv(env_key)
                if secret:
                    return secret
                logger.warning(f"[WEBHOOK] ⚠️ {env_key} não definido no .env — usando secret padrão para {phone}")
        except Exception:
            pass  # body sem metadata (ex: challenge de verificação) — usa padrão
        return self.app_secret

    def validate_signature(self, payload: bytes = None) -> bool:
        """
        Valida a assinatura HMAC-SHA256 enviada pelo WhatsApp Business API
        no header X-Hub-Signature-256.
        Suporta múltiplas Meta Apps via _PHONE_SECRET_MAP.
        """
        signature = request.headers.get('X-Hub-Signature-256', '')
        if not signature:
            return False

        expected_signature = signature.replace('sha256=', '')

        if payload is None:
            payload = request.get_data()  # Flask cacheia — request.get_json() ainda funciona depois

        secret = self._secret_para_payload(payload)
        mac = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256)
        return hmac.compare_digest(expected_signature, mac.hexdigest())

    def validate_verify_token(self, token: str) -> bool:
        """
        Valida o token de verificação enviado pelo WhatsApp durante
        a configuração inicial do webhook.

        Args:
            token: Token recebido do WhatsApp

        Returns:
            bool: True se o token for válido, False caso contrário
        """
        return hmac.compare_digest(token, self.verify_token)

    def validate_webhook_verification(self, mode: str, token: str) -> bool:
        """
        Valida a requisição de verificação completa do webhook do WhatsApp.

        Args:
            mode: Modo da verificação (deve ser 'subscribe')
            token: Token de verificação

        Returns:
            bool: True se a verificação for válida, False caso contrário
        """
        return mode == 'subscribe' and self.validate_verify_token(token)

    def get_access_token(self) -> str:
        """
        Retorna o access token do WhatsApp Business API.

        Returns:
            str: Access token configurado
        """
        return self.access_token


# Instância global para uso nas rotas
whatsapp_security = WhatsAppSecurity()


# ============ DECORADORES ============

def validar_assinatura_whatsapp():
    """
    Decorador para validar assinatura HMAC-SHA256 do WhatsApp Business API.

    Uso:
        @app.post("/api/v1/webhook-whatsapp")
        @validar_assinatura_whatsapp()
        def webhook_receive():
            # seu código aqui

    Retorna 401 se a assinatura for inválida.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Valida a assinatura usando a instância global
            if not whatsapp_security.validate_signature():
                logger.critical('[WEBHOOK] ❌ Assinatura INVÁLIDA!')
                logger.critical(f'[WEBHOOK] Headers: {dict(request.headers)}')
                logger.critical(f'[WEBHOOK] Remote addr: {request.remote_addr}')
                return jsonify({
                    'error': 'Unauthorized',
                    'message': 'Assinatura inválida'
                }), 401

            logger.info("[WEBHOOK] ✅ Assinatura VÁLIDA!")

            # Se a validação passar, executa a função original
            return f(*args, **kwargs)

        return decorated_function
    return decorator
