"""
Follow-up por e-mail do checkout web: pedidos com QR Pix gerado (estado 1002) que não
foram pagos em 1h, e ainda dentro da janela de validade do QR (24h).

Fluxo:
  1. Busca pedidos elegíveis (estado 1002, e-mail cadastrado, QR ainda válido,
     followup ainda não enviado)
  2. Para cada um, monta e-mail fixo com os bônus/bumps escolhidos, o QR code
     anexado inline (cid:) e um botão para pagar direto pelo site do Banco do Brasil
  3. Envia via Gmail API (mesmo helper do e-mail de entrega)
  4. Marca data_followup_pagamento_web no pedido
"""

import base64
import html
import logging
import os

import database as db
from fluxos._email_gmail import enviar as _enviar_gmail, lighten_hex as _lighten_hex
from web.checkout import _gerar_qrcode_base64

_QR_CID = 'qrcode-pix-followup'

logger = logging.getLogger(__name__)

_TAG = "FLUXO-FOLLOWUP-WEB"


def executar():
    logger.info("=" * 120)
    logger.info(f"[{_TAG}] 🕐 Iniciando verificação de followup de pagamento web")

    pedidos = db.buscar_pedidos_followup_pagamento_web(minutos_sem_atualizacao=60)

    if not pedidos:
        logger.info(f"[{_TAG}] ℹ️ Nenhum pedido pendente de followup.")
        logger.info("=" * 120)
        return

    logger.info(f"[{_TAG}] 📋 {len(pedidos)} pedido(s) para followup.")

    for pedido in pedidos:
        pedido_id = pedido['id']
        try:
            _enviar_followup(pedido)
            db.marcar_followup_pagamento_web_enviado(pedido_id)
            logger.info(f"[{_TAG}] ✅ Followup enviado para pedido #{pedido_id}.")
        except Exception as e:
            # Erro em um pedido não deve travar o envio dos demais da rodada —
            # o próprio pedido continua elegível e será retentado na próxima varredura.
            logger.error(f"[{_TAG}] ❌ Erro no pedido #{pedido_id}: {e}")

    logger.info(f"[{_TAG}] ✅ Rotina de followup concluída.")
    logger.info("=" * 120)


def _enviar_followup(pedido: dict) -> None:
    pedido_id  = pedido['id']
    produto_id = pedido['produto_id']
    produto    = db.get_produto_disponivel_web(produto_id)

    destinatario = pedido['email']
    nome_cliente = (pedido.get('contact_name') or 'cliente').split()[0]
    remetente    = (produto or {}).get('email_remetente') or os.getenv('EMAIL_FROM', '')
    nome_produto = (produto or {}).get('nome', 'Guia Digital')

    nome_remetente_email = (produto or {}).get('email_nome_remetente') or 'LSN Livros'
    cor_primaria         = (produto or {}).get('email_cor_primaria') or '#2d6a1f'
    cor_secundaria       = (produto or {}).get('email_cor_secundaria') or '#b45309'

    itens_extras = [
        item['nome'] for item in db.listar_itens_pedido(pedido_id)
        if item['tipo'] != 'principal'
    ]

    qrcode_bytes = (
        base64.b64decode(_gerar_qrcode_base64(pedido['qr_code_pix']))
        if pedido.get('qr_code_pix') else None
    )

    base_url = os.getenv('APP_BASE_URL', '').rstrip('/')
    link_pagamento = pedido.get('url_bbpay') or f"{base_url}/pay/{produto_id}?pedido={pedido_id}"

    subject = f'🎁 {nome_cliente}, seu {nome_produto} ainda está te esperando!'

    _enviar_gmail(
        destinatario=destinatario,
        remetente=remetente,
        nome_remetente=f'{nome_remetente_email} — {nome_produto}',
        subject=subject,
        html=_corpo_html(nome_cliente, nome_produto, itens_extras, bool(qrcode_bytes),
                        pedido.get('qr_code_pix') or '', link_pagamento,
                        nome_remetente_email, cor_primaria, cor_secundaria),
        imagens_inline=[{'cid': _QR_CID, 'dados': qrcode_bytes, 'subtype': 'png'}] if qrcode_bytes else None,
    )


