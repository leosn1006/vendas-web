"""Configuração do SMS (lida do .env). Ver docs/SMS.md."""
import os


def _lista(nome):
    import re
    return {re.sub(r'\D', '', n) for n in os.getenv(nome, '').split(',') if re.sub(r'\D', '', n)}


ATIVO = os.getenv('SMS_ATIVO', '1') == '1'
# Chave da API nova da Comtele (header x-api-key). O nome da variável é o que já estava no .env.
COMTELE_CHAVE = os.getenv('CONTENT_SMS_API', '')
COMTELE_URL = os.getenv('SMS_COMTELE_URL', 'https://api.comtele.com.br/messages/sms/send')
COMTELE_ROTA = int(os.getenv('SMS_COMTELE_ROTA', '17') or 17)
# Segredo no caminho do webhook de entrega (a Comtele não assina o aviso). Vazio = webhook desligado.
WEBHOOK_SEGREDO = os.getenv('SMS_WEBHOOK_SEGREDO', '')
# Fora de produção, só estes números recebem SMS de verdade (com DDI, separados por vírgula); os demais vão para o log.
DEV_PERMITIDOS = _lista('SMS_DEV_PERMITIDOS')
CUSTO_UNITARIO = float(os.getenv('SMS_CUSTO_UNITARIO', '0.12') or 0.12)
