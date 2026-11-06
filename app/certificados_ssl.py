"""
Alerta diário de vencimento dos certificados SSL (infra/certbot/README.md).

Conecta em cada domínio pelo HTTPS, como o navegador, e lê o vencimento do certificado servido.
Manda e-mail para o admin@ quando algum estiver a DIAS_ALERTA dias ou menos de vencer, ou já
inválido (vencido, nome errado, fora do ar). Os Let's Encrypt renovam sozinhos com 30 dias de folga,
então um deles aqui é sinal de que o renew.sh parou; lsnlivros e lbe-livros (mTLS do Pix BB) são
renovados à mão.

Domínio novo: incluir em DOMINIOS (a skill novo-dominio lembra disso).
"""

import html
import logging
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DIAS_ALERTA = 20
DESTINATARIO = 'admin@lsnlivros.com.br'

# Certificado pago, cadastrado no BB para o mTLS do Pix: renovação manual.
DOMINIOS_MANUAIS = ('lsnlivros.com.br', 'lbe-livros.site')

DOMINIOS = DOMINIOS_MANUAIS + (
    'lssolucoesdigitais.com.br', 'lsdigitalsolucoes.com.br', 'lneditor.com.br', 'kpnlivros.com.br',
    'lsfb-livros.com.br', 'rc-livros.com.br', 'lclivros.com.br', 'ju-livros.com.br', 'lsreceitas.com.br',
    'lblivros.com.br', 'lbelivros.com.br', 'stracklivros.com.br', 'barreiroslivros.com.br',
    'breplivros.site', 'lb-livros.site', 'livrinhosdigitais.site', 'leituraemais.site',
    'vitrinidaju.site', 'livrosemais.site',
)


def consultar(dominio: str, timeout: int = 10) -> dict:
    """{'dominio', 'vence_em' (datetime UTC), 'dias'} ou {'dominio', 'erro'} se o navegador recusaria."""
    contexto = ssl.create_default_context()
    try:
        with socket.create_connection((dominio, 443), timeout=timeout) as sock:
            with contexto.wrap_socket(sock, server_hostname=dominio) as tls:
                cert = tls.getpeercert()
    except (OSError, ssl.SSLError) as exc:
        return {'dominio': dominio, 'erro': str(exc)}
    vence = ssl.cert_time_to_seconds(cert['notAfter'])
    return {'dominio': dominio,
            'vence_em': datetime.fromtimestamp(vence, tz=timezone.utc),
            'dias': int((vence - time.time()) // 86400)}


def _linha(r: dict) -> str:
    tipo = 'manual (BB)' if r['dominio'] in DOMINIOS_MANUAIS else "Let's Encrypt: renew.sh não renovou"
    if 'erro' in r:
        situacao = f"<b>INVÁLIDO</b> ({html.escape(r['erro'])})"
    else:
        situacao = f"vence em {r['vence_em']:%d/%m/%Y} ({r['dias']} dias)"
    return f"<li><b>{r['dominio']}</b>: {situacao}. {tipo}</li>"


def verificar_certificados(dominios=DOMINIOS, enviar_email=None) -> list:
    """Consulta todos e, se algum precisar de atenção, avisa por e-mail. Devolve os que precisam."""
    from config import EH_PRODUCAO

    with ThreadPoolExecutor(max_workers=8) as pool:  # em sequência, um domínio fora do ar somaria 10 s cada
        resultados = list(pool.map(consultar, dominios))
    alertas = [r for r in resultados if 'erro' in r or r['dias'] <= DIAS_ALERTA]
    for r in resultados:
        logger.info(f"[SSL] {r['dominio']}: {r.get('erro') or str(r['dias']) + ' dias'}")
    if not alertas:
        return []

    assunto = f"[SSL] {len(alertas)} certificado(s) vencendo ou inválido(s)"
    if not EH_PRODUCAO:
        logger.warning(f"{assunto} (dev: e-mail não enviado)")
        return alertas

    corpo = (f"<p>Certificados com {DIAS_ALERTA} dias ou menos até vencer, ou já recusados pelo navegador:</p>"
             f"<ul>{''.join(_linha(r) for r in alertas)}</ul>"
             "<p>Como renovar: <code>infra/certbot/README.md</code>.</p>")
    if enviar_email is None:
        from fluxos._email_gmail import enviar as enviar_email
    enviar_email(destinatario=DESTINATARIO, remetente=DESTINATARIO, nome_remetente='Alerta SSL',
                 subject=assunto, html=corpo)
    logger.warning(f"{assunto}: e-mail enviado para {DESTINATARIO}")
    return alertas