def _corpo_html(nome: str, nome_produto: str, itens_extras: list, tem_qrcode: bool,
                codigo_pix: str, link_pagamento: str, nome_remetente: str,
                cor_primaria: str, cor_secundaria: str) -> str:
    cor_primaria_clara = _lighten_hex(cor_primaria, 0.3)

    secao_bonus = ''
    if itens_extras:
        lista = ''.join(
            f'<p style="font-size:14px; color:#555; margin:4px 0;">🎁 {nome_item}</p>'
            for nome_item in itens_extras
        )
        secao_bonus = f'''
                  <p style="font-size:14px; color:#555; margin:0 0 8px;">
                    Seu pedido continua reservado com tudo que você escolheu:
                  </p>
                  {lista}'''

    qr_html = ''
    if tem_qrcode:
        qr_html = f'''
                  <img src="cid:{_QR_CID}" alt="QR code Pix"
                       style="width:220px; height:220px; margin:16px auto; display:block;">'''

    copia_cola_html = ''
    if codigo_pix:
        copia_cola_html = f'''
                  <p style="font-size:13px; color:#555; margin:16px 0 6px;">
                    Ou toque e segure o código abaixo pra copiar (Pix Copia e Cola):
                  </p>
                  <div style="background:#ffffff; border:1px dashed #999; border-radius:8px;
                              padding:12px 14px; font-family:monospace; font-size:12px;
                              color:#333; word-break:break-all; text-align:left; user-select:all;">
                    {html.escape(codigo_pix)}
                  </div>'''

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; background:#f9f5ef; margin:0; padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9f5ef; padding:24px 0;">
    <tr><td align="center">
      <table width="100%" style="max-width:560px; background:#ffffff; border-radius:16px;
                                  overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.08);">

        <!-- Cabeçalho -->
        <tr>
          <td style="background:linear-gradient(135deg,{cor_primaria},{cor_primaria_clara}); padding:28px 32px; text-align:center;">
            <h1 style="color:#ffffff; font-size:22px; font-weight:bold; margin:0; font-family:Georgia,serif;">
              🎁 {nome}, seu {nome_produto} ainda está te esperando!
            </h1>
          </td>
        </tr>

        <!-- Corpo -->
        <tr>
          <td style="padding:32px;">

            <p style="font-size:16px; color:#333; margin:0 0 16px;">
              Oi, {nome}! Aqui é a <strong>{nome_remetente}</strong>.
            </p>

            <p style="font-size:16px; color:#333; margin:0 0 16px;">
              Vi que você começou a garantir o <strong>{nome_produto}</strong> mas o
              pagamento ainda não foi concluído — não se preocupe, seu pedido continua
              reservado.
            </p>

            <table width="100%" style="background:#fff8e1; border-radius:12px;
                                        margin:0 0 28px; text-align:center;">
              <tr>
                <td style="padding:24px 20px;">
                  {secao_bonus}
                  <p style="font-size:15px; font-weight:bold; color:#1a4012; margin:16px 0 8px;">
                    Escaneie o QR code abaixo com o app do seu banco (Pix):
                  </p>
                  {qr_html}
                  {copia_cola_html}
                  <a href="{link_pagamento}"
                     style="display:inline-block; background:{cor_secundaria}; color:#ffffff;
                            font-size:15px; font-weight:bold; text-decoration:none;
                            padding:14px 28px; border-radius:12px; margin:16px 0 0;">
                    🏦 Pagar via Banco do Brasil
                  </a>
                </td>
              </tr>
            </table>

            <p style="font-size:14px; color:#555; margin:0 0 24px;">
              Qualquer dúvida, é só responder este e-mail que te ajudo. 😊
            </p>

            <p style="font-size:14px; color:#666; margin:0;">
              Com carinho,<br>
              <strong style="color:{cor_primaria};">{nome_remetente}</strong>
            </p>
          </td>
        </tr>

        <!-- Rodapé -->
        <tr>
          <td style="background:#f0f0f0; padding:16px 32px; text-align:center;">
            <p style="font-size:11px; color:#999; margin:0;">
              Você recebeu este e-mail porque iniciou uma compra em lsnlivros.com.br.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
