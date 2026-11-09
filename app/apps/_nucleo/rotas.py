"""Rotas comuns a todos os apps: /app/<slug>/entrar, link de entrada, sair, manifest e service worker.

As telas de cada app ficam no blueprint do próprio app (apps/<slug>/rotas.py).
"""
import json
import logging
import os

from flask import Blueprint, g, jsonify, make_response, redirect, render_template, request

import config
from apps import app_config
from apps._nucleo import auth, emails, licenca as lic
from apps._nucleo.urls import base_absoluta, url_absoluta

logger = logging.getLogger(__name__)

bp = Blueprint('apps_nucleo', __name__, template_folder='../templates')

_STATIC = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'static')


@bp.app_template_global('asset')
def asset(caminho: str) -> str:
    """URL de um arquivo em /static com ?v=<data de modificação> (o nginx guarda /static por 1 dia)."""
    try:
        v = int(os.path.getmtime(os.path.join(_STATIC, caminho)))
    except OSError:
        v = 0
    return f'/static/{caminho}?v={v}'


def _app_ou_404(slug):
    cfg = app_config(slug)
    if not cfg:
        return None, ('Página não encontrada', 404)
    return cfg, None


def _home(cfg) -> str:
    return f'{cfg.prefixo}/'


@bp.get('/app/<slug>/entrar')
def entrar(slug):
    cfg, erro = _app_ou_404(slug)
    if erro:
        return erro
    auth.carregar_cliente(slug)
    if g.cliente and g.licenca:
        return redirect(_home(cfg))
    resp = make_response(render_template(
        [f'apps/{slug}/entrar.html', 'apps/_nucleo/entrar.html'],
        app=cfg, link_invalido=request.args.get('link') == 'invalido'))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bp.post('/app/<slug>/entrar/codigo')
def pedir_codigo(slug):
    cfg, erro = _app_ou_404(slug)
    if erro:
        return erro
    if not auth.origem_confiavel():
        return jsonify(ok=False, erro='Pedido recusado. Recarregue a página e tente de novo.'), 403
    r = auth.pedir_codigo(auth.corpo_json().get('email'), auth.ip_cliente())
    if not r['ok']:
        return jsonify(ok=False, erro=r['erro']), 400
    try:
        emails.enviar_codigo(cfg, r['cliente']['email'], r['codigo'])
    except Exception as e:
        logger.error(f"[APPS] Falha ao enviar código para {r['cliente']['email']}: {e}")
        return jsonify(ok=False, erro='Não conseguimos enviar o email agora. Tente de novo em alguns minutos.'), 502
    resposta = {'ok': True}
    if not config.EH_PRODUCAO:
        resposta['codigo_dev'] = r['codigo']
    return jsonify(resposta)


@bp.post('/app/<slug>/entrar/confirmar')
def confirmar_codigo(slug):
    cfg, erro = _app_ou_404(slug)
    if erro:
        return erro
    if not auth.origem_confiavel():
        return jsonify(ok=False, erro='Pedido recusado. Recarregue a página e tente de novo.'), 403
    dados = auth.corpo_json()
    cliente_id, msg = auth.confirmar_codigo(dados.get('email'), dados.get('codigo'))
    if not cliente_id:
        return jsonify(ok=False, erro=msg), 400
    resp = jsonify(ok=True, destino=_home(cfg))
    return auth.gravar_cookie(resp, auth.criar_sessao(cliente_id))


@bp.get('/app/<slug>/entrar/link/<token>')
def entrar_por_link(slug, token):
    """Link de uso único (Estante 2, checkout, atendimento): entra já logada, sem código."""
    cfg, erro = _app_ou_404(slug)
    if erro:
        return erro
    cliente_id = auth.consumir_link_entrada(token, slug)
    if not cliente_id:
        # Link já usado ou vencido: se ela já tem sessão aqui, segue normal; senão, pede o código.
        auth.carregar_cliente(slug)
        if g.cliente and g.licenca:
            return redirect(_home(cfg))
        return redirect(f'{cfg.prefixo}/entrar?link=invalido')
    resp = redirect(_home(cfg))
    return auth.gravar_cookie(resp, auth.criar_sessao(cliente_id))


