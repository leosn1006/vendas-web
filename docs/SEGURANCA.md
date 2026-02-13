# 🔒 Módulo de Segurança - WhatsApp Business API

## 📁 Estrutura

```
app/
├── app.py              # Rotas principais (limpo, sem lógica de segurança)
├── seguranca.py        # Classe WhatsAppSecurity (toda lógica de validação)
├── exemplo_seguranca.py # Exemplos de uso e testes
└── webhook_whatsApp.py # Lógica de processamento de mensagens
```

## 🎯 Objetivo

Separar a **lógica de segurança** da **lógica de rotas** para:
- ✅ Código mais limpo e organizado
- ✅ Fácil manutenção e testes
- ✅ Reutilização em outros módulos
- ✅ Escalabilidade (adicionar novas validações facilmente)

## 📝 Uso Básico

### 1. Validação em Rotas Flask

```python
from seguranca import whatsapp_security

@app.post("/api/v1/webhook-whatsapp")
def webhook_receive():
    # Valida assinatura HMAC-SHA256
    if not whatsapp_security.validate_signature():
        return jsonify({'error': 'Unauthorized'}), 401

    # Processa a mensagem
    return processo_mensagem()
```

### 2. Validação Manual (fora do Flask)

```python
from seguranca import WhatsAppSecurity

security = WhatsAppSecurity()

# Valida token
is_valid = security.validate_verify_token(token)

# Valida verificação do webhook
is_valid = security.validate_webhook_verification(mode, token)
```

## 🔧 Métodos Disponíveis

### `WhatsAppSecurity`

#### `validate_signature(payload=None) -> bool`
Valida a assinatura HMAC-SHA256 do WhatsApp.
- **Parâmetro**: `payload` (opcional, usa `request.get_data()` se não fornecido)
- **Retorna**: `True` se válido, `False` caso contrário

#### `validate_verify_token(token: str) -> bool`
Valida o token de verificação.
- **Parâmetro**: `token` - Token recebido do WhatsApp
- **Retorna**: `True` se válido, `False` caso contrário

#### `validate_webhook_verification(mode: str, token: str) -> bool`
Valida a requisição completa de verificação do webhook.
- **Parâmetros**:
  - `mode` - Deve ser "subscribe"
  - `token` - Token de verificação
- **Retorna**: `True` se válido, `False` caso contrário

#### `get_access_token() -> str`
Retorna o access token configurado.
- **Retorna**: String com o access token

## 🧪 Testes

Execute os exemplos:
```bash
cd app
python exemplo_seguranca.py
```

Ou integre com seu framework de testes:
```python
import unittest
from seguranca import WhatsAppSecurity

class TestSecurity(unittest.TestCase):
    def setUp(self):
        self.security = WhatsAppSecurity()

    def test_token_validation(self):
        self.assertTrue(
            self.security.validate_verify_token(self.security.verify_token)
        )
```

## 🔐 Variáveis de Ambiente

Configure no arquivo `.env`:

```env
WHATSAPP_VERIFY_TOKEN=seu-token-personalizado
WHATSAPP_APP_SECRET=seu-app-secret-do-meta
WHATSAPP_ACCESS_TOKEN=seu-access-token-do-meta
```

## 🚀 Expandindo o Módulo

Facilmente adicione novas funcionalidades de segurança:

```python
class WhatsAppSecurity:
    # ... métodos existentes ...

    def validate_rate_limit(self, user_id: str) -> bool:
        """Nova validação: rate limiting"""
        pass

    def validate_ip_whitelist(self, ip: str) -> bool:
        """Nova validação: whitelist de IPs"""
        pass

    def log_security_event(self, event: str):
        """Nova funcionalidade: logging de eventos"""
        pass
```

## 📚 Documentação Relacionada

- [WEBHOOK_WHATSAPP.md](../WEBHOOK_WHATSAPP.md) - Configuração completa do webhook
- [.env.example](../.env.example) - Template de variáveis de ambiente
- [WhatsApp Business API Docs](https://developers.facebook.com/docs/whatsapp)

---

**Mantido por**: Equipe de Desenvolvimento
**Última atualização**: Fevereiro 2026
