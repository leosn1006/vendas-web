"""Venda "entrega antes, contribuição depois" no site (docs/CONTRIBUICAO_WEB.md, migration 100).

A/B na landing do WhatsApp: no clique em "Quero receber", o braço sorteado (cookie fixo por produto) decide se a
cliente vai pro WhatsApp (braço `wpp`, como sempre) ou fica no site (braço `estante`): informa o nome, ouve o áudio
da persona, informa o e-mail e recebe o livro na Estante 2 (estado 1009), que pede a contribuição — o preço do plano
padrão, pago pelo checkout v2 (/pay2?ref=<guid>), que libera os bônus.

Configuração por produto em `contribuicao_config` (percentual 0 = desligado). `?contrib=estante|wpp` força o braço
para QA, e esses cliques ficam marcados `teste=1` (fora da análise).
"""
import logging
import os
import random
import re
import time

from flask import jsonify, request

from web import web_bp

logger = logging.getLogger(__name__)

_TAG = '[CONTRIBUICAO]'
COOKIE_MAX_AGE_BRACO = 30 * 86400
_BRACOS = ('wpp', 'estante')


def _cookie_braco(produto_id: int) -> str:
    return f'ab_contrib_{int(produto_id)}'


def _ler_cookie_braco(req, produto_id: int):
    """(braço, teste) do cookie, ou (None, False). Valor: 'wpp' | 'estante' | 'wpp:teste' | 'estante:teste'."""
    valor = req.cookies.get(_cookie_braco(produto_id), '')
    braco, _, marca = valor.partition(':')
    if braco not in _BRACOS:
        return None, False
    return braco, marca == 'teste'


def sortear_braco(req, produto_id: int, config) -> dict:
    """Braço desta visita: {'braco', 'teste', 'cookie'} — `cookie` = valor a gravar (None = não mexe no cookie).

    Ordem: ?contrib= (QA) → cookie de teste → teste desligado (todo mundo no WhatsApp, o cookie antigo não vale:
    é o botão de desligar) → cookie do sorteio → sorteio novo pelo percentual."""
    forcado = req.args.get('contrib')
    if config and forcado in _BRACOS:
        return {'braco': forcado, 'teste': True, 'cookie': f'{forcado}:teste'}
    braco_cookie, teste_cookie = _ler_cookie_braco(req, produto_id)
    if config and braco_cookie and teste_cookie:
        return {'braco': braco_cookie, 'teste': True, 'cookie': None}
    percentual = int(config['percentual_estante'] or 0) if config and config['ativo'] else 0
    if percentual <= 0:
        return {'braco': 'wpp', 'teste': False, 'cookie': None}
    if braco_cookie:
        return {'braco': braco_cookie, 'teste': False, 'cookie': None}
    braco = 'estante' if random.random() * 100 < percentual else 'wpp'
    return {'braco': braco, 'teste': False, 'cookie': braco}


def _static(caminho):
    return f'/static/{caminho}' if caminho else ''


def _plano_resumo(produto_id: int):
    """Plano padrão (o que a contribuição paga): preço e o livro principal (capa/nome) para a tela de chegada."""
    from database import get_plano_venda
    plano = get_plano_venda(produto_id)
    if not plano:
        return None, None
    principal = plano['principais'][0]
    return plano, {
        'preco': float(plano['preco_promocional']),
        'livro_nome': principal.get('nome_venda') or plano.get('nome'),
        'livro_capa': principal.get('imagem_pequena') or plano.get('imagem_pequena'),
    }


def formatar_preco(valor: float) -> str:
    return f'{valor:.2f}'.replace('.', ',').replace(',00', '')


_CACHE_CONFIG_SEGUNDOS = 60
_cache_config: dict = {}


def _config_landing(produto_id: int):
    """Configuração para a landing, com cache de 60 s por processo: é a página de mais tráfego, e mudar o percentual
    (inclusive desligar) leva no máximo 1 minuto para valer."""
    from database import get_contribuicao_config
    agora = time.monotonic()
    em_cache = _cache_config.get(produto_id)
    if em_cache and agora - em_cache[0] < _CACHE_CONFIG_SEGUNDOS:
        return em_cache[1]
    config = get_contribuicao_config(produto_id)
    _cache_config[produto_id] = (agora, config)
    return config


