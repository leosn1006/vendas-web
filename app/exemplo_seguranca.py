"""
Exemplos de uso da classe WhatsAppSecurity.

Este arquivo demonstra como usar a classe de segurança
de forma independente ou em testes.
"""
from seguranca import WhatsAppSecurity
import hmac
import hashlib


def exemplo_validacao_manual():
    """
    Exemplo de como usar a classe WhatsAppSecurity manualmente.
    Útil para testes ou uso fora do contexto Flask.
    """
    # Inicializa a classe de segurança
    security = WhatsAppSecurity()

    # Exemplo 1: Validar token de verificação
    print("=== Exemplo 1: Validação de Token ===")
    token_recebido = "meu-token-secreto"
    is_valid = security.validate_verify_token(token_recebido)
    print(f"Token válido: {is_valid}")

    # Exemplo 2: Validar verificação completa do webhook
    print("\n=== Exemplo 2: Validação de Webhook ===")
    mode = "subscribe"
    token = security.verify_token
    is_valid = security.validate_webhook_verification(mode, token)
    print(f"Verificação válida: {is_valid}")

    # Exemplo 3: Calcular assinatura HMAC manualmente
    print("\n=== Exemplo 3: Cálculo de Assinatura HMAC ===")
    payload = b'{"test": "data"}'
    app_secret = security.app_secret

    mac = hmac.new(
        app_secret.encode('utf-8'),
        payload,
        hashlib.sha256
    )
    signature = mac.hexdigest()
    print(f"Assinatura calculada: sha256={signature}")

    # Exemplo 4: Obter access token
    print("\n=== Exemplo 4: Access Token ===")
    access_token = security.get_access_token()
    print(f"Access Token length: {len(access_token)}")


def exemplo_teste_unitario():
    """
    Exemplo de como criar testes unitários para a classe.
    """
    import unittest

    class TestWhatsAppSecurity(unittest.TestCase):

        def setUp(self):
            """Inicializa a classe antes de cada teste."""
            self.security = WhatsAppSecurity()

        def test_validate_verify_token_success(self):
            """Testa se um token válido é aceito."""
            token = self.security.verify_token
            self.assertTrue(self.security.validate_verify_token(token))

        def test_validate_verify_token_failure(self):
            """Testa se um token inválido é rejeitado."""
            invalid_token = "token-invalido"
            self.assertFalse(self.security.validate_verify_token(invalid_token))

        def test_validate_webhook_verification_success(self):
            """Testa validação completa do webhook."""
            mode = "subscribe"
            token = self.security.verify_token
            self.assertTrue(
                self.security.validate_webhook_verification(mode, token)
            )

        def test_validate_webhook_verification_wrong_mode(self):
            """Testa rejeição de modo incorreto."""
            mode = "unsubscribe"
            token = self.security.verify_token
            self.assertFalse(
                self.security.validate_webhook_verification(mode, token)
            )

    # Executar testes
    print("\n=== Executando Testes Unitários ===")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestWhatsAppSecurity)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


if __name__ == "__main__":
    print("WhatsAppSecurity - Exemplos de Uso\n")

    # Executa os exemplos
    exemplo_validacao_manual()

    # Executa testes (comentado por padrão)
    # exemplo_teste_unitario()

    print("\n✅ Exemplos executados com sucesso!")
    print("\nPara usar em produção, importe diretamente:")
    print("  from seguranca import whatsapp_security")
    print("  whatsapp_security.validate_signature()")
