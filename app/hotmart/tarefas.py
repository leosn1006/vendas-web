"""Tarefa Celery da Hotmart (fila baixa, em celery_app.task_routes). Ver docs/HOTMART.md → "Conciliação"."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='hotmart.conciliar')
def conciliar(origem='beat'):
    """De hora em hora (beat) ou pelo botão do admin (origem='botao'): confere as vendas dos últimos
    HOTMART_DIAS_CONCILIACAO dias na API da Hotmart. Roda no worker: são dezenas de chamadas à API."""
    from hotmart import api, conciliacao
    if not api.configurada():
        return None              # sem credencial (ex.: dev sem a Hotmart): não faz nada nem enche o log
    return conciliacao.conciliar(origem=origem)
