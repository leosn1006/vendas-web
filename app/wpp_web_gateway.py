"""Cliente da API de administração do gateway WhatsApp Web (projeto api-wpp-web).

Só o backend chama: o token do gateway nunca vai ao navegador. O QR devolvido é credencial
(quem o lê controla o chip) — não logar, não cachear.
"""
import io
import os
import re
import logging
from urllib.parse import quote, urlsplit

import qrcode
import qrcode.image.svg
import requests

from config import WPP_WEB_API_URL, WPP_WEB_WEBHOOK_URL

logger = logging.getLogger(__name__)

_TIMEOUT_S = 10
_TOKEN_ENV_KEY = 'GATEWAY_TOKEN_WPP'


class ErroGatewayWppWeb(Exception):
    def __init__(self, mensagem: str, status: int = None):
        super().__init__(mensagem)
        self.status = status


def _base_admin() -> str:
    """https://host:porta do gateway, derivado de WPP_WEB_API_URL (que termina em /vNN.N/)."""
    if not WPP_WEB_API_URL:
        raise ErroGatewayWppWeb('WPP_WEB_API_URL não está definida no .env.')
    partes = urlsplit(WPP_WEB_API_URL)
    return f"{partes.scheme}://{partes.netloc}"


def _headers() -> dict:
    token = os.getenv(_TOKEN_ENV_KEY, '')
    if not token:
        raise ErroGatewayWppWeb(f'{_TOKEN_ENV_KEY} não está definida no .env.')
    return {'Authorization': f'Bearer {token}'}


def _chamar(metodo: str, caminho: str, json_body: dict = None):
    try:
        resp = requests.request(metodo, f"{_base_admin()}{caminho}", headers=_headers(),
                                json=json_body, timeout=_TIMEOUT_S)
    except requests.RequestException as e:
        raise ErroGatewayWppWeb(f'Gateway inalcançável: {type(e).__name__}') from e
    if resp.status_code == 204:
        return {}
    try:
        corpo = resp.json()
    except ValueError:
        corpo = {}
    if not resp.ok:
        raise ErroGatewayWppWeb(corpo.get('error') or f'HTTP {resp.status_code}', status=resp.status_code)
    return corpo


def _somente_digitos(telefone: str) -> str:
    return re.sub(r'\D', '', telefone or '')


GATEWAY_TOKEN_ENV_KEY = _TOKEN_ENV_KEY
_ID_CHIP_RE = re.compile(r'^web-(\d{10,15})$')


def normalizar_cadastro_numero(provedor: str, telefone: str, api_phone_number_id, token_env_key):
    """Coerência entre provedor, api_phone_number_id e token_env_key no cadastro do número.

    Devolve (api_phone_number_id, token_env_key) prontos para gravar. Levanta ValueError com mensagem
    para o admin. Evita: chip do gateway com o token da Meta (o token real iria como Bearer para o gateway),
    número da Meta com o token do gateway (iria para graph.facebook.com), e id do chip que não bate com o
    telefone (o pareamento pelo admin criaria um chip diferente do que o webhook informa).
    """
    api_phone_number_id = (api_phone_number_id or '').strip() or None
    token_env_key = (token_env_key or '').strip() or None
    if provedor != 'wpp_web':
        if token_env_key == GATEWAY_TOKEN_ENV_KEY:
            raise ValueError(f'{GATEWAY_TOKEN_ENV_KEY} é o token do gateway; só vale para o provedor WhatsApp Web.')
        return api_phone_number_id, token_env_key or 'WHATSAPP_ACCESS_TOKEN'

    digitos = _somente_digitos(telefone)
    esperado = f'web-{digitos}'
    if not _ID_CHIP_RE.match(esperado):
        raise ValueError('Display phone inválido para o WhatsApp Web (use DDI+DDD+número, só dígitos).')
    if api_phone_number_id and api_phone_number_id != esperado:
        raise ValueError(f'Para o WhatsApp Web o API phone_number_id deve ser {esperado} (web-<número do chip>).')
    if token_env_key not in (None, 'WHATSAPP_ACCESS_TOKEN', GATEWAY_TOKEN_ENV_KEY):
        raise ValueError(f'Para o WhatsApp Web o Token env key deve ser {GATEWAY_TOKEN_ENV_KEY}.')
    # 'WHATSAPP_ACCESS_TOKEN' é o padrão do formulário (Meta): aqui vira o token do gateway.
    return esperado, GATEWAY_TOKEN_ENV_KEY


