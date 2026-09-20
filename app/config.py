import os
# url do Whatsapp Business API
# Override por env só para ambientes de teste/dev: apontar para um endereço morto (ex.: http://127.0.0.1:9/) impede que
# qualquer código deste processo alcance a API oficial da Meta. Vazio/ausente = Graph API, como sempre foi.
# Barra final garantida: os chamadores concatenam f"{WHATSAPP_API_URL}{id}/messages".
WHATSAPP_API_URL = (os.getenv('WHATSAPP_API_URL') or 'https://graph.facebook.com/v24.0').rstrip('/') + '/'
# Gateway WhatsApp Web (api-wpp-web): imita a Cloud API; usado por números com provedor='wpp_web'
# em telefones_produto. Vazio = nenhum número wpp_web pode enviar (falha explícita).
WPP_WEB_API_URL = os.getenv('WPP_WEB_API_URL', '')
# URL que o gateway chama para entregar as mensagens recebidas (webhook). O host precisa estar em
# WhatsAppSecurity._HOST_SECRET_MAP: dele sai o segredo que assina o webhook. Vazio = webhook do chip
# não é configurado pelo admin (fica por conta de `wpp chip webhook` / PATCH manual).
WPP_WEB_WEBHOOK_URL = os.getenv('WPP_WEB_WEBHOOK_URL', '')
WHATSAPP_NUMBER=["5561982155687"]
FLUXO_WHATSAPP = {'introducao': 1,
                  'envio_produto': 2,
                  'cobranca': 3,
                  'comprovante': 4,
                  'brinde': 5,
                  'agradecimento': 6,
                  'reclamação': 7,
                  'devolucao': 8
        }
