"""SMS do sistema (Comtele), genérico para qualquer produto. Ver docs/SMS.md.

  config.py   .env (chave, rota, trava do dev, custo)
  texto.py    sem acento e no máximo 160 caracteres (1 parte)
  comtele.py  cliente da API
  servico.py  enviar (número, link curto, registro em sms_envios) e o relatório de entrega
  tarefas.py  a tarefa Celery que fala com a Comtele
  rotas.py    webhook de entrega
O link curto (/m/<codigo>) fica em links_curtos.py, também genérico.
"""
import logging


def registrar(flask_app):
    """Registra o webhook de entrega e o link curto. Um problema aqui nunca derruba o resto do site."""
    try:
        import links_curtos
        flask_app.register_blueprint(links_curtos.bp)
        from sms.rotas import bp
        flask_app.register_blueprint(bp)
    except Exception as e:
        logging.getLogger(__name__).error(f'[SMS] Módulo NÃO carregado: {e}')