def contexto_landing(req, produto_id: int):
    """Contexto da landing do WhatsApp: {'braco', 'teste', 'cookie', ...}. Qualquer falha devolve None e a landing
    segue como sempre (WhatsApp) — o teste nunca pode derrubar a página de mais tráfego."""
    try:
        config = _config_landing(produto_id)
        if not config:
            return None
        sorteio = sortear_braco(req, produto_id, config)
        ctx = {**sorteio, 'produto_id': produto_id}
        if sorteio['braco'] != 'estante':
            return ctx
        _, resumo = _plano_resumo(produto_id)
        if not resumo:
            logger.error(f'{_TAG} Produto #{produto_id} sem plano padrão: braço estante cai pro WhatsApp')
            return {**ctx, 'braco': 'wpp', 'cookie': None}  # não grava "estante" pra quem viu o WhatsApp
        ctx.update({
            'persona_nome': config['persona_nome'],
            'persona_foto': _static(config['persona_foto']),
            'audio_intro': _static(config['audio_intro']),
            'texto_intro': config['texto_intro'] or '',
            'checklist': [l.strip() for l in (config['checklist'] or '').splitlines() if l.strip()],
            'preco': formatar_preco(resumo['preco']),
            'livro_nome': resumo['livro_nome'],
            'livro_capa': _static(f"images/{resumo['livro_capa']}") if resumo['livro_capa'] else '',
        })
        return ctx
    except Exception as e:
        logger.exception(f'{_TAG} Erro ao montar o contexto da landing do produto #{produto_id}: {e}')
        return None


def gravar_cookie_braco(resp, produto_id: int, ctx) -> None:
    if ctx and ctx.get('cookie'):
        resp.set_cookie(_cookie_braco(produto_id), ctx['cookie'], max_age=COOKIE_MAX_AGE_BRACO, samesite='Lax')


def registrar_braco_wpp(pedido_id: int, produto_id: int) -> None:
    """Lead do WhatsApp (gravar-lide) de quem caiu no braço wpp: entra na conta do A/B. Sem cookie de braço (teste
    desligado ou visita de antes) não entra. Nunca derruba o lead."""
    try:
        braco, teste = _ler_cookie_braco(request, produto_id)
        if braco != 'wpp':
            return
        from database import registrar_contribuicao_pedido
        config = _config_landing(produto_id)
        if not config or not (teste or (config['ativo'] and config['percentual_estante'])):
            return
        registrar_contribuicao_pedido(pedido_id, produto_id, 'wpp', teste)
    except Exception as e:
        logger.error(f'{_TAG} Erro ao registrar o braço wpp do pedido #{pedido_id}: {e}')


