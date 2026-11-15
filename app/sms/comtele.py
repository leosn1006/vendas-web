"""Cliente da API nova da Comtele (developers.comtele.com.br, "Send SMS Message"): POST com x-api-key."""
import logging

import requests

from sms import config

logger = logging.getLogger(__name__)


class ErroSms(Exception):
    """A Comtele recusou (chave, número, saldo...): não adianta tentar de novo."""


class ErroPassageiro(ErroSms):
    """Rede, 5xx ou 429: vale tentar de novo."""


def enviar(telefone: str, texto: str, tag: str, custom: str) -> str:
    """Envia um SMS; devolve o requestId da Comtele. `tag` = origem (aparece no relatório deles) e `custom` = id do
    nosso envio (para casar o relatório de entrega)."""
    if not config.COMTELE_CHAVE:
        raise ErroSms('CONTELE_SMS_API (chave da Comtele) não configurada')
    corpo = {'receivers': [telefone], 'contactGroups': [], 'message': texto, 'route': config.COMTELE_ROTA,
             'tag': tag[:40], 'custom': custom[:40], 'scheduleDate': None}
    # Nova tentativa só quando é certo que a Comtele NÃO aceitou (sem conexão, 429, 503). Resposta que não chegou
    # (timeout de leitura) ou 500/502/504 podem ser SMS já aceito: tentar de novo = SMS repetido e cobrado. Esses
    # viram ErroSms ('falhou', com o motivo) e o relatório de entrega, se vier, corrige para 'entregue'.
    try:
        resposta = requests.post(config.COMTELE_URL, json=corpo, timeout=(5, 20),
                                 headers={'x-api-key': config.COMTELE_CHAVE, 'Content-Type': 'application/json'})
    except requests.ConnectTimeout as erro:
        raise ErroPassageiro(f'sem conexão: {erro}') from erro
    except requests.ConnectionError as erro:
        # Só é certo que não saiu se a conexão nem abriu (DNS, recusada). "Connection aborted" depois do envio pode
        # ser SMS aceito.
        if any(sinal in str(erro) for sinal in ('NewConnectionError', 'Failed to establish', 'Name or service',
                                                  'nodename nor servname', 'Temporary failure in name resolution')):
            raise ErroPassageiro(f'sem conexão: {erro}') from erro
        raise ErroSms(f'conexão caiu (pode ter saído): {erro}') from erro
    except requests.RequestException as erro:
        raise ErroSms(f'sem resposta da Comtele (pode ter saído): {erro}') from erro
    if resposta.status_code in (429, 503):
        raise ErroPassageiro(f'HTTP {resposta.status_code}: {resposta.text[:200]}')
    if resposta.status_code >= 500:
        raise ErroSms(f'HTTP {resposta.status_code} (pode ter saído): {resposta.text[:200]}')
    try:
        dados = resposta.json()
    except ValueError:
        dados = {}
    if resposta.status_code >= 400 or dados.get('hasError'):
        raise ErroSms(f"HTTP {resposta.status_code}: {dados.get('message') or dados.get('errors') or resposta.text[:200]}")
    request_id = ((dados.get('object') or {}).get('requestId')) or ''
    logger.info(f'[SMS] Comtele aceitou o envio {custom} ({request_id})')
    return str(request_id)
