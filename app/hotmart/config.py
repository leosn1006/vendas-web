"""Configuração da Hotmart (lida do .env). Ver docs/HOTMART.md."""
import os

# Token secreto que a Hotmart manda no cabeçalho X-HOTMART-HOTTOK (painel → Ferramentas → Webhook). Vazio = webhook
# desligado (responde 404).
HOTTOK = os.getenv('HOTMART_HOTTOK', '')

# Dias entre a aprovação e o dinheiro ficar disponível para saque (estimativa da previsão de repasse; vendas em outra
# moeda: 15 dias, pela ajuda da Hotmart). A data real do saque não vem no webhook.
try:
    DIAS_REPASSE = int(os.getenv('HOTMART_DIAS_REPASSE', '15') or 15)
except ValueError:
    DIAS_REPASSE = 15

# API de vendas (conciliação): credencial de Ferramentas → Credenciais Developers. O tipo (produção ou sandbox) é
# escolhido na criação e não muda; a de sandbox recebe 403 em developers.hotmart.com. Vazio = conciliação desligada.
CLIENT_ID = os.getenv('HOTMART_CLIENT_ID', '')
CLIENT_SECRET = os.getenv('HOTMART_CLIENT_SECRET', '')
CLIENT_TOKEN = os.getenv('HOTMART_CLIENT_TOKEN', '')          # o "Basic ..." (com ou sem o prefixo)
API_URL = (os.getenv('HOTMART_API_URL', '') or 'https://developers.hotmart.com').rstrip('/')  # sandbox: https://sandbox.hotmart.com
URL_TOKEN = 'https://api-sec-vlc.hotmart.com/security/oauth/token'
try:
    DIAS_CONCILIACAO = int(os.getenv('HOTMART_DIAS_CONCILIACAO', '45') or 45)
except ValueError:
    DIAS_CONCILIACAO = 45

# Checkout da Hotmart (o link do botão da prévia): https://pay.hotmart.com/<produto_hotmart>?off=<oferta>&xcod=<guid>
URL_PAGAMENTO = (os.getenv('HOTMART_URL_PAGAMENTO', '') or 'https://pay.hotmart.com').rstrip('/')