@bp.get('/pedido2/<guid>/abrir-app/<slug>')
def abrir_app_da_estante(guid, slug):
    """Botão "Abrir meu app" da Estante 2 (e destino do checkout depois do pagamento).

    O guid da Estante já dá acesso aos e-books da cliente; aqui ele vira um link de entrada de uso
    único no app, no domínio oficial do app (onde fica o cookie). Libera a licença na hora se o
    Celery ainda não liberou (o checkout redireciona 1,5 s depois de confirmar o pagamento)."""
    cfg, erro = _app_ou_404(slug)
    if erro:
        return erro
    from web.checkout import resolver_pedido_por_guid
    estante = f'/pedido2/{guid}'
    pedido, _, erro_pedido = resolver_pedido_por_guid(guid)
    # Entrega da contribuição (1009): e-mail digitado sem verificação nem pagamento — nunca vira acesso a app.
    if erro_pedido or pedido.get('estado_id') == 1009:
        return redirect(estante)
    try:
        lic.liberar_licencas_do_pedido(pedido['id'])
    except Exception as e:
        logger.error(f"[APPS] Erro ao liberar apps do pedido #{pedido['id']} pela Estante: {e}")
    cliente = lic.buscar_cliente_por_email(pedido.get('email'))
    if not cliente or not lic.buscar_licenca(cliente['id'], slug):
        return redirect(estante)
    if lic.pedido_criou_a_conta(cliente['id'], pedido['id'], slug):
        # Conta nova, nascida deste pedido: entra direto (link de uso único).
        caminho = f"/entrar/link/{auth.criar_link_entrada(cliente['id'], slug)}"
    else:
        # Conta que já existia (renovação, outro pedido com o mesmo e-mail...): o e-mail do checkout
        # não é verificado, então só entra com o código enviado ao e-mail. Quem já está logada
        # neste aparelho passa direto (a tela /entrar redireciona).
        caminho = '/entrar'
    # Em produção, sempre o domínio do app (config.dominio ou APP_BASE_URL): a Estante pode estar em
    # qualquer domínio nosso, mas a sessão e o ícone instalado precisam ficar num só. No dev, o
    # APP_BASE_URL aponta para o site real — fica no mesmo host (localhost).
    absoluto = cfg.dominio or config.EH_PRODUCAO
    resp = redirect(url_absoluta(cfg, caminho) if absoluto and base_absoluta(cfg) else f'{cfg.prefixo}{caminho}')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bp.post('/app/<slug>/sair')
def sair(slug):
    cfg, erro = _app_ou_404(slug)
    if erro:
        return erro
    if not auth.origem_confiavel():
        return jsonify(ok=False, erro='Pedido recusado.'), 403
    auth.encerrar_sessao(request.cookies.get(auth.COOKIE))
    return auth.apagar_cookie(jsonify(ok=True, destino=f'{cfg.prefixo}/entrar'))


@bp.get('/app/<slug>/manifest.webmanifest')
def manifest(slug):
    cfg, erro = _app_ou_404(slug)
    if erro:
        return erro
    dados = {
        'name': cfg.nome,
        'short_name': cfg.nome_curto,
        'description': cfg.descricao,
        'lang': 'pt-BR',
        'start_url': _home(cfg),
        'scope': _home(cfg),
        'display': 'standalone',
        'background_color': cfg.cor_fundo,
        'theme_color': cfg.cor_tema,
        'icons': [
            {'src': asset(cfg.icone_192), 'sizes': '192x192', 'type': 'image/png'},
            {'src': asset(cfg.icone_512), 'sizes': '512x512', 'type': 'image/png'},
            {'src': asset(cfg.icone_512), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }
    resp = make_response(json.dumps(dados, ensure_ascii=False))
    resp.headers['Content-Type'] = 'application/manifest+json; charset=utf-8'
    return resp


# Service worker mínimo: só o necessário para o navegador oferecer "instalar". Sem cache offline
# (o app precisa de internet, como o original). Servido dentro de /app/<slug>/ para o escopo ser o app.
_SW = """// Service worker do app: permite instalar na tela inicial. Não guarda páginas offline.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
"""


@bp.get('/app/<slug>/sw.js')
def service_worker(slug):
    cfg, erro = _app_ou_404(slug)
    if erro:
        return erro
    resp = make_response(_SW)
    resp.headers['Content-Type'] = 'text/javascript; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp
