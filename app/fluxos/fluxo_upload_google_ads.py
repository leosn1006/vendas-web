import os
import logging
from datetime import datetime
from types import SimpleNamespace
from google.ads.googleads.client import GoogleAdsClient
from database import busca_vendas_pendentes_google, marcar_venda_como_enviada_ao_google_ads

logger = logging.getLogger(__name__)

def executar():
    logger.info("=" * 120)
    logger.info(f"[FLUXO-UPLOAD-GOOGLE-ADS] 🎬 Iniciando upload de conversões")

    # Recomendo carregar o cliente FORA do loop para performance
    client = GoogleAdsClient.load_from_storage("/app/google-ads.yaml")

    vendas = busca_vendas_pendentes_google()

    # Use o ID da SUBCONTA aqui
    customer_id = os.getenv("GOOGLE_ADS_SUBACCOUNT_ID") # ID da conta das campanhas
    conversion_action_id = os.getenv("GOOGLE_ADS_META_ID")  # Pegue o ID numérico no painel do Ads

    if not customer_id or not conversion_action_id:
        raise ValueError("Variáveis GOOGLE_ADS_SUBACCOUNT_ID e GOOGLE_ADS_META_ID são obrigatórias para upload no Google Ads")

    for venda in vendas:
        if isinstance(venda, dict):
            venda = SimpleNamespace(**venda)

        if isinstance(venda.data_pagamento, str):
            try:
                venda.data_pagamento = datetime.fromisoformat(venda.data_pagamento)
            except ValueError:
                venda.data_pagamento = datetime.strptime(venda.data_pagamento, "%Y-%m-%d %H:%M:%S")

        gclid = venda.gclid
        venda_id = venda.id

        # Garante o formato: 2023-10-27 14:30:00-03:00
        # Se sua data no banco já tiver timezone, o %z resolve.
        # Caso contrário, adicione manualmente o offset da sua região:
        conversion_date_time = venda.data_pagamento.strftime("%Y-%m-%d %H:%M:%S-03:00")
        VL_10 = 10.00 # valor fixo para não expor o valor real pago, por questões de privacidade e para evitar erros de formatação do valor na API do Google Ads, que pode causar falhas no upload da conversão. O ideal é configurar um valor padrão no produto ou campanha para usar nesse caso, para não precisar hardcodar esse valor no código.
        sucesso = enviar_gclid_ads(
            client,
            customer_id,
            conversion_action_id,
            gclid,
            conversion_date_time,
            #venda.valor_pago
            VL_10
        )

        if sucesso:
            marcar_venda_como_enviada_ao_google_ads(venda_id)

def enviar_gclid_ads(client, customer_id, conversion_action_id, gclid, conversion_date_time, conversion_value):
    service = client.get_service("ConversionUploadService")
    click_conversion = client.get_type("ClickConversion")

    # Monta o caminho obrigatório: customers/{customer_id}/conversionActions/{action_id}
    click_conversion.conversion_action = client.get_service("ConversionActionService").conversion_action_path(
        customer_id, conversion_action_id
    )

    click_conversion.gclid = gclid
    click_conversion.conversion_value = float(conversion_value)
    click_conversion.currency_code = "BRL"
    click_conversion.conversion_date_time = conversion_date_time

    request = client.get_type("UploadClickConversionsRequest")
    request.customer_id = customer_id
    request.conversions.append(click_conversion)
    request.partial_failure = True

    try:
        response = service.upload_click_conversions(request=request)

        # Como enviamos apenas 1 por vez, verificamos a primeira posição do resultado
        if response.partial_failure_error.code != 0:
            # Aqui ele pega erros como "GCLID muito recente" ou "expirado"
            logger.error(f"❌ Erro parcial no Google Ads: {response.partial_failure_error.message}")
            return False

        logger.info(f"✅ GCLID {gclid} enviado com sucesso!")
        return True

    except Exception as e:
        logger.error(f"💥 Erro crítico na chamada da API: {e}")
        return False
