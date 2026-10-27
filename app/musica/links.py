"""Endereços das páginas da Música (para e-mails, QR code e tarefas, que rodam sem requisição)."""
from musica import config


def base(dominio: str | None) -> str:
    if config.URL_PUBLICA:
        return config.URL_PUBLICA
    return f'https://{dominio}' if dominio else ''


def previa(musica: dict) -> str:
    """Prévia (antes de pagar): o funil da música."""
    return f"{base(musica.get('dominio'))}/musica/p/{musica['token']}"


def checkout(musica: dict) -> str:
    """Checkout da música, reabrindo o pedido com o PIX ainda válido (se houver), montado por web.links.link_checkout
    (CLAUDE.md). Vai só para a própria cliente (lembrete), então pode levar o token."""
    from web.links import link_checkout
    plano = {'slug': musica['pedido_aberto_plano'], 'padrao': False} if musica.get('pedido_aberto_plano') else None
    return base(musica.get('dominio')) + link_checkout(musica['produto_id'], plano, pedido=musica.get('pedido_aberto_id'),
                                                       musica=musica['token'])


def sem_lembretes(musica: dict) -> str:
    """Link do rodapé dos lembretes: "não quero mais receber"."""
    return f"{base(musica.get('dominio'))}/musica/p/{musica['token']}/sem-lembretes"


def presente(musica: dict) -> str:
    """Página do presente (QR code e e-mail para quem recebe): só a música, sem dados de quem comprou."""
    return f"{base(musica.get('dominio'))}/musica/m/{musica['token']}"


def compra(guid: str, dominio: str | None) -> str:
    """Área de quem comprou (pelo guid do pedido pago): fotos do videoclipe, QR, entrega por e-mail."""
    return f'{base(dominio)}/musica/compra/{guid}'


def webhook(nome_gerador: str) -> str | None:
    return f'{config.URL_PUBLICA}/musica/webhook/{nome_gerador}' if config.URL_PUBLICA else None
