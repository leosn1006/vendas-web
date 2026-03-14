"""
Entrega do e-book por e-mail com PDFs em anexo.

Fluxo:
  1. Busca pedido (email, contact_name, produto_id)
  2. Busca produto (url_pdf, url_pdf_bonus, email_remetente, descricao) — tabela produtos
  3. Monta e-mail com PDFs como anexos (não como link)
  4. Envia via Brevo API (HTTP/443 — sem dependência de porta SMTP)
  5. Marca data_envio_ebook no pedido
"""

import os
import base64
import logging
import requests

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'arquivos')


def executar(pedido_id: int) -> None:
    import database as db

    pedido  = db.get_pedido(pedido_id)
    produto = db.get_produto_disponivel_web(pedido['produto_id'])

    if not pedido.get('email'):
        logger.warning(f'[EMAIL] Pedido #{pedido_id} sem e-mail — entrega ignorada')
        return

    destinatario = pedido['email']
    nome_cliente = (pedido.get('contact_name') or '').split()[0] or 'cliente'
    remetente    = (produto or {}).get('email_remetente') or os.getenv('EMAIL_FROM', '')
    nome_produto = (produto or {}).get('descricao', 'Guia Digital')
    pedido_num   = f'#{pedido_id:04d}'
    subject      = f'Pedido {pedido_num} - ✅ ACESSO LIBERADO: Seu {nome_produto} está em anexo!'

    anexos = []
    if produto and produto.get('url_pdf'):
        anexos.append(_ler_anexo(produto['url_pdf']))
    if produto and produto.get('url_pdf_bonus'):
        anexos.append(_ler_anexo(produto['url_pdf_bonus']))

    _enviar(
        destinatario=destinatario,
        remetente=remetente,
        subject=subject,
        html=_corpo_html(nome_cliente, nome_produto),
        anexos=anexos,
    )
    db.marcar_ebook_enviado(pedido_id)
    logger.info(f'[EMAIL] ✅ Pedido #{pedido_id} entregue para {destinatario}')


def _ler_anexo(nome_arquivo: str) -> dict:
    caminho = os.path.join(_BASE_DIR, nome_arquivo)
    with open(caminho, 'rb') as f:
        conteudo = base64.b64encode(f.read()).decode()
    return {'name': nome_arquivo, 'content': conteudo}


def _enviar(destinatario: str, remetente: str, subject: str,
            html: str, anexos: list) -> None:
    payload = {
        'sender':      {'name': 'Luiza — Guia Pães Saudáveis', 'email': remetente},
        'to':          [{'email': destinatario}],
        'subject':     subject,
        'htmlContent': html,
        'attachment':  anexos,
    }
    resp = requests.post(
        'https://api.brevo.com/v3/smtp/email',
        json=payload,
        headers={
            'api-key':      os.getenv('BREVO_API_KEY', ''),
            'Content-Type': 'application/json',
        },
        timeout=30,
    )
    resp.raise_for_status()


def _corpo_html(nome: str, nome_produto: str) -> str:
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

        <!-- Cabeçalho verde -->
        <tr>
          <td style="background:linear-gradient(135deg,#1a4012,#2d6a1f); padding:28px 32px; text-align:center;">
            <h1 style="color:#ffffff; font-size:22px; margin:0; font-family:Georgia,serif;">
              ✅ Seu {nome_produto} chegou!
            </h1>
          </td>
        </tr>

        <!-- Corpo -->
        <tr>
          <td style="padding:32px;">
            <p style="font-size:16px; color:#333; margin:0 0 16px;">
              Olá, <strong>{nome}</strong>! Tudo bem?
            </p>
            <p style="font-size:15px; color:#444; line-height:1.7; margin:0 0 16px;">
              Aqui é a <strong>Luiza</strong>. Passando para confirmar que o seu pagamento
              foi recebido com sucesso. Parabéns pela decisão de transformar o seu café da manhã! 🎉
            </p>

            <!-- Destaque anexo -->
            <table width="100%" style="background:#f0f7eb; border-left:4px solid #2d6a1f;
                                        border-radius:0 12px 12px 0; margin:20px 0;">
              <tr>
                <td style="padding:16px 20px;">
                  <p style="font-size:15px; font-weight:bold; color:#1a4012; margin:0 0 8px;">
                    📥 ONDE ESTÁ O SEU GUIA?
                  </p>
                  <p style="font-size:14px; color:#444; line-height:1.6; margin:0;">
                    Para garantir que você nunca perca o acesso, eu anexei o Guia Digital
                    <strong>diretamente neste e-mail</strong>.<br><br>
                    Procure pelo ícone de <strong>clipe 📎</strong> ou pelo nome do arquivo
                    logo abaixo da mensagem — no Gmail pelo celular, os anexos aparecem
                    <em>bem no finalzinho</em>, depois da assinatura.
                  </p>
                </td>
              </tr>
            </table>

            <p style="font-size:15px; font-weight:bold; color:#333; margin:20px 0 8px;">
              O que fazer agora:
            </p>
            <ol style="font-size:14px; color:#444; line-height:1.8; margin:0 0 20px; padding-left:20px;">
              <li>Toque no arquivo em anexo para abrir.</li>
              <li>Salve no seu celular (app <em>Arquivos</em> ou <em>Downloads</em>) para acessar
                  sempre que quiser, mesmo sem internet.</li>
              <li>Se preferir, imprima as receitas para ter sempre à mão na cozinha!</li>
            </ol>

            <!-- Caixa de bônus -->
            <table width="100%" style="background:#fff8e1; border:1px dashed #f59e0b;
                                        border-radius:12px; margin:0 0 24px;">
              <tr>
                <td style="padding:16px 20px;">
                  <p style="font-size:14px; font-weight:bold; color:#b45309; margin:0 0 8px;">
                    🎁 O QUE VOCÊ VAI ENCONTRAR LÁ DENTRO:
                  </p>
                  <ul style="font-size:14px; color:#444; line-height:1.8; margin:0; padding-left:18px;">
                    <li>As <strong>50 receitas de pães</strong> sem glúten e sem lactose.</li>
                    <li>Seu <strong>Bônus Especial</strong>: Livro de Bolos Fofinhos — incluído no mesmo e-mail.</li>
                    <li>O passo a passo para <strong>nunca mais errar o ponto da massa</strong>.</li>
                  </ul>
                </td>
              </tr>
            </table>

            <p style="font-size:15px; color:#333; line-height:1.7; margin:0 0 24px;">
              Prepare o forno — o cheirinho de pão quentinho vai invadir a sua casa logo logo! 🍞
            </p>

            <p style="font-size:14px; color:#666; margin:0;">
              Com carinho,<br>
              <strong style="color:#1a4012;">Luiza — Guia Pães Saudáveis</strong>
            </p>
          </td>
        </tr>

        <!-- Rodapé -->
        <tr>
          <td style="background:#f0f0f0; padding:16px 32px; text-align:center;">
            <p style="font-size:11px; color:#999; margin:0;">
              Você recebeu este e-mail porque realizou uma compra em lsnlivros.com.br.<br>
              Guarde este e-mail para ter sempre acesso aos seus arquivos.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
