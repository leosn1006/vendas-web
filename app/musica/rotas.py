"""Rotas da Música (/musica/...): HTTP fino → casos de uso. Erros sempre jsonify(...), 4xx — nunca abort()
(o handler global transforma em 500 e avisa no WhatsApp). POST que grava exige Origin/Referer do próprio host.

Páginas: /musica/ (landing, ?ocasiao=), /musica/criar (quiz), /musica/p/<token> (letra, espera e prévia),
/musica/compra/<guid> (quem comprou), /musica/m/<token> (o presente: QR code e e-mail apontam para cá).

Idiomas (musica/idiomas.py): o mesmo blueprint é registrado uma vez por idioma (/musica = pt-BR, /mx/cancion =
es-MX). g.idioma = o do endereço; nas páginas e na API de uma música, o DA MÚSICA. Links sempre por _rota() (o
blueprint do idioma), textos por t() (conteudo/<idioma>/textos.json).
"""
import logging
import re
from pathlib import Path

import requests
from flask import Blueprint, g, jsonify, make_response, redirect, render_template, request, send_file, url_for
from markupsafe import Markup, escape

from apps._nucleo.formato import reais
from musica import casos_de_uso as uc
from musica import config, idiomas
from musica.casos_de_uso import Recusa
from musica.dominio import quiz as _quiz
from musica.dominio import regras
from musica.dominio.recursos import ENTREGA_EMAIL, QRCODE, VIDEOCLIPE
from musica.fabrica import servicos

logger = logging.getLogger(__name__)

bp = Blueprint('musica', __name__, url_prefix='/musica', template_folder='templates', static_folder='static',
               static_url_path='/static')

ATUALIZADO_LEGAL = '21 de novembro de 2026'


# ================================================================ utilidades

def _ip():
    return (request.headers.get('X-Real-IP') or request.remote_addr or '').strip()


def _host():
    return (request.headers.get('X-Forwarded-Host') or request.host or '').split(':')[0].lower()


def _origem_confiavel():
    from apps._nucleo.auth import origem_confiavel
    return origem_confiavel()


# ================================================================ idiomas

@bp.before_request
def _idioma_do_endereco():
    g.idioma = idiomas.do_blueprint(request.blueprint)
    # Os endereços traduzidos (/crear, /terminos...) só valem no idioma deles, e os originais não valem onde há
    # tradução: nada de /musica/crear nem /mx/cancion/criar (conteúdo duplicado com o caminho no idioma errado).
    nome = (request.endpoint or '').rsplit('.', 1)[-1]
    traduzidos = idiomas.cfg(g.idioma).get('endpoints', {})
    de_outro_idioma = {e for i, c in idiomas.IDIOMAS.items() for e in c.get('endpoints', {}).values() if i != g.idioma}
    if nome in traduzidos or (nome in de_outro_idioma and nome not in traduzidos.values()):
        return _nao_encontrada()


def _idioma():
    return getattr(g, 'idioma', None) or idiomas.IDIOMA_PADRAO


def _usar_idioma_da_musica(musica):
    """Página ou API de uma música: vale o idioma dela (gravado na criação), não o do endereço."""
    if musica:
        g.idioma = idiomas.valido(musica.get('idioma'))
    return musica


def _musica_do_token(token):
    """A música do token (só o formato válido vai ao banco), já com o idioma dela valendo para a resposta."""
    return _usar_idioma_da_musica(servicos().repositorio.por_token(token) if re.fullmatch(r'[0-9a-f]{32}', token) else None)


def _rota(nome, **valores):
    """url_for no blueprint do idioma atual (ex.: _rota('criar') = /musica/criar ou /mx/cancion/crear... o caminho
    é o mesmo, só muda o prefixo)."""
    cfg = idiomas.cfg(_idioma())
    return url_for(f"{cfg['blueprint']}.{cfg.get('endpoints', {}).get(nome, nome)}", **valores)


def _texto(chave, **valores):
    return idiomas.texto(_idioma(), chave, **valores)


def _quiz_atual():
    return _quiz.do_idioma(_idioma())


def _recusa(r: Recusa):
    """A mensagem dos casos de uso (em português) no idioma da tela: textos.json → "recusas" (texto pt → texto do
    idioma); sem tradução, vai a original."""
    textos = idiomas.textos(_idioma())
    traduzida = textos.get('recusas', {}).get(r.mensagem)
    if traduzida is None:   # mensagem com número (f-string): "recusas_padroes" = [[regex, texto com {0}...], ...]
        for padrao, modelo in textos.get('recusas_padroes', []):
            try:   # um padrão mal escrito no textos.json nunca derruba a mensagem de erro (vai a original)
                achou = re.fullmatch(padrao, r.mensagem)
                if achou:
                    traduzida = modelo.format(*achou.groups())
                    break
            except (re.error, IndexError, KeyError):
                logger.error(f'[MUSICA] Padrão de tradução inválido em recusas_padroes ({_idioma()}): {padrao!r}')
    return jsonify(erro=traduzida or r.mensagem), r.status


def _nao_encontrada():
    return render_template('musica/legal.html', pagina='nao_encontrada', atualizado=_atualizado_legal()), 404


def _atualizado_legal():
    return _texto('legal.atualizado_em') if _idioma() != idiomas.IDIOMA_PADRAO else ATUALIZADO_LEGAL