def _pedido_contribuicao_por_guid(guid):
    from database import get_pedido_by_guid, ESTADO_CONTRIBUICAO_CLICOU, ESTADO_CONTRIBUICAO_ENTREGUE
    if not isinstance(guid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{4,40}', guid):
        return None
    pedido = get_pedido_by_guid(guid)
    if not pedido or pedido['estado_id'] not in (ESTADO_CONTRIBUICAO_CLICOU, ESTADO_CONTRIBUICAO_ENTREGUE):
        return None
    return pedido


def _nome_valido(nome) -> str:
    nome = re.sub(r'\s+', ' ', str(nome or '')).strip()
    return nome[:60] if 1 <= len(nome) else ''


@web_bp.post('/api/v1/contribuicao/iniciar')
def contribuicao_iniciar():
    """Clique em "Quero receber" no braço estante: cria o pedido da entrega (1008) com a atribuição do anúncio —
    o clique conta aqui, igual ao lead do WhatsApp, antes de ela digitar qualquer coisa.

    O guid que o navegador guardou só é reaproveitado se aquela entrega ainda NÃO aconteceu (1008: desistiu antes do
    e-mail). Entregue (1009), o clique cria um pedido novo: pode ser outra pessoa no mesmo celular (mãe e filho), e
    reaproveitar trocaria o nome e o e-mail do pedido do outro. Se for a mesma pessoa, o /entregar a devolve para a
    Estante dela (mesmo e-mail da entrega anterior deste navegador)."""
    from database import (get_contribuicao_config, get_plano_venda, criar_pedido_contribuicao,
                          registrar_contribuicao_pedido, gravar_clique_pedido, ESTADO_CONTRIBUICAO_CLICOU)
    from lead_incluir import atribuicao_do_clique
    from meta_clique import ip_e_navegador, registrar_campanha_meta

    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({'erro': 'corpo'}), 400
    try:
        produto_id = int(body.get('produto_id'))
    except (TypeError, ValueError):
        return jsonify({'erro': 'produto'}), 400
    # Só quem foi sorteada pro braço estante, com o teste ligado (ou QA): página antiga em cache, aba esquecida ou
    # robô não criam entrega nem entram na conta do A/B. A página cai pro WhatsApp.
    config = get_contribuicao_config(produto_id)
    braco, teste = _ler_cookie_braco(request, produto_id)
    if not config or braco != 'estante' or not (teste or (config['ativo'] and config['percentual_estante'])):
        return jsonify({'erro': 'indisponivel'}), 409
    existente = _pedido_contribuicao_por_guid(body.get('guid'))
    if existente and existente['produto_id'] == produto_id and existente['estado_id'] == ESTADO_CONTRIBUICAO_CLICOU:
        # Clicou de novo (mesma aba/aparelho): mesmo pedido, mas o clique conta — no braço wpp cada clique é um lead.
        # Clique novo de anúncio (gclid/fbc na URL): vale o último, como no lead novo do WhatsApp.
        try:
            from database import contar_clique_contribuicao, atualizar_clique_contribuicao
            contar_clique_contribuicao(existente['id'])
            atrib = atribuicao_do_clique(body)
            if atrib.get('gclid') or atrib.get('wbraid') or atrib.get('gbraid') or atrib.get('clique'):
                atualizar_clique_contribuicao(existente['id'], atrib)
        except Exception as e:
            logger.error(f"{_TAG} Erro ao contar o clique repetido do pedido #{existente['id']}: {e}")
        return jsonify({'guid': existente['guid']}), 200
    plano = get_plano_venda(produto_id)
    if not plano:
        return jsonify({'erro': 'indisponivel'}), 409
    try:
        atrib = atribuicao_do_clique(body)
        pedido = criar_pedido_contribuicao(produto_id, '', atrib, plano)
        registrar_contribuicao_pedido(pedido['id'], produto_id, 'estante', teste)
        try:
            ip, navegador = ip_e_navegador(request)
            gravar_clique_pedido(pedido['id'], ip=ip, navegador=navegador,
                                 fbc=atrib['clique']['fbc'] if atrib['clique'] else None)
            if atrib['clique']:
                registrar_campanha_meta(produto_id, atrib['clique']['campaignid'], venda_web=False)
        except Exception as e:
            logger.error(f"{_TAG} Erro ao gravar o clique do pedido #{pedido['id']}: {e}")
        logger.info(f"{_TAG} Pedido #{pedido['id']} (produto {produto_id}) criado no braço estante")
        return jsonify({'guid': pedido['guid']}), 200
    except Exception as e:
        logger.exception(f'{_TAG} Erro ao iniciar a contribuição do produto #{produto_id}: {e}')
        return jsonify({'erro': 'interno'}), 500


@web_bp.post('/api/v1/contribuicao/nome')
def contribuicao_nome():
    from database import definir_nome_contribuicao
    body = request.get_json(force=True, silent=True) or {}
    pedido = _pedido_contribuicao_por_guid(body.get('guid'))
    nome = _nome_valido(body.get('nome'))
    if not pedido or not nome:
        return jsonify({'erro': 'nome'}), 400
    definir_nome_contribuicao(pedido['id'], nome)
    return jsonify({'ok': True}), 200


@web_bp.post('/api/v1/contribuicao/entregar')
def contribuicao_entregar():
    """Informou o e-mail: entrega o livro (1008 → 1009), manda o e-mail com o link da Estante e devolve a URL dela.

    O e-mail é digitado sem verificação, então este é um jeito de fazer o Gmail do admin@ mandar e-mail para qualquer
    endereço: o "seu livro chegou" sai só na PRIMEIRA entrega do pedido (corrigiu o e-mail depois → "Reenviar o
    e-mail" da Estante, que tem limite; o e-mail de uma entrega feita não muda) e passa pelos limites por IP e global
    (envios_email_site). Barrado, ela
    recebe o livro na tela do mesmo jeito; só o e-mail não sai."""
    from database import (entregar_pedido_contribuicao, reservar_envio_email, juntar_clique_na_entrega_anterior,
                          ESTADO_CONTRIBUICAO_ENTREGUE)
    from web.email_validacao import validar_email

    body = request.get_json(force=True, silent=True) or {}
    pedido = _pedido_contribuicao_por_guid(body.get('guid'))
    if not pedido:
        return jsonify({'erro': 'pedido'}), 404
    email = str(body.get('email') or '').strip().lower()
    checagem = validar_email(email)
    if not checagem['valido']:
        return jsonify({'erro': 'email', 'motivo': checagem['motivo'], 'sugestao': checagem.get('sugestao')}), 400
    nome = _nome_valido(body.get('nome'))
    # Mesma pessoa voltando: uma das entregas anteriores DESTE navegador (os guids que a página guardou, nunca uma
    # busca pelo e-mail no banco — e-mail digitado não prova nada) tem o mesmo e-mail → volta para a Estante dela.
    anterior = _entrega_anterior_com_email(body.get('anteriores'), pedido, email)
    if anterior:
        try:
            juntar_clique_na_entrega_anterior(pedido['id'], anterior['id'])
        except Exception as e:
            logger.error(f"{_TAG} Erro ao juntar o clique {pedido['id']} na entrega {anterior['id']}: {e}")
        return jsonify({'url': f"/pedido2/{anterior['guid']}", 'guid': anterior['guid']}), 200
    url = {'url': f"/pedido2/{pedido['guid']}?chegou=1", 'guid': pedido['guid']}
    if not entregar_pedido_contribuicao(pedido['id'], nome, email):
        # Já entregue (voltou nesta página, ou dois toques): mesmo e-mail → a Estante; outro e-mail → a página
        # recomeça com um pedido novo (o e-mail de uma entrega feita nunca muda: ver entregar_pedido_contribuicao).
        atual = _pedido_contribuicao_por_guid(pedido['guid'])
        if atual and atual['estado_id'] == ESTADO_CONTRIBUICAO_ENTREGUE and (atual.get('email') or '').lower() == email:
            return jsonify(url), 200
        return jsonify({'erro': 'ja_entregue'}), 409
    _enviar_email_entrega(pedido['id'], reservar_envio_email)  # só quem fez a entrega (1008 → 1009) manda
    return jsonify(url), 200


def _entrega_anterior_com_email(guids, pedido: dict, email: str):
    """A entrega (1009) do mesmo produto, entre as que este navegador já recebeu (até 5), feita com este e-mail."""
    from database import ESTADO_CONTRIBUICAO_ENTREGUE
    if not isinstance(guids, list):
        return None
    for g in guids[:5]:
        anterior = _pedido_contribuicao_por_guid(g)
        if (anterior and anterior['id'] != pedido['id'] and anterior['estado_id'] == ESTADO_CONTRIBUICAO_ENTREGUE
                and anterior['produto_id'] == pedido['produto_id'] and (anterior.get('email') or '').lower() == email):
            return anterior
    return None


def _limite_entrega_hora() -> int:
    try:
        return max(1, int(os.getenv('CONTRIBUICAO_ENTREGA_LIMITE_HORA', '200')))
    except ValueError:
        return 200


def _enviar_email_entrega(pedido_id: int, reservar) -> None:
    from database import desfazer_envio_email
    from meta_clique import ip_e_navegador
    try:
        motivo = reservar('entrega_contribuicao', pedido_id, ip_e_navegador(request)[0], _limite_entrega_hora())
    except Exception as e:
        logger.error(f'{_TAG} Erro ao checar o limite do e-mail de entrega do pedido #{pedido_id}: {e}')
        return
    if motivo != 'ok':
        nivel = logger.error if motivo == 'global' else logger.warning
        nivel(f'{_TAG} E-mail de entrega do pedido #{pedido_id} não enviado (limite: {motivo})')
        return
    try:
        import tasks
        tasks.enviar_email_contribuicao_entrega.delay(pedido_id)
    except Exception as e:
        logger.error(f"{_TAG} Erro ao agendar o e-mail de entrega do pedido #{pedido_id}: {e}")
        desfazer_envio_email('entrega_contribuicao', pedido_id)


@web_bp.post('/api/v1/contribuicao/evento')
def contribuicao_evento():
    """Marco do funil vindo da página (sendBeacon). Sempre 204: nunca atrapalha a cliente."""
    from database import marcar_marco_contribuicao, MARCOS_CONTRIBUICAO_PAGINA
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict) or body.get('marco') not in MARCOS_CONTRIBUICAO_PAGINA:
        return '', 204
    try:
        pedido = _pedido_contribuicao_por_guid(body.get('guid'))
        if pedido:
            marcar_marco_contribuicao(pedido['id'], body['marco'])
    except Exception as e:
        logger.error(f'{_TAG} Erro ao gravar o marco {body.get("marco")}: {e}')
    return '', 204


