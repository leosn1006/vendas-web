"""
Módulo de segurança para validação de webhooks e autenticação.
"""
import os
import hmac
import hashlib
import logging
from functools import wraps
from flask import request, jsonify, has_request_context

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

    # Cada Meta App tem uma URL de webhook num domínio distinto.
    # O Host header (definido pelo nginx) identifica a Meta App que enviou a requisição.
    # Domínios não mapeados são rejeitados explicitamente — sem fallback silencioso.
    _HOST_SECRET_MAP = {
        'lneditor.com.br': 'WHATSAPP_APP_SECRET',
        'lsnlivros.com.br': 'WHATSAPP_APP_SECRET_LSN',
        'lssolucoesdigitais.com.br': 'WHATSAPP_APP_SECRET_LSSD',
        'rc-livros.com.br': 'WHATSAPP_APP_SECRET_RC',
        'lclivros.com.br': 'WHATSAPP_APP_SECRET_LC',
        'lsdigitalsolucoes.com.br': 'WHATSAPP_APP_SECRET_LSDS',
        'kpnlivros.com.br': 'WHATSAPP_APP_SECRET_KPN',
        'ju-livros.com.br': 'WHATSAPP_APP_SECRET_JU',
    }

    _HOST_ACCESS_TOKEN_MAP = {
        'lneditor.com.br': 'WHATSAPP_ACCESS_TOKEN',
        'lsnlivros.com.br': 'WHATSAPP_ACCESS_TOKEN_LSN',
        'lssolucoesdigitais.com.br': 'WHATSAPP_ACCESS_TOKEN_LSSD',
        'rc-livros.com.br': 'WHATSAPP_ACCESS_TOKEN_RC',
        'lclivros.com.br': 'WHATSAPP_ACCESS_TOKEN_LC',
        'lsdigitalsolucoes.com.br': 'WHATSAPP_ACCESS_TOKEN_LSDS',
        'kpnlivros.com.br': 'WHATSAPP_ACCESS_TOKEN_KPN',
        'ju-livros.com.br': 'WHATSAPP_ACCESS_TOKEN_JU',
    }

    def _secret_para_payload(self) -> str:
        """Retorna o WHATSAPP_APP_SECRET correto para o domínio da requisição."""
        host = request.host.split(':')[0].lower()
        env_key = self._HOST_SECRET_MAP.get(host)
        if not env_key:
            logger.error(f"[WEBHOOK] ❌ Host '{host}' não mapeado em _HOST_SECRET_MAP — rejeitar requisição")
            return ''
        secret = os.getenv(env_key)
        if not secret:
            logger.error(f"[WEBHOOK] ❌ {env_key} não definido no .env para host '{host}' — rejeitar requisição")
            return ''
        logger.info(f"[WEBHOOK] 🔑 Usando {env_key} para host {host}")
        return secret

    def validate_signature(self, payload: bytes = None) -> bool:
        """
        Valida a assinatura HMAC-SHA256 enviada pelo WhatsApp Business API
        no header X-Hub-Signature-256.
        Suporta múltiplas Meta Apps via _HOST_SECRET_MAP (por domínio) e _PHONE_SECRET_MAP (fallback por telefone).
        """
        signature = request.headers.get('X-Hub-Signature-256', '')
        if not signature:
            return False

        expected_signature = signature.replace('sha256=', '')

        if payload is None:
            payload = request.get_data()  # Flask cacheia — request.get_json() ainda funciona depois

        secret = self._secret_para_payload()
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
        if not has_request_context():
            return self.access_token

        host = request.host.split(':')[0].lower()
        env_key = self._HOST_ACCESS_TOKEN_MAP.get(host)
        if not env_key:
            logger.error(f"[WEBHOOK] ❌ Host '{host}' não mapeado em _HOST_ACCESS_TOKEN_MAP — rejeitar requisição")
            return ''

        token = os.getenv(env_key, '')
        if not token:
            logger.error(f"[WEBHOOK] ❌ {env_key} não definido no .env para host '{host}' — rejeitar requisição")
            return ''
        return token


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