def _turnstile_ok(token):
    if not config.TURNSTILE_SECRET:
        return True
    try:
        r = requests.post('https://challenges.cloudflare.com/turnstile/v0/siteverify',
                          data={'secret': config.TURNSTILE_SECRET, 'response': token or '', 'remoteip': _ip()},
                          timeout=10)
        return r.json().get('success') is True
    except requests.RequestException:
        return False


_CACHE_PRODUTO = {}   # idioma -> {'quando', 'produto'}


def _produto(idioma=None):
    """O produto da Música no idioma (do banco, ver RepositorioMysql.produto_musica), guardado por 60 s: toda página
    usa. Sem `idioma`: o da requisição."""
    import time
    idioma = idiomas.valido(idioma or _idioma())
    cache = _CACHE_PRODUTO.setdefault(idioma, {'quando': 0.0, 'produto': None})
    if time.time() - cache['quando'] > 60:
        try:
            cache['produto'] = servicos().repositorio.produto_musica(idioma)
        except Exception as e:
            logger.error(f'[MUSICA] Erro ao buscar o produto da Música ({idioma}): {e}')
        cache['quando'] = time.time()
    return cache['produto']


def _pid():
    return (_produto() or {}).get('id') or 0


def _empresa():
    """Razão social, CNPJ e e-mail para os termos e a privacidade."""
    produto = _produto()
    try:
        empresa = servicos().repositorio.empresa_do_produto(produto)
    except Exception:
        empresa = {}
    from web.checkout import formatar_cnpj
    cnpj = formatar_cnpj(empresa.get('cnpj'))
    return {'razao_social': empresa.get('razao_social') or '', 'cnpj': cnpj,
            'email_suporte': (produto or {}).get('email_remetente') or empresa.get('email') or ''}


def _planos_a_venda():
    """Os planos da Música à venda (vitrine, sem renovação) do produto do idioma, do mais barato ao mais caro:
    [{slug, nome, descricao, preco, videoclipe, plano}]."""
    from database import get_plano_venda, listar_planos_produto, preco_cobrado_plano
    from musica.dominio.recursos import plano_vende_musica
    planos = []
    produto_id = _pid()
    for p in listar_planos_produto(produto_id):
        if not p['ativo'] or p.get('renovacao'):
            continue
        plano = get_plano_venda(produto_id, p['slug'])
        if not plano_vende_musica(plano):
            continue
        planos.append({'slug': plano['slug'], 'nome': plano['nome'], 'descricao': plano.get('descricao') or '',
                       'preco': preco_cobrado_plano(produto_id, plano),
                       'videoclipe': any(i.get('recurso') == VIDEOCLIPE for i in plano['principais']),
                       'plano': plano})
    return sorted(planos, key=lambda x: x['preco'])


def _oferta_ultima_chance(planos, token):
    """O popup "última chance" da prévia: quando ela escolhe o plano padrão (só a música), oferece uma vez o
    plano mais caro que tenha desconto de oferta (admin → plano → "Desconto de oferta"), desde que o preço com
    desconto continue acima do padrão. O desconto vai num link assinado (web/oferta.py) que o checkout revalida.
    None = sem oferta (o clique vai direto ao checkout); um erro aqui nunca derruba a prévia."""
    try:
        from web.oferta import oferta_do_plano
        padrao = next((p for p in planos if p['plano'].get('padrao')), None)
        if not padrao:
            return None
        for alvo in reversed([p for p in planos if not p['plano'].get('padrao')]):   # do mais caro ao mais barato
            o = oferta_do_plano(alvo['plano'], alvo['preco'], musica=token)
            if o and o['preco_promocional'] > padrao['preco']:
                return {'nome': alvo['nome'], 'videoclipe': alvo['videoclipe'], 'preco_cheio': reais(o['preco_cheio']),
                        'preco': reais(o['preco_promocional']), 'economia': reais(o['economia']), 'link': o['href'],
                        'expira': o['expira']}
    except Exception:
        logger.exception('[MUSICA] Falha ao montar a oferta da prévia')
    return None


def _t(chave, **valores):
    """Frase do textos.json do idioma para os templates. A frase é conteúdo nosso (pode ter HTML, não é escapada); os
    valores trocados nas {marcas} são escapados (podem vir da cliente ou do banco), salvo os que já vierem Markup."""
    texto = Markup(idiomas.texto(_idioma(), chave))
    for nome, valor in valores.items():
        texto = texto.replace('{' + nome + '}', escape(valor))
    return texto


def _outros_idiomas():
    """O seletor de país do rodapé da landing: os outros idiomas com a Música à venda (sem produto, não aparece)."""
    return [{'bandeira': c['bandeira'], 'pais': c['pais'], 'lang': c['html_lang'], 'link': url_for(f"{c['blueprint']}.inicio")}
            for i, c in idiomas.IDIOMAS.items() if i != _idioma() and c.get('no_seletor', True) and _produto(i)]


@bp.context_processor
def _variaveis_das_paginas():
    produto = _produto()
    marca = ((produto or {}).get('email_nome_remetente') or (produto or {}).get('nome')
             or idiomas.texto(_idioma(), 'geral.marca_padrao'))
    return {'marca': marca, 'turnstile_site_key': config.TURNSTILE_SITE_KEY, 'dominio_cfg': _empresa(),
            # só promete WhatsApp com o envio ligado (geral e do idioma: no México, desligado até os templates em es)
            'produto_id': _pid(), 'whatsapp_ativo': idiomas.whatsapp_ativo(_idioma()),
            'idioma': _idioma(), 'idioma_cfg': idiomas.cfg(_idioma()), 'textos': idiomas.textos(_idioma()),
            't': _t, 'rota': _rota, 'outros_idiomas': _outros_idiomas}


def _com_cookie_do_funil(resposta, pedido_id):
    from web.checkout import COOKIE_MAX_AGE_FUNIL
    if pedido_id:
        resposta.set_cookie(f'pedido_web_{_pid()}', str(pedido_id), max_age=COOKIE_MAX_AGE_FUNIL)
    return resposta


def _pedido_origem():
    """O pedido do cookie do funil, só se ainda é um rascunho (1003/1004) deste produto: o valor vem do navegador
    (um id inexistente quebraria a FK; o de uma compra de outra pessoa levaria o GCLID dela)."""
    cookie = request.cookies.get(f'pedido_web_{_pid()}', '')
    if not cookie.isdigit():
        return None
    from database import get_pedido_nao_finalizado
    pedido = get_pedido_nao_finalizado(int(cookie), _pid())
    return pedido['id'] if pedido else None


def _rascunho_do_funil():
    """O pedido rascunho (1004) desta visita: guarda a campanha (GCLID) desde a primeira página do anúncio."""
    from web.checkout import rastrear_visita_funil
    try:
        return rastrear_visita_funil(request, _pid(), estado_novo=1004)
    except Exception as e:
        logger.error(f'[MUSICA] Erro ao registrar a visita no funil: {e}')
        return None


def _quem_da_landing():
    """Os botões "Pra quem é a música?" do topo da landing: as mesmas opções da 1ª pergunta do quiz e, por ocasião,
    as relações que combinam com ela (a página de uma ocasião só mostra quem combina)."""
    quiz = _quiz_atual()
    return {'opcoes_quem': next(p['opcoes'] for p in quiz.PERGUNTAS if p['chave'] == 'para_quem'),
            'relacoes_por_ocasiao': quiz.relacoes_por_ocasiao()}


# =================================================================== páginas

def _regras_do_navegador(quiz):
    """config_do_navegador + o que o JS do quiz precisa saber do idioma sem depender do texto das opções."""
    return {**quiz.config_do_navegador(), 'outra_pessoa': quiz.OUTRA_PESSOA, 'outra_ocasiao': quiz.OUTRA_OCASIAO,
            'vozes_padrao': quiz.VOZES_PADRAO}


@bp.get('/')
def inicio():
    if not _produto():
        return _nao_encontrada()
    pedido_id = _rascunho_do_funil()
    planos = _planos_a_venda()
    preco_texto = reais(planos[0]['preco']) if planos else ''
    # ?ocasiao= (Brasil) ou ?ocasion= (anúncios em espanhol): a página de ocasião da landing
    ocasiao = request.args.get('ocasiao') or request.args.get('ocasion') or ''
    resposta = make_response(render_template('musica/inicio.html', ocasiao=ocasiao,
                                             preco_texto=preco_texto, **_quem_da_landing()))
    return _com_cookie_do_funil(resposta, pedido_id)


@bp.get('/criar')
@bp.get('/crear', endpoint='crear')   # es: "criar" é criar filhos
def criar():
    if not _produto():
        return _nao_encontrada()
    pedido_id = _rascunho_do_funil()   # anúncio que leva direto ao quiz também registra a campanha
    sub = idiomas.cfg(_idioma())['pasta_amostras']   # amostras do "aperte o play" de cada idioma
    pasta = Path(bp.static_folder) / 'estilos' / sub
    amostras = {a.stem: url_for('musica.static', filename=f'estilos/{sub}{a.name}') for a in sorted(pasta.glob('*.mp3'))}
    quiz = _quiz_atual()
    resposta = make_response(render_template('musica/quiz.html', perguntas=quiz.PERGUNTAS, amostras=amostras,
                                             regras_quiz=_regras_do_navegador(quiz)))
    return _com_cookie_do_funil(resposta, pedido_id)


@bp.get('/p/<token>')
def pagina_previa(token):
    """Letra, espera e prévia (o funil depois do quiz). Música já comprada vai para a página do presente."""
    musica = _musica_do_token(token)
    if not musica:
        return _nao_encontrada()
    if musica['liberada_em']:
        return redirect(_rota('pagina_presente', token=token))
    return render_template('musica/pedido.html', token=token)


@bp.route('/p/<token>/sem-lembretes', methods=['GET', 'POST'])
def sem_lembretes(token):
    """Link do rodapé dos lembretes. O GET só pergunta (leitores de e-mail abrem os links sozinhos para checar
    segurança — um GET que já parasse os lembretes pararia sem ela pedir); o botão faz o POST."""
    if not re.fullmatch(r'[0-9a-f]{32}', token) or not _usar_idioma_da_musica(servicos().repositorio.por_token(token)):
        return _nao_encontrada()
    if request.method == 'POST':
        uc.parar_lembretes(servicos(), token)
        return render_template('musica/legal.html', pagina='sem_lembretes_ok', atualizado=_atualizado_legal())
    return render_template('musica/legal.html', pagina='sem_lembretes', token=token, atualizado=_atualizado_legal())