def buscar_chip(chip_ref: str):
    """View do chip (status, action, needsAction, message, webhook) ou None se não existe no gateway."""
    try:
        return _chamar('GET', f'/admin/chips/{quote(chip_ref, safe="")}')
    except ErroGatewayWppWeb as e:
        if e.status == 404:
            return None
        raise


def criar_chip(telefone: str) -> dict:
    digitos = _somente_digitos(telefone)
    if len(digitos) < 10:
        raise ErroGatewayWppWeb('Número inválido para o gateway.')
    return _chamar('POST', '/admin/chips', {'phone': digitos, 'pairing': 'qr'})


def reiniciar_chip(chip_ref: str) -> dict:
    return _chamar('POST', f'/admin/chips/{quote(chip_ref, safe="")}/restart')


def _segredo_do_webhook(url_webhook: str) -> str:
    """Segredo que o vendas-web usa para validar a assinatura: escolhido pelo Host da URL (mesmo mapa
    que whatsapp_seguranca usa ao receber). Host não mapeado ou segredo ausente = erro explícito."""
    from whatsapp_seguranca import WhatsAppSecurity
    host = (urlsplit(url_webhook).hostname or '').lower()
    env_key = WhatsAppSecurity._HOST_SECRET_MAP.get(host)
    if not env_key:
        raise ErroGatewayWppWeb(f"Host '{host}' da WPP_WEB_WEBHOOK_URL não está em _HOST_SECRET_MAP.")
    segredo = os.getenv(env_key, '')
    if not segredo:
        raise ErroGatewayWppWeb(f'{env_key} não está definida no .env (segredo do webhook de {host}).')
    return segredo


def garantir_webhook(chip: dict, chip_ref: str) -> bool:
    """Configura no chip o webhook do vendas-web, se ainda não houver um. Devolve True se configurou.
    Idempotente: não mexe em chip que já tem webhook próprio (custom). Sem WPP_WEB_WEBHOOK_URL não faz nada."""
    if not WPP_WEB_WEBHOOK_URL:
        return False
    if (chip.get('webhook') or {}).get('custom'):
        return False
    _chamar('PATCH', f'/admin/chips/{quote(chip_ref, safe="")}',
            {'webhookUrl': WPP_WEB_WEBHOOK_URL, 'appSecret': _segredo_do_webhook(WPP_WEB_WEBHOOK_URL)})
    logger.info(f"[WPP-WEB] 🔗 Webhook do chip {chip_ref} configurado para {WPP_WEB_WEBHOOK_URL}")
    return True


def remover_chip(chip_ref: str) -> bool:
    """Desvincula o aparelho (logout do WhatsApp Web), apaga a sessão e o cadastro do chip no gateway.
    Devolve False se o chip já não existia lá (404) — remover de novo não é erro."""
    try:
        _chamar('DELETE', f'/admin/chips/{quote(chip_ref, safe="")}')
        return True
    except ErroGatewayWppWeb as e:
        if e.status == 404:
            return False
        raise


def recriar_do_zero(chip_ref: str, telefone: str) -> None:
    """Apaga o chip (sessão + cadastro) no gateway e recria vazio, pronto para gerar um QR novo.

    Usado quando o chip trava em estados que o simples restart não resolve: a sessão do Chromium
    (perfil em disco) ficou corrompida numa tentativa anterior e o gateway só limpa arquivos de trava
    entre tentativas normais, não a pasta inteira — então o restart sozinho repete o mesmo erro. Caso real:
    INIT_FAILED com "Cannot read properties of null (reading 'Socket')" resistente a restart e a proxy,
    resolvido só apagando e recriando (ver docs/INTEGRACAO.md)."""
    remover_chip(chip_ref)
    criar_chip(telefone)


def buscar_qr(chip_ref: str) -> dict:
    """{status, action, needsAction, message, qr, pairingCode}. `qr` é a string crua do QR."""
    return _chamar('GET', f'/admin/chips/{quote(chip_ref, safe="")}/qr')


def qr_para_svg(texto_qr: str) -> str:
    """Renderiza a string crua do QR como SVG (sem depender de Pillow nem de JS no navegador)."""
    img = qrcode.make(texto_qr, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode('utf-8')
