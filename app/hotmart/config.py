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