@bp.get('/m/<token>')
def pagina_presente(token):
    """O presente: ouvir, baixar e ver o videoclipe. Sem dados de quem comprou, sem cross-sell."""
    try:
        musica, recursos = uc.musica_liberada(servicos(), token)
    except Recusa:
        return _nao_encontrada()
    _usar_idioma_da_musica(musica)
    video = VIDEOCLIPE in recursos and musica['video_status'] == 'pronto'
    return render_template('musica/musica.html', musica=musica, para=regras.para_quem(musica['respostas'], _texto('geral.sem_nome')),
                           letra_texto=regras.para_leitura(musica['letra_exibicao'], _texto('geral.refrao')), video=video)


@bp.get('/m/<token>/<int:numero>.mp3')
def musica_completa(token, numero):
    try:
        musica, _ = uc.musica_liberada(servicos(), token)
    except Recusa:
        return _nao_encontrada()
    arquivo = servicos().arquivos.completa(token, numero)
    if numero not in (1, 2) or not arquivo.exists():
        return _nao_encontrada()
    return send_file(arquivo, mimetype='audio/mpeg', as_attachment=request.args.get('baixar') == '1',
                     download_name=f"{musica['titulo'] or 'musica'} - versao {numero}.mp3", conditional=True, max_age=0)


@bp.get('/m/<token>/videoclipe.mp4')
def videoclipe(token):
    try:
        musica, recursos = uc.musica_liberada(servicos(), token)
    except Recusa:
        return _nao_encontrada()
    arquivo = servicos().arquivos.videoclipe(token)
    if VIDEOCLIPE not in recursos or musica['video_status'] != 'pronto' or not arquivo.exists():
        return _nao_encontrada()
    return send_file(arquivo, mimetype='video/mp4', as_attachment=request.args.get('baixar') == '1',
                     download_name=f"{musica['titulo'] or 'videoclipe'}.mp4", conditional=True, max_age=0)


@bp.get('/m/<token>/videoclipe.jpg')
def capa_video(token):
    try:
        uc.musica_liberada(servicos(), token)
    except Recusa:
        return _nao_encontrada()
    arquivo = servicos().arquivos.capa_video(token)
    if not arquivo.exists():
        return _nao_encontrada()
    return send_file(arquivo, mimetype='image/jpeg', conditional=True, max_age=0)


@bp.get('/previa/<token>/<int:numero>.mp3')
def previa(token, numero):
    if not re.fullmatch(r'[0-9a-f]{32}', token) or numero not in (1, 2):
        return _nao_encontrada()
    arquivo = servicos().arquivos.previa(token, numero)
    if not arquivo.exists():
        return _nao_encontrada()
    return send_file(arquivo, mimetype='audio/mpeg', conditional=True, max_age=0)


@bp.get('/compra/<guid>')
def pagina_compra(guid):
    """Área de quem comprou: ouvir e baixar, cartão QR, presente por e-mail, fotos do videoclipe."""
    try:
        pedido, musica, recursos = uc.compra(servicos(), guid)
    except Recusa as r:
        if r.status == 409:
            return render_template('musica/legal.html', pagina='liberando', atualizado=_atualizado_legal()), 409
        return _nao_encontrada()
    _usar_idioma_da_musica(musica)
    return render_template('musica/compra.html', guid=guid, musica=musica, recursos=recursos,
                           para=regras.para_quem(musica['respostas'], _texto('geral.sem_nome')),
                           letra_texto=regras.para_leitura(musica['letra_exibicao'], _texto('geral.refrao')),
                           link_presente=_rota('pagina_presente', token=musica['token'], _external=True),
                           tem_qrcode=QRCODE in recursos, tem_presente=ENTREGA_EMAIL in recursos,
                           de_editavel=uc.pode_mudar_de(musica),
                           nomes_quem_recebe=regras.nomes_quem_recebe(musica['respostas']),
                           tem_video=VIDEOCLIPE in recursos, legenda_video=config.LEGENDA_VIDEO,
                           max_fotos=servicos().video.max_fotos, whatsapp_ativo=idiomas.whatsapp_ativo(_idioma()),
                           # o agendado é gravado no horário de Brasília; a tela mostra no fuso do idioma e, onde a
                           # pessoa agenda no horário dela (hora_com_fuso), o JS troca para o fuso do navegador
                           presente_em_local=regras.para_fuso(musica['presente_em'],
                                                              idiomas.cfg(idiomas.IDIOMA_PADRAO)['fuso'],
                                                              idiomas.cfg(_idioma())['fuso']),
                           presente_em_iso=_com_fuso_de_brasilia(musica['presente_em'])
                           if idiomas.textos(_idioma())['compra']['js'].get('hora_com_fuso') else None)


def _com_fuso_de_brasilia(quando):
    """O horário do banco (Brasília, sem fuso) em ISO com o fuso, para o navegador converter para o dele."""
    if not quando:
        return None
    from zoneinfo import ZoneInfo
    return quando.replace(tzinfo=ZoneInfo(idiomas.cfg(idiomas.IDIOMA_PADRAO)['fuso'])).isoformat()


