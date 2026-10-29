"""Admin → Músicas vendidas (só administradores): ver a música de cada compra e REFAZER a música a pedido da cliente,
num rascunho que só entra no lugar da dela quando o admin aprova (docs/MUSICA.md "Refazer a música de uma compra").
As regras ficam em musica.casos_de_uso; aqui só a tela."""
import logging

from flask import flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from admin import admin_bp
from admin.auth import requer_admin

logger = logging.getLogger(__name__)


def _s():
    from musica.fabrica import servicos
    return servicos()


def _recusa_para_flash(funcao, *args, **kwargs):
    """Roda o caso de uso; a Recusa vira mensagem na tela (e não erro 500)."""
    from musica.casos_de_uso import Recusa
    try:
        return funcao(*args, **kwargs), True
    except Recusa as recusa:
        flash(recusa.mensagem, 'error')
        return None, False


@admin_bp.get('/musicas')
@requer_admin
def musicas_vendidas():
    busca = request.args.get('busca', '').strip()[:120]
    return render_template('admin/musicas.html', vendas=_s().repositorio.musicas_vendidas(busca), busca=busca)


@admin_bp.get('/musicas/<int:musica_id>')
@requer_admin
def musica_detalhe(musica_id):
    from musica import links
    from musica.dominio import quiz, regras
    from musica.dominio.recursos import RECURSOS
    s = _s()
    musica = s.repositorio.por_id(musica_id)
    if musica and musica.get('rascunho_de'):
        return redirect(url_for('admin.musica_detalhe', musica_id=musica['rascunho_de']))
    venda = s.repositorio.venda_da_musica(musica_id)
    if not musica or not venda:
        flash('Música paga não encontrada.', 'error')
        return redirect(url_for('admin.musicas_vendidas'))
    recursos = s.repositorio.recursos_do_pedido(venda['pedido_id'])
    return render_template(
        'admin/musica_detalhe.html', musica=musica, venda=venda, recursos=recursos,
        nomes_itens=[RECURSOS.get(r, {}).get('nome', r) for r in sorted(recursos)],
        rascunho=s.repositorio.rascunho_ativo(musica_id),
        para=regras.para_quem(musica['respostas']),
        link_compra=links.compra(venda['guid'], venda['dns_origem'] or musica['dominio']),
        link_presente=links.presente(musica), tem_fotos=s.arquivos.tem_fotos(musica['token']),
        relacoes=[[r['valor']] * 2 for r in quiz.RELACOES], ocasioes=[[o['valor']] * 2 for o in quiz.OCASIOES],
        tons=[[t['valor'], t['texto']] for t in quiz.TONS], estilos=quiz.ESTILOS, vozes=list(quiz.VOZES.items()),
        regras_quiz=quiz.config_do_navegador())


@admin_bp.get('/musicas/<int:musica_id>/andamento')
@requer_admin
def musica_andamento(musica_id):
    """A página consulta enquanto o rascunho escreve a letra ou gera a música (recarrega quando muda)."""
    rascunho = _s().repositorio.rascunho_ativo(musica_id)
    return jsonify(status=rascunho['status'] if rascunho else None)


@admin_bp.get('/musicas/<int:musica_id>/audio/<int:numero>.mp3')
@requer_admin
def musica_audio_admin(musica_id, numero):
    """A versão completa (da original ou do rascunho) para ouvir no admin."""
    s = _s()
    musica = s.repositorio.por_id(musica_id)
    arquivo = s.arquivos.completa(musica['token'], numero) if musica and numero in (1, 2) else None
    if not arquivo or not arquivo.exists():
        return 'Áudio não encontrado.', 404
    return send_file(arquivo, mimetype='audio/mpeg', conditional=True, max_age=0)


def _voltar(musica_id):
    return redirect(url_for('admin.musica_detalhe', musica_id=musica_id) + '#refazer')


def _quem():
    return getattr(current_user, 'email', '?')


