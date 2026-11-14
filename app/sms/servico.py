"""Envio de SMS do sistema (qualquer produto). Quem usa monta o texto; aqui: número, trava do dev, link curto,
registro em sms_envios e a tarefa que fala com a Comtele. Ver docs/SMS.md."""
import logging
import re
from typing import Callable

import config as config_geral
import links_curtos
from sms import comtele, config
from sms.texto import LIMITE, partes, sem_acento

logger = logging.getLogger(__name__)


def celular(telefone) -> str:
    """Celular brasileiro com DDI ('55' + DDD + 9 + 8 dígitos) ou '' (fixo, incompleto, de fora — por enquanto só
    Brasil). Aceita com ou sem o 55, com o 0 da operadora e com máscara."""
    digitos = re.sub(r'\D', '', str(telefone or '')).lstrip('0')
    if len(digitos) == 11:
        digitos = '55' + digitos
    return digitos if len(digitos) == 13 and digitos.startswith('55') and digitos[4] == '9' else ''


def mascarar(telefone: str) -> str:
    return f'({telefone[2:4]}) *****-{telefone[-4:]}' if telefone and len(telefone) >= 8 else telefone or ''


def _db():
    from database import db
    return db


def enviar(produto_id: int | None, telefone: str, montar_texto: Callable[[str], str], url_destino: str,
           dominio_base: str, origem: str, etapa: str | None = None, ref_tipo: str | None = None,
           ref_id: int | None = None, minimo_minutos: int | None = None) -> int | None:
    """Agenda um SMS. `montar_texto(link_curto)` devolve o texto já com o link (`dominio/m/<codigo>`). Devolve o id
    em sms_envios, ou None quando não sai (SMS desligado, número que não é celular, sem domínio para o link, ou o
    mesmo celular recebeu SMS há menos de `minimo_minutos` — de qualquer origem: duas músicas com e-mails diferentes
    não somam SMS no mesmo celular).

    Grava antes de chamar a Comtele (a tarefa só envia o que está 'pendente'): uma falha no meio nunca vira SMS
    repetido."""
    if not config.ATIVO:
        logger.info(f'[SMS] Desligado (SMS_ATIVO=0): {origem} para ...{str(telefone)[-4:]} não enviado')
        return None
    numero = celular(telefone)
    if not numero:
        logger.info(f'[SMS] {origem}: ...{str(telefone)[-4:]} não é celular brasileiro; não enviado')
        return None
    if not re.sub(r'^https?://', '', dominio_base or '').strip('/'):
        logger.error(f'[SMS] {origem} ({ref_tipo} {ref_id}): sem domínio para o link curto; não enviado')
        return None
    if minimo_minutos and _db().execute_query(
            "SELECT 1 FROM sms_envios WHERE telefone = %s AND status IN ('pendente', 'enviando', 'enviado', 'entregue') "
            "AND criado_em > NOW() - INTERVAL %s MINUTE LIMIT 1", (numero, minimo_minutos), fetch_one=True):
        logger.info(f'[SMS] {origem}: {mascarar(numero)} recebeu SMS há menos de {minimo_minutos} min; não enviado')
        return None
    link = links_curtos.criar(url_destino, origem, ref_tipo, ref_id)
    texto = sem_acento(montar_texto(links_curtos.endereco(dominio_base, link['codigo'])))
    status, erro = 'pendente', None
    if len(texto) > LIMITE:
        status, erro = 'falhou', f'texto com {len(texto)} caracteres (máximo {LIMITE}): não enviado'
        logger.error(f'[SMS] {origem}: {erro} — {texto!r}')
    elif not config_geral.EH_PRODUCAO and numero not in config.DEV_PERMITIDOS:
        status = 'ignorado_dev'
        logger.info(f'[SMS][DEV] NÃO enviado para {mascarar(numero)} (fora de SMS_DEV_PERMITIDOS): {texto}')
    envio_id = _db().execute_query(
        "INSERT INTO sms_envios (produto_id, origem, etapa, ref_tipo, ref_id, telefone, texto, partes, link_id, status, "
        "erro) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (produto_id, origem, etapa, ref_tipo, ref_id, numero, texto, partes(texto), link['id'], status, erro))
    if status == 'pendente':
        from sms.tarefas import enviar_sms
        enviar_sms.delay(envio_id)
    return envio_id


def processar(envio_id: int) -> None:
    """Tarefa: envia um SMS 'pendente'. ErroPassageiro sobe (a tarefa tenta de novo); recusa vira 'falhou'."""
    db = _db()
    if db.execute_query("UPDATE sms_envios SET status = 'enviando' WHERE id = %s AND status = 'pendente'",
                        (envio_id,), return_rowcount=True) != 1:
        return   # já saiu, ou outra tarefa está enviando
    envio = db.execute_query("SELECT * FROM sms_envios WHERE id = %s", (envio_id,), fetch_one=True)
    try:
        request_id = comtele.enviar(envio['telefone'], envio['texto'], envio['origem'], str(envio_id))
    except comtele.ErroPassageiro:
        db.execute_query("UPDATE sms_envios SET status = 'pendente' WHERE id = %s", (envio_id,))
        raise
    except Exception as erro:
        db.execute_query("UPDATE sms_envios SET status = 'falhou', erro = %s WHERE id = %s",
                         (str(erro)[:500], envio_id))
        logger.error(f'[SMS] Envio {envio_id} recusado: {erro}')
        return
    db.execute_query("UPDATE sms_envios SET status = 'enviado', provedor_id = %s, enviado_em = NOW(), erro = NULL "
                     "WHERE id = %s", (request_id or None, envio_id))


def destravar(minutos: int = 60) -> int:
    """Envio parado em 'enviando' (worker caiu no meio da chamada à Comtele): vira 'falhou' com o motivo, sem reenviar
    (pode ter saído; o relatório de entrega corrige para 'entregue' se vier). Chamado pela tarefa sms.manutencao."""
    return _db().execute_query(
        "UPDATE sms_envios SET status = 'falhou', erro = 'interrompido no envio (pode ter saído)' "
        "WHERE status = 'enviando' AND criado_em < NOW() - INTERVAL %s MINUTE", (minutos,), return_rowcount=True) or 0


def desistir(envio_id: int, erro: str) -> None:
    """Esgotadas as novas tentativas de um erro passageiro."""
    _db().execute_query("UPDATE sms_envios SET status = 'falhou', erro = %s WHERE id = %s AND status = 'pendente'",
                        (f'erro passageiro: {erro}'[:500], envio_id))


# Relatório de entrega (callback). Formato do painel antigo: Sender (o nosso id interno), Status, PhoneNumber,
# StatusDate. O do painel novo ainda não foi visto: o payload cru vai para o log para ajustarmos.
_FALHAS = ('undeliver', 'reject', 'expir', 'error', 'erro', 'fail', 'falh', 'nao entreg', 'não entreg')


def status_entrega(texto) -> str | None:
    """'entregue', 'falhou' ou None (intermediário, ex.: Accepted/Processed)."""
    t = str(texto or '').lower()
    if any(f in t for f in _FALHAS):
        return 'falhou'
    if 'deliver' in t or 'entreg' in t:
        return 'entregue'
    return None


def _campo(dados: dict, *nomes):
    minusculos = {str(k).lower(): v for k, v in dados.items()}
    return next((minusculos[n.lower()] for n in nomes if minusculos.get(n.lower()) not in (None, '')), None)


def registrar_entrega(dados: dict) -> bool:
    """Aplica um aviso de entrega da Comtele. Casa pelo nosso id (custom/Sender) ou, sem ele, pelo telefone (o envio
    mais antigo das últimas 48 h ainda sem resposta da operadora — os avisos chegam na ordem dos envios). Devolve se
    achou o envio."""
    logger.info(f'[SMS] Aviso de entrega da Comtele: {dados}')
    novo = status_entrega(_campo(dados, 'status', 'dlrStatus', 'deliveryStatus'))
    if not novo:
        return False
    db = _db()
    ref = str(_campo(dados, 'custom', 'sender', 'senderName') or '')
    envio = None
    if ref.isdigit():
        envio = db.execute_query("SELECT id FROM sms_envios WHERE id = %s", (int(ref),), fetch_one=True)
    if not envio:
        numero = celular(_campo(dados, 'phoneNumber', 'receiver', 'phone', 'number'))
        if numero:
            envio = db.execute_query(
                "SELECT id FROM sms_envios WHERE telefone = %s AND status = 'enviado' "
                "AND enviado_em > NOW() - INTERVAL 48 HOUR ORDER BY id ASC LIMIT 1", (numero,), fetch_one=True)
    if not envio:
        return False
    if novo == 'entregue':
        db.execute_query("UPDATE sms_envios SET status = 'entregue', entregue_em = COALESCE(entregue_em, NOW()), "
                         "erro = NULL WHERE id = %s", (envio['id'],))
    else:
        db.execute_query("UPDATE sms_envios SET status = 'falhou', erro = %s WHERE id = %s AND status <> 'entregue'",
                         (f"operadora: {_campo(dados, 'status', 'dlrStatus')}"[:500], envio['id']))
    return True
