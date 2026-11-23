"""Checkout da Hotmart (vendas de fora do Brasil; começa pela Música do México). Ver docs/HOTMART.md.

  config.py       .env (hottok, prazo de repasse)
  leitura.py      o aviso (webhook 2.0) → dict com os campos que usamos
  cambio.py       valor da moeda da cliente → reais (BRL, conversão da Hotmart, PTAX, última taxa)
  repositorio.py  SQL (pagamento_hotmart, pagamento_hotmart_eventos, hotmart_ofertas) e o pedido
  servico.py      as regras: qual evento faz o quê com o pedido
  rotas.py        POST /hotmart/webhook
"""
import logging


def registrar(flask_app):
    """Registra o webhook. Um problema aqui nunca derruba o resto do site."""
    try:
        from hotmart.rotas import bp
        flask_app.register_blueprint(bp)
    except Exception as e:
        logging.getLogger(__name__).error(f'[HOTMART] Módulo NÃO carregado: {e}')