@bp.get('/compra/<guid>/enviar')
def enviar_pelo_whatsapp(guid):
    """Botão "Enviar pelo seu WhatsApp": abre o WhatsApp de quem comprou já na conversa de quem ganha (se ela
    informou o número) com a mensagem e o link do presente prontos."""
    try:
        _, musica, _ = uc.compra(servicos(), guid)
    except Recusa:
        return _nao_encontrada()
    _usar_idioma_da_musica(musica)
    from urllib.parse import quote
    nome = musica['presente_nome'] or regras.para_quem(musica['respostas'], _texto('geral.sem_nome'))
    link = _rota('pagina_presente', token=musica['token'], _external=True)
    texto = _texto('compra.enviar_pelo_whatsapp', nome=nome, link=link)
    return redirect(f"https://wa.me/{musica['presente_whatsapp'] or ''}?text={quote(texto)}")


@bp.get('/compra/<guid>/cartao')
def cartao_qrcode(guid):
    """Cartão para imprimir com o QR code que abre a página do presente (order bump)."""
    try:
        _, musica, recursos = uc.compra(servicos(), guid)
    except Recusa:
        return _nao_encontrada()
    if QRCODE not in recursos:
        return _nao_encontrada()
    _usar_idioma_da_musica(musica)
    link = _rota('pagina_presente', token=musica['token'], _external=True)
    return render_template('musica/cartao.html', musica=musica, para=regras.para_quem(musica['respostas'], _texto('geral.sem_nome')),
                           qr=_qr_svg(link))


def _qr_svg(texto):
    """QR code em SVG sem tamanho fixo (escala com o cartão, não corta na impressão)."""
    import qrcode
    import qrcode.image.svg
    imagem = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, border=2,
                         error_correction=qrcode.constants.ERROR_CORRECT_M)
    svg = imagem.to_string(encoding='unicode')
    svg = re.sub(r'<\?xml[^>]*>', '', svg)
    return re.sub(r'\s(width|height)="[^"]*"', '', svg, count=2)


@bp.get('/termos')
@bp.get('/terminos', endpoint='terminos')
def termos():
    return render_template('musica/legal.html', pagina='termos', atualizado=_atualizado_legal())


@bp.get('/privacidade')
@bp.get('/privacidad', endpoint='privacidad')
def privacidade():
    return render_template('musica/legal.html', pagina='privacidade', atualizado=_atualizado_legal())


# ======================================================================= API

@bp.post('/api/musicas')
def api_criar():
    if not _origem_confiavel():
        return jsonify(erro=_texto('erros.recarregue')), 403
    if not _produto():
        return jsonify(erro=_texto('erros.fora_de_venda')), 404
    dados = request.get_json(silent=True) or {}
    if not _turnstile_ok(dados.get('turnstile')):
        return jsonify(erro=_texto('erros.robo')), 400
    bruto = dados.get('respostas') if isinstance(dados.get('respostas'), dict) else {}
    quiz = _quiz_atual()
    respostas = regras.montar_respostas(bruto, quiz.CHAVES_VALIDAS, quiz.MAX_PESSOAS, quiz, _texto('geral.e'),
                                        _texto('geral.se_fala'))
    if quiz.combinacao_invalida(respostas):
        return jsonify(erro=_texto('erros.resposta_faltando')), 400
    digitado = str(dados.get('whatsapp') or '').strip()[:30]
    # opcional: só celular do país do idioma, com o DDI (Brasil 55, México 52)
    whatsapp = regras.celular_do_idioma(digitado, idiomas.cfg(_idioma())['telefone'])
    if digitado and not whatsapp:
        return jsonify(erro=_texto('erros.celular')), 400
    email = (dados.get('email') or '').strip().lower()[:200]
    erro_email = _erro_email(email)
    if erro_email:
        return jsonify(erro=erro_email), 400
    try:
        musica = uc.criar_musica(servicos(), _pid(), respostas, email, whatsapp, _ip(),
                                 pedido_origem_id=_pedido_origem(), dominio=_host(), idioma=_idioma())
    except Recusa as r:
        return _recusa(r)
    return jsonify(token=musica['token'], link=_rota('pagina_previa', token=musica['token']))


def _erro_email(email: str) -> str | None:
    """A mesma checagem de e-mail do checkout (web/email_validacao.py: formato, "gmail.comm" e domínio que não existe
    no DNS), com a mensagem no idioma da tela; None se passou."""
    from web.email_validacao import validar_email
    checagem = validar_email(email)
    if checagem['valido']:
        return None
    return _texto('erros.email_dominio' if checagem['motivo'] == 'dominio_inexistente' else 'erros.email_invalido')


def _ditado_excedido() -> bool:
    """15 por IP por hora e o teto do dia (config). É limite de CUSTO: com o Redis fora do ar, recusa (o contrário do
    limite do checkout, que nunca bloqueia venda) — ela ainda pode escrever na caixa."""
    from datetime import date
    from web.checkout import _excedeu_limite_ip
    return (_excedeu_limite_ip('musica_ditado', _ip(), config.DITADO_POR_HORA, 3600, sem_redis_bloqueia=True)
            or _excedeu_limite_ip('musica_ditado_dia', date.today().isoformat(), config.DITADO_POR_DIA, 86400,
                                  sem_redis_bloqueia=True))