def contexto_estante(pedido: dict, lembrete: bool = False):
    """Camada de contribuição da Estante 2: só para a entrega (1009) que ainda não foi paga. None = Estante normal.
    Nunca derruba a Estante."""
    try:
        from database import (ESTADO_CONTRIBUICAO_ENTREGUE, get_contribuicao_config, contribuicao_paga,
                              marcar_marco_contribuicao)
        from web.links import link_checkout
        if pedido.get('estado_id') != ESTADO_CONTRIBUICAO_ENTREGUE:
            return None
        config = get_contribuicao_config(pedido['produto_id'])
        # Só o vínculo (por_email=False): o e-mail da entrega não é verificado — ver contribuicao_paga.
        if not config or contribuicao_paga(pedido, por_email=False):
            return None
        plano, resumo = _plano_resumo(pedido['produto_id'])
        if not plano:
            return None
        marcar_marco_contribuicao(pedido['id'], 'estante_em')
        usar_lembrete = lembrete and config['audio_lembrete']
        return {
            'guid': pedido['guid'],
            'persona_nome': config['persona_nome'],
            'persona_foto': _static(config['persona_foto']),
            'audio': _static(config['audio_lembrete'] if usar_lembrete else config['audio_cobranca']),
            'texto': (config['texto_lembrete'] if usar_lembrete else config['texto_cobranca']) or '',
            'preco': formatar_preco(resumo['preco']),
            'link': link_checkout(pedido['produto_id'], plano, v2=True, ref=pedido['guid']),
        }
    except Exception as e:
        logger.exception(f"{_TAG} Erro ao montar a contribuição da Estante do pedido #{pedido.get('id')}: {e}")
        return None


def eh_origem_contribuicao(pedido_origem: dict | None, produto_id: int) -> bool:
    """O checkout v2 é a contribuição de uma entrega (texto "Sua contribuição", herda o clique, sai do follow-up):
    veio da Estante de uma entrega 1009 ainda não paga e é do MESMO produto. O cross-sell de outro produto (que a
    Estante volta a mostrar depois do pagamento) é uma compra normal."""
    from database import ESTADO_CONTRIBUICAO_ENTREGUE, contribuicao_paga
    if not pedido_origem or pedido_origem.get('estado_id') != ESTADO_CONTRIBUICAO_ENTREGUE:
        return False
    if pedido_origem.get('produto_id') != produto_id:
        return False
    try:
        return not contribuicao_paga(pedido_origem, por_email=False)
    except Exception as e:
        logger.error(f"{_TAG} Erro ao checar a contribuição da entrega #{pedido_origem.get('id')}: {e}")
        return False
