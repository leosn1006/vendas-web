"""Envio das compras para a API de Conversões da Meta, venda a venda. O que não foi aceito volta na hora seguinte."""
import hashlib
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import requests

import config
from database import busca_vendas_meta_sem_dataset, busca_vendas_pendentes_meta, marcar_venda_como_enviada_a_meta
from fluxos.fluxo_upload_google_ads import valor_conversao

logger = logging.getLogger(__name__)

_SP_TZ = timezone(timedelta(hours=-3))
_PREFIXO_TOKEN = 'META_TOKEN_'
_DIAS_AVISO_JANELA = 5  # aos 6 a venda sai da seleção sem rastro; a Meta recusa evento com mais de 7


def _sha256(valor: str) -> str:
    return hashlib.sha256(valor.encode('utf-8')).hexdigest()


def normalizar_telefone(telefone) -> str:
    """Só dígitos, sem zeros à esquerda, com DDI. Celular brasileiro salvo sem o 9º dígito ganha o 9 de volta
    (o checkout tira o 9 para casar com o webhook do WhatsApp). Fixo e outros países não mudam."""
    digitos = re.sub(r'[^0-9]', '', str(telefone or '')).lstrip('0')
    # O checkout não põe o DDI quando o número já começa com 55, caso do DDD 55 (RS).
    if len(digitos) in (10, 11) and digitos.startswith('55'):
        digitos = f'55{digitos}'
    if len(digitos) == 12 and digitos.startswith('55') and digitos[4] in '6789':
        return f'{digitos[:4]}9{digitos[4:]}'
    return digitos


def _data_pagamento(venda) -> datetime:
    """data_pagamento com fuso: o banco grava em horário de Brasília, seja qual for o fuso do servidor."""
    data = venda.data_pagamento
    if isinstance(data, str):
        try:
            data = datetime.fromisoformat(data)
        except ValueError:
            data = datetime.strptime(data, "%Y-%m-%d %H:%M:%S")
    return data if data.tzinfo else data.replace(tzinfo=_SP_TZ)


def montar_evento(venda) -> dict | None:
    """O evento Purchase da venda, ou None sem domínio ou sem navegador, que a Meta exige."""
    if not venda.dns_origem or not venda.client_user_agent:
        return None

    user_data = {'client_user_agent': venda.client_user_agent}
    if venda.client_ip:
        user_data['client_ip_address'] = venda.client_ip
    if venda.fbc:
        user_data['fbc'] = venda.fbc
    email = (venda.email or '').strip().lower()
    if email:
        user_data['em'] = [_sha256(email)]
    telefone = normalizar_telefone(venda.contact_phone)
    if telefone:
        user_data['ph'] = [_sha256(telefone)]

    return {
        'event_name': 'Purchase',
        # A data do comprovante do WhatsApp não é validada: pode estar no futuro.
        'event_time': min(int(_data_pagamento(venda).timestamp()), int(time.time())),
        'event_id': f'pedido-{venda.id}',
        'action_source': 'website',
        'event_source_url': f'https://{venda.dns_origem}/',
        'custom_data': {'currency': 'BRL', 'value': float(valor_conversao(venda))},
        'user_data': user_data,
    }


def _token(nome_variavel) -> str:
    """O nome vem do admin: só META_TOKEN_*, para outro segredo do ambiente nunca sair para a Meta."""
    if not str(nome_variavel or '').startswith(_PREFIXO_TOKEN):
        return ''
    return os.getenv(nome_variavel, '').strip()


def _enviar_evento(venda, evento: dict, token: str, codigo_teste: str) -> bool:
    """Manda um evento. True só com events_received >= 1."""
    payload = {'data': [evento]}
    if codigo_teste:
        payload['test_event_code'] = codigo_teste
    resposta = requests.post(
        f"{config.WHATSAPP_API_URL}{venda.meta_dataset_id}/events",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=30,
    )
    try:
        corpo = resposta.json()
    except ValueError:
        corpo = None
    recebidos = corpo.get('events_received') if isinstance(corpo, dict) else None
    if resposta.status_code == 200 and isinstance(recebidos, int) and recebidos >= 1:
        return True
    erro = corpo.get('error') if isinstance(corpo, dict) else None
    logger.error(f"[FLUXO-META-CONVERSOES] ❌ Venda {venda.id} recusada: HTTP {resposta.status_code} | {erro or recebidos}")
    return False


def _processar_venda(venda) -> str:
    """Tenta enviar uma venda e devolve em que total do resumo ela entra."""
    evento = montar_evento(venda)
    if not evento:
        logger.warning(f"[FLUXO-META-CONVERSOES] ⚠️ Venda {venda.id} sem domínio ou sem navegador: fica pendente")
        return 'pendentes'

    token = _token(venda.meta_token_env_var)
    if not token:
        logger.error(f"[FLUXO-META-CONVERSOES] ❌ Venda {venda.id}: token '{venda.meta_token_env_var}' inválido ou vazio")
        return 'erros'

    codigo_teste = os.getenv('META_TEST_EVENT_CODE', '').strip()
    if not _enviar_evento(venda, evento, token, codigo_teste):
        return 'erros'
    if codigo_teste:
        return 'testes'  # modo teste: a venda continua pendente para o envio de verdade
    marcar_venda_como_enviada_a_meta(venda.id)
    return 'enviadas'


def _avisar_se_perto_de_sair(venda) -> None:
    pago_ha = datetime.now(_SP_TZ) - _data_pagamento(venda)
    if pago_ha >= timedelta(days=_DIAS_AVISO_JANELA):
        logger.error(f"[FLUXO-META-CONVERSOES] ⏰ Venda {venda.id} sem aceite há {pago_ha.days} dias: aos 6 sai da seleção")


def _avisar_vendas_sem_dataset() -> None:
    """Só diagnóstico: uma falha aqui não pode impedir o envio."""
    try:
        for venda in busca_vendas_meta_sem_dataset():
            logger.error(f"[FLUXO-META-CONVERSOES] ❌ Venda {venda['id']}: produto {venda['produto_id']} sem dataset para "
                         f"o domínio '{venda['dns_origem']}': não será enviada")
    except Exception as e:
        logger.error(f"[FLUXO-META-CONVERSOES] ❌ Erro ao procurar vendas sem dataset: {type(e).__name__}: {e}")


def executar() -> dict:
    _avisar_vendas_sem_dataset()
    vendas = busca_vendas_pendentes_meta()
    resumo = {'vendas': len(vendas), 'enviadas': 0, 'testes': 0, 'pendentes': 0, 'erros': 0}
    for venda in vendas:
        venda = SimpleNamespace(**venda)  # valor_conversao lê por atributo
        try:
            situacao = _processar_venda(venda)
            if situacao in ('erros', 'pendentes'):
                _avisar_se_perto_de_sair(venda)
        except Exception as e:
            logger.error(f"[FLUXO-META-CONVERSOES] ❌ Erro na venda {venda.id}: {type(e).__name__}: {e}")
            situacao = 'erros'
        resumo[situacao] += 1
    logger.info(f"[FLUXO-META-CONVERSOES] 🏁 {resumo}")
    return resumo