@bp.post('/api/ditado')
def api_ditado():
    """Microfone da tela de lembranças: o áudio (campo "audio", até 2 min a 24 kbps ≈ 400 KB) vira texto. Sem turnstile
    (é a cada gravação): origem do site, até 1 MB (o padrão do nginx nas rotas da música), 15 por IP por hora e um
    teto do dia (custo da OpenAI)."""
    if not _origem_confiavel():
        return jsonify(erro=_texto('erros.recarregue')), 403
    if (request.content_length or 0) > 1024 * 1024:
        return jsonify(erro=_texto('erros.audio_grande')), 413
    audio = request.files.get('audio')
    if not audio:
        return jsonify(erro=_texto('erros.audio_vazio')), 400
    if (request.content_length or 0) < 1000 or audio.mimetype.split(';')[0] not in uc.FORMATOS_DITADO:
        return _recusa(Recusa('Não deu para entender o áudio. Tente de novo, falando perto do celular.'))
    if _ditado_excedido():
        logger.warning(f'[MUSICA] Limite do microfone atingido (IP {_ip()})')
        return jsonify(erro=_texto('erros.ditado_limite')), 429
    try:
        texto = uc.transcrever(servicos(), audio.stream, audio.mimetype, _idioma(), request.form.get('dica'))
    except Recusa as r:
        return _recusa(r)
    return jsonify(texto=texto)


@bp.get('/api/musicas/<token>')
def api_ver(token):
    musica = _musica_do_token(token)
    if not musica:
        return jsonify(erro=_texto('erros.musica_nao_encontrada')), 404
    resposta = {
        'status': musica['status'],
        'para': regras.para_quem(musica['respostas'], _texto('geral.sem_nome')),
        'titulo': musica['titulo'],
        'letra': regras.para_leitura(musica['letra_exibicao'], _texto('geral.refrao')),
        'ajustes_restantes': max(0, config.LIMITE_AJUSTES_LETRA - musica['ajustes_letra']),
        'outras_versoes_restantes': max(0, config.LIMITE_OUTRA_VERSAO - musica['outras_versoes']),
        # "chega no e-mail e no WhatsApp": só com o envio do WhatsApp da Música ligado (MUSICA_WHATSAPP_ATIVO e o
        # do idioma da música)
        'whatsapp_ativo': idiomas.whatsapp_ativo(_idioma()),
        'tem_whatsapp': idiomas.whatsapp_ativo(_idioma()) and bool(regras.telefone_whatsapp(musica.get('whatsapp'))),
    }
    if musica['liberada_em']:
        resposta['link_musica'] = _rota('pagina_presente', token=token)
    elif musica['status'] == 'previa_pronta':
        resposta['previas'] = [_rota('previa', token=token, numero=f['numero']) for f in musica['faixas'] or []]
        resposta['planos'], resposta['oferta'] = _planos_e_oferta_da_previa(token)
    return jsonify(resposta)


def _planos_e_oferta_da_previa(token):
    """Os botões de compra da prévia e o popup "última chance". Brasil: o nosso checkout (/pay, PIX ou cartão, em
    reais) — sem mudança. Nunca um checkout em reais para quem não está no Brasil.

    Fora do Brasil (Hotmart, docs/HOTMART.md): cada plano com oferta 'botao' em hotmart_ofertas vira (preço na moeda
    da oferta, link /comprar/<token>/<oferta>, que cria o pedido e vai para a Hotmart com o xcod) e o popup usa a
    oferta 'popup'. Plano sem oferta não aparece; nenhum = "venda fechada"."""
    if _idioma() != idiomas.IDIOMA_PADRAO:
        return _planos_e_oferta_hotmart(token)
    from web.links import link_checkout
    planos = _planos_a_venda()
    return ([{'nome': p['nome'], 'descricao': p['descricao'], 'preco': reais(p['preco']),
              'videoclipe': p['videoclipe'], 'padrao': bool(p['plano'].get('padrao')),
              'link': link_checkout(_pid(), p['plano'], musica=token)} for p in planos],
            _oferta_ultima_chance(planos, token))


def _planos_e_oferta_hotmart(token):
    """Os botões da prévia de fora do Brasil, com as ofertas da Hotmart. Um erro aqui nunca derruba a prévia (vira
    "venda fechada")."""
    try:
        from hotmart import checkout as hotmart_checkout
        ofertas = hotmart_checkout.ofertas_da_previa(_pid())
        moeda = idiomas.cfg(_idioma())['moeda']      # preços comparados e somados só na moeda do país
        planos = []
        for p in _planos_a_venda():
            o = ofertas['botao'].get(p['plano']['id'])
            if o and (o['moeda'] or '').upper() == moeda:
                planos.append({'nome': p['nome'], 'descricao': p['descricao'], 'videoclipe': p['videoclipe'],
                               'padrao': bool(p['plano'].get('padrao')), 'valor': o['preco'],
                               'preco': hotmart_checkout.preco_texto(o['preco'], o['moeda']),
                               'link': _rota('comprar_hotmart', token=token, codigo=o['codigo'])})
        planos.sort(key=lambda x: x['valor'])
        oferta = None
        popup = ofertas['popup'] if ofertas['popup'] and (ofertas['popup']['moeda'] or '').upper() == moeda else None
        padrao = next((x for x in planos if x['padrao']), None)
        cheia = next((x for x in planos if popup and not x['padrao']
                      and x['link'].endswith('/' + ofertas['botao'][popup['plano_id']]['codigo'])), None) \
            if popup and popup['plano_id'] in ofertas['botao'] else None
        if popup and padrao and cheia and padrao['valor'] < popup['preco'] < cheia['valor']:
            # O desconto é a oferta 'popup' da Hotmart; o link leva um token assinado (o mesmo de web/oferta.py, 24 h)
            # que /comprar confere: sem ele, o código da oferta com desconto sozinho não vende.
            from web.oferta import gerar_token
            assinatura = gerar_token(_pid(), popup['plano_id'])
            oferta = {'nome': cheia['nome'], 'videoclipe': cheia['videoclipe'], 'preco_cheio': cheia['preco'],
                      'preco': hotmart_checkout.preco_texto(popup['preco'], popup['moeda']),
                      'economia': hotmart_checkout.preco_texto(cheia['valor'] - popup['preco'], popup['moeda']),
                      'link': _rota('comprar_hotmart', token=token, codigo=popup['codigo'], oferta=assinatura),
                      'expira': int(assinatura.split('.', 1)[0])}
        return [{k: v for k, v in x.items() if k != 'valor'} for x in planos], oferta
    except Exception:
        logger.exception('[MUSICA] Falha ao montar as ofertas da Hotmart na prévia')
        return [], None