@admin_bp.post('/musicas/<int:musica_id>/refazer')
@requer_admin
def musica_refazer(musica_id):
    from musica import casos_de_uso as uc
    _, ok = _recusa_para_flash(uc.criar_rascunho, _s(), musica_id, request.form,
                               letra_nova=request.form.get('letra_nova') == '1')
    if ok:
        logger.info(f'[ADMIN] {_quem()} começou a refazer a música #{musica_id}')
        flash('Rascunho criado. A música da cliente não muda até você clicar em "Usar esta na compra".', 'success')
    return _voltar(musica_id)


def _do_rascunho(rascunho_id):
    rascunho = _s().repositorio.por_id(rascunho_id)
    return (rascunho or {}).get('rascunho_de') or 0


@admin_bp.post('/musicas/rascunho/<int:rascunho_id>/escolhas')
@requer_admin
def musica_rascunho_escolhas(rascunho_id):
    from musica import casos_de_uso as uc
    _, ok = _recusa_para_flash(uc.editar_escolhas_rascunho, _s(), rascunho_id, request.form,
                               letra_nova=request.form.get('letra_nova') == '1')
    if ok:
        flash('Escolhas salvas.', 'success')
    return _voltar(_do_rascunho(rascunho_id))


@admin_bp.post('/musicas/rascunho/<int:rascunho_id>/ajuste')
@requer_admin
def musica_rascunho_ajuste(rascunho_id):
    from musica import casos_de_uso as uc
    _, ok = _recusa_para_flash(uc.ajustar_rascunho, _s(), rascunho_id, request.form.get('instrucao'))
    if ok:
        flash('A IA está reescrevendo a letra. A página atualiza sozinha.', 'success')
    return _voltar(_do_rascunho(rascunho_id))


@admin_bp.post('/musicas/rascunho/<int:rascunho_id>/letra')
@requer_admin
def musica_rascunho_letra(rascunho_id):
    from musica import casos_de_uso as uc
    f = request.form
    _, ok = _recusa_para_flash(uc.editar_letra_rascunho, _s(), rascunho_id, f.get('titulo'), f.get('exibicao'),
                               f.get('cantada'))
    if ok:
        flash('Letra salva. Crie a música para ouvir.', 'success')
    return _voltar(_do_rascunho(rascunho_id))


@admin_bp.post('/musicas/rascunho/<int:rascunho_id>/gerar')
@requer_admin
def musica_rascunho_gerar(rascunho_id):
    from musica import casos_de_uso as uc
    _, ok = _recusa_para_flash(uc.gerar_rascunho, _s(), rascunho_id)
    if ok:
        logger.info(f'[ADMIN] {_quem()} gerou a música do rascunho #{rascunho_id}')
        flash('Criando a música (leva uns 2 a 4 minutos). A página atualiza sozinha.', 'success')
    return _voltar(_do_rascunho(rascunho_id))


@admin_bp.post('/musicas/rascunho/<int:rascunho_id>/usar')
@requer_admin
def musica_rascunho_usar(rascunho_id):
    from musica import casos_de_uso as uc
    musica_id = _do_rascunho(rascunho_id)
    resultado, ok = _recusa_para_flash(uc.usar_rascunho, _s(), rascunho_id, avisar=request.form.get('avisar') == '1')
    if ok:
        logger.info(f'[ADMIN] {_quem()} trocou a música #{musica_id} pelo rascunho #{rascunho_id} ({resultado})')
        partes = ['Pronto: a música nova já está na compra da cliente.']
        if resultado['video']:
            partes.append('O videoclipe está sendo refeito com as fotos dela.')
        partes.append('Ela foi avisada por e-mail.' if resultado['avisada'] else 'Ela não foi avisada por e-mail.')
        flash(' '.join(partes), 'success')
    return redirect(url_for('admin.musica_detalhe', musica_id=musica_id))


@admin_bp.post('/musicas/rascunho/<int:rascunho_id>/descartar')
@requer_admin
def musica_rascunho_descartar(rascunho_id):
    from musica import casos_de_uso as uc
    original = _do_rascunho(rascunho_id)
    _, ok = _recusa_para_flash(uc.descartar_rascunho, _s(), rascunho_id)
    if ok:
        flash('Rascunho descartado. A música da cliente não mudou.', 'success')
    return redirect(url_for('admin.musica_detalhe', musica_id=original) if original else url_for('admin.musicas_vendidas'))
