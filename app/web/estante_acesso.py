"""
"Guarde seu livro" na Estante 2 (/pedido2/<guid>): para a cliente não perder o acesso se fechar a aba e o e-mail não
chegar. A instrução só funciona se ela vir ANTES de perder a aba, então o bloco oferece ações, não texto:

  - baixar o livro (o PDF no aparelho dispensa e-mail e aba);
  - mandar o link da Estante para o próprio WhatsApp (contato "(Você)", o "Conversar comigo" do WhatsApp);
  - ver para onde o e-mail foi (mascarado) e pedir o reenvio.

Reenvio (POST /api/v1/estante/<guid>/reenviar-email): sempre para o e-mail já gravado no pedido (a tela não tem
campo de e-mail, então não serve para mandar e-mail a terceiros), só para pedidos do site (pago 1000 ou entrega da
contribuição 1009), com limites gravados no banco (database.reservar_envio_email, migration 101). O teto global
por hora protege a cota de envio do Gmail do admin@: estourar a cota para as entregas de todos os produtos.
"""
import logging
import os

from flask import jsonify, request

from web import web_bp

logger = logging.getLogger(__name__)
_TAG = '[ESTANTE-REENVIO]'

ESTADOS_REENVIO = (1000, 1009)  # pago no site · entrega da contribuição (o e-mail sai do fluxo da contribuição)


def _limite_global_hora() -> int:
    try:
        return max(1, int(os.getenv('REENVIO_ESTANTE_LIMITE_HORA', '60')))
    except ValueError:
        return 60


def mascarar_email(email: str) -> str:
    """maria.silva@gmail.com -> m•••@gmail.com (ela reconhece o próprio e-mail; quem só tem o link não lê ele)."""
    usuario, _, dominio = (email or '').strip().partition('@')
    if not usuario or not dominio:
        return ''
    return f'{usuario[0]}•••@{dominio}'


def pode_reenviar(pedido: dict) -> bool:
    return bool(pedido and pedido.get('email') and pedido.get('fluxo_inicial') == 'web'
                and pedido.get('estado_id') in ESTADOS_REENVIO)


def contexto_guardar(pedido: dict, itens: list, guid: str, base_url: str) -> dict | None:
    """Dados do bloco "Guarde seu livro". None se não há livro liberado (nada para guardar)."""
    liberados = [i for i in itens if not i.get('bloqueado')]
    if not liberados:
        return None
    # Um livro: botão grande com o nome dele. Vários: sem botão (o celular baixa um arquivo por toque, e "baixar
    # meu livro" baixando só um de quatro engana) — a frase manda pro "Baixar" de cada card.
    principal = liberados[0] if len(liberados) == 1 else None
    return {
        'download': f"/pedido/{principal['guid_pedido']}/arquivo/{principal['id']}?download=1" if principal else '',
        'livro': principal.get('nome') or '' if principal else '',
        'varios': principal is None,
        'link': f"{base_url.rstrip('/')}/pedido2/{guid}",
        'email': mascarar_email(pedido.get('email')) if pode_reenviar(pedido) else '',
    }


def _ip() -> str:
    from meta_clique import ip_e_navegador  # mesma fonte do IP da entrega da contribuição (mesmo limite por IP)
    return ip_e_navegador(request)[0] or ''


@web_bp.post('/api/v1/estante/<guid>/reenviar-email')
def estante_reenviar_email(guid):
    import database as db
    pedido = db.get_pedido_by_guid(guid) if guid and len(guid) <= 64 else None
    if not pode_reenviar(pedido):
        return jsonify({'erro': 'indisponivel'}), 404
    motivo = db.reservar_envio_email('reenvio_estante', pedido['id'], _ip(), _limite_global_hora())
    if motivo != 'ok':
        if motivo == 'global':
            # Freio de emergência: muitos reenvios na última hora (abuso ou bug). Ninguém mais recebe até baixar.
            logger.error(f'{_TAG} ⚠️ Teto global de reenvios por hora atingido ({_limite_global_hora()}) — '
                         f'reenvio do pedido #{pedido["id"]} recusado. Verificar abuso.')
        else:
            logger.info(f'{_TAG} Reenvio do pedido #{pedido["id"]} recusado: {motivo}')
        return jsonify({'erro': motivo}), 429
    try:
        import tasks
        tasks.reenviar_email_estante.delay(pedido['id'])
    except Exception as e:
        # Nem foi pra fila: devolve a vaga (senão ela fica barrada pelo limite sem ter recebido nada).
        logger.error(f'{_TAG} Erro ao agendar o reenvio do pedido #{pedido["id"]}: {e}')
        db.desfazer_envio_email('reenvio_estante', pedido['id'])
        return jsonify({'erro': 'global'}), 503
    logger.info(f'{_TAG} Reenvio do pedido #{pedido["id"]} agendado')
    return jsonify({'ok': True, 'email': mascarar_email(pedido['email'])})