@bp.get('/comprar/<token>/<codigo>')
def comprar_hotmart(token, codigo):
    """Fora do Brasil: o botão de compra da prévia. Cria (ou reaproveita) o nosso pedido do plano da oferta, liga a
    música a ele e manda para o checkout da Hotmart com o guid no xcod (o webhook confirma). Guarda o guid num cookie
    para a página de obrigado."""
    if _idioma() == idiomas.IDIOMA_PADRAO:
        return _nao_encontrada()
    from hotmart import checkout as hotmart_checkout
    from web.checkout import _excedeu_limite_ip
    produto_id = _pid()
    musica = _musica_do_token(token)
    oferta = hotmart_checkout.oferta_para_link(codigo, produto_id, idiomas.cfg(_idioma())['moeda'])
    if not musica or not oferta:
        return _nao_encontrada()
    previa = _rota('pagina_previa', token=token)
    if oferta['uso'] == 'popup':
        from web.oferta import validar_token
        if not validar_token(request.args.get('oferta'), produto_id, oferta['plano_id']):
            return redirect(previa)      # desconto só pelo popup (link assinado e dentro da validade)
    # Pré-carregamento do navegador/mensageiro não cria pedido: só o clique de verdade.
    if 'prefetch' in (request.headers.get('Sec-Purpose', '') + request.headers.get('Purpose', '')).lower():
        return '', 204
    try:
        uc.musica_para_checkout(servicos(), token, produto_id)
    except Recusa:
        return redirect(previa)      # já comprada (a prévia leva ao presente) ou ainda não pronta
    if _excedeu_limite_ip('musica_hotmart', _ip(), 30, 3600):
        logger.warning(f'[MUSICA] Limite de cliques em comprar (Hotmart) atingido (IP {_ip()})')
        return redirect(previa)
    # o plano já vem de get_plano_venda (_planos_a_venda): o mesmo objeto vai para os itens do pedido
    a_venda = next((p for p in _planos_a_venda() if p['plano']['id'] == oferta['plano_id']), None)
    if not a_venda:
        return _nao_encontrada()
    plano = a_venda['plano']
    pedido = hotmart_checkout.pedido_aberto(musica['id'], plano['id'])
    if not pedido:
        pedido = hotmart_checkout.criar_pedido(produto_id, plano, a_venda['preco'], '', musica.get('email') or '',
                                               _host())
    try:
        from musica.integracao import vincular_ao_pedido
        vincular_ao_pedido(token, pedido['id'], produto_id)
    except Recusa:
        return redirect(previa)
    logger.info(f"[MUSICA] Música {musica['id']} → Hotmart (pedido #{pedido['id']}, oferta {oferta['codigo']})")
    # a música só guarda o e-mail (o nome a Hotmart pede no checkout)
    resposta = redirect(hotmart_checkout.link_pagamento(oferta, pedido['guid'], email=musica.get('email') or ''))
    resposta.set_cookie(_COOKIE_HOTMART, pedido['guid'], max_age=30 * 86400, httponly=True, samesite='Lax',
                        secure=request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https')
    return resposta


_COOKIE_HOTMART = 'musica_hotmart'


@bp.get('/gracias')
def obrigado_hotmart():
    """A página de obrigado cadastrada na Hotmart: espera o webhook confirmar e manda para a área da compra."""
    if _idioma() == idiomas.IDIOMA_PADRAO:
        return _nao_encontrada()
    return render_template('musica/obrigado.html', tem_pedido=bool(request.cookies.get(_COOKIE_HOTMART)))


@bp.get('/api/compra-hotmart')
def api_compra_hotmart():
    """Estado do pedido DO COOKIE (nunca um guid pela URL): pago → o link da área da compra."""
    from hotmart import checkout as hotmart_checkout
    guid = request.cookies.get(_COOKIE_HOTMART) or ''
    pedido = hotmart_checkout.estado_do_pedido(guid) if re.fullmatch(r'[A-Za-z0-9_-]{4,64}', guid) else None
    estado = (pedido or {}).get('estado')
    if estado == 1000:
        return jsonify(situacao='pago', link=_rota('pagina_compra', guid=guid))
    if estado == 1010:
        return jsonify(situacao='aguardando')
    if estado == 1011:   # cartão recusado / expirou: volta para a prévia para tentar de novo
        return jsonify(situacao='cancelado',
                       link=_rota('pagina_previa', token=pedido['token']) if pedido.get('token') else None)
    return jsonify(situacao='processando' if estado is not None else 'sem_pedido')


@bp.post('/api/musicas/<token>/ajustar')
def api_ajustar(token):
    if not _origem_confiavel():
        return jsonify(erro=_texto('erros.recarregue')), 403
    _musica_do_token(token)
    try:
        uc.pedir_ajuste(servicos(), token, (request.get_json(silent=True) or {}).get('ajuste'))
    except Recusa as r:
        return _recusa(r)
    return jsonify(ok=True)


@bp.post('/api/musicas/<token>/gerar')
def api_gerar(token):
    if not _origem_confiavel():
        return jsonify(erro=_texto('erros.recarregue')), 403
    _musica_do_token(token)
    try:
        uc.gerar(servicos(), token, _ip())
    except Recusa as r:
        return _recusa(r)
    return jsonify(ok=True)


@bp.post('/api/musicas/<token>/outra-versao')
def api_outra_versao(token):
    if not _origem_confiavel():
        return jsonify(erro=_texto('erros.recarregue')), 403
    _musica_do_token(token)
    try:
        uc.outra_versao(servicos(), token)
    except Recusa as r:
        return _recusa(r)
    return jsonify(ok=True)


@bp.post('/api/compra/<guid>/presente')
def api_presente(guid):
    """Entrega para quem recebe (e-mail e/ou WhatsApp): agora ou na data/hora escolhida (horário de Brasília)."""
    if not _origem_confiavel():
        return jsonify(erro=_texto('erros.recarregue')), 403
    from datetime import datetime
    from zoneinfo import ZoneInfo
    dados = request.get_json(silent=True) or {}
    quando = None
    if not dados.get('agora'):
        try:
            quando = datetime.fromisoformat(dados.get('quando') or '')
        except ValueError:
            return jsonify(erro=_texto('erros.data_hora')), 400
        if quando.tzinfo:   # com fuso: converte para o horário de Brasília, como o resto do sistema (sem fuso)
            quando = quando.astimezone(ZoneInfo(idiomas.cfg(idiomas.IDIOMA_PADRAO)['fuso'])).replace(tzinfo=None)
    email = str(dados.get('email') or '').strip()
    if email:
        try:
            uc.compra(servicos(), guid)   # compra de verdade antes da consulta de DNS (não segura o worker à toa)
        except Recusa as r:
            return _recusa(r)
        erro_email = _erro_email(email)
        if erro_email:
            return jsonify(erro=erro_email), 400
    try:
        uc.agendar_presente(servicos(), guid, dados.get('nome'), dados.get('email'), dados.get('mensagem'), quando,
                            whatsapp=dados.get('whatsapp'), confirmo=bool(dados.get('confirmo')), de=dados.get('de'))
    except Recusa as r:
        return _recusa(r)
    return jsonify(ok=True, agora=quando is None)


@bp.post('/api/compra/<guid>/fotos')
def api_foto(guid):
    """Uma foto do videoclipe por requisição (campo "foto"; primeira=1 recomeça a seleção)."""
    if not _origem_confiavel():
        return jsonify(erro=_texto('erros.recarregue')), 403
    if (request.content_length or 0) > 2 * 1024 * 1024:
        return jsonify(erro=_texto('erros.foto_grande')), 413
    foto = request.files.get('foto')
    if not foto or not foto.filename:
        return jsonify(erro=_texto('erros.escolha_foto')), 400
    try:
        guardadas = uc.receber_foto(servicos(), guid, foto.stream, request.form.get('primeira') == '1')
    except Recusa as r:
        return _recusa(r)
    return jsonify(ok=True, fotos=guardadas)


@bp.post('/api/compra/<guid>/video')
def api_video(guid):
    """Depois das fotos: começa a montar o vídeo."""
    if not _origem_confiavel():
        return jsonify(erro=_texto('erros.recarregue')), 403
    dados = request.get_json(silent=True) or {}
    try:
        uc.iniciar_video(servicos(), guid, 2 if str(dados.get('versao')) == '2' else 1, dados.get('legenda') is not False)
    except Recusa as r:
        return _recusa(r)
    return jsonify(ok=True)


@bp.get('/api/compra/<guid>/video')
def api_status_video(guid):
    try:
        _, musica, _ = uc.compra(servicos(), guid)
    except Recusa as r:
        return _recusa(r)
    return jsonify(status=musica['video_status'])


@bp.post('/webhook/<provedor>')
def webhook(provedor):
    """O gerador avisa que terminou (assinatura conferida pelo adaptador). Aviso válido = 200 (quem decide é a
    consulta que ele dispara); assinatura inválida ou outro provedor = 401."""
    try:
        valido = uc.aviso_do_gerador(servicos(), provedor, request.get_data(), dict(request.headers))
    except Exception as e:
        logger.error(f'[MUSICA] Erro no webhook do gerador {provedor}: {e}')
        valido = False
    return jsonify(ok=valido), (200 if valido else 401)
