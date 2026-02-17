"""
Módulo de segurança para validação de webhooks e autenticação.
"""
import os
import hmac
import hashlib
import logging
from functools import wraps
from flask import request, jsonify


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

    def validate_signature(self, payload: bytes = None) -> bool:
        """
        Valida a assinatura HMAC-SHA256 enviada pelo WhatsApp Business API
        no header X-Hub-Signature-256.

        Args:
            payload: Dados do payload (opcional, usa request.get_data() se não fornecido)

        Returns:
            bool: True se a assinatura for válida, False caso contrário
        """
        signature = request.headers.get('X-Hub-Signature-256', '')

        if not signature:
            return False

        # Remove o prefixo 'sha256=' da assinatura
        expected_signature = signature.replace('sha256=', '')

        # Obtém o payload
        if payload is None:
            payload = request.get_data()

        # Calcula o HMAC do payload usando o app_secret
        mac = hmac.new(
            self.app_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        )
        calculated_signature = mac.hexdigest()

        # Compara as assinaturas de forma segura
        return hmac.compare_digest(expected_signature, calculated_signature)

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
logger = logging.getLogger(__name__)

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
