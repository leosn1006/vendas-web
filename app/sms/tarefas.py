"""Tarefa Celery do SMS (fila normal, em celery_app.task_routes)."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='sms.enviar', bind=True, max_retries=3)
def enviar_sms(self, envio_id):
    """Envia um SMS de sms_envios. Erro passageiro da Comtele: tenta de novo em 1, 2 e 4 min."""
    from sms import comtele, servico
    try:
        servico.processar(envio_id)
    except comtele.ErroPassageiro as exc:
        if self.request.retries >= self.max_retries:
            servico.desistir(envio_id, str(exc))
            logger.error(f'[SMS] Envio {envio_id} desistiu depois de {self.max_retries} novas tentativas: {exc}')
            return
        raise self.retry(exc=exc, countdown=60 * 2 ** self.request.retries)


@shared_task(name='sms.limpeza')
def limpeza():
    """Diária: apaga os acessos aos links curtos com mais de 90 dias (IP é dado pessoal)."""
    import links_curtos
    return links_curtos.limpar_acessos(90)


@shared_task(name='sms.manutencao')
def manutencao():
    """A cada 30 min: envio parado em 'enviando' há mais de 1 h (worker caiu no meio) vira 'falhou', sem reenviar."""
    from sms import servico
    destravados = servico.destravar(60)
    if destravados:
        logger.warning(f'[SMS] {destravados} envio(s) parado(s) em "enviando" marcado(s) como falhou')
    return destravados
