"""Idiomas da Música (musica/idiomas.py): o Brasil continua igual e cada idioma tem conteúdo completo e coerente
(textos, quiz, estilos), e a música usa o idioma DELA do começo ao fim (letra, som, prévia, links, lembretes)."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from musica import casos_de_uso as uc
from musica import idiomas, links, mensagens
from musica.dominio import quiz as _quiz
from musica.dominio import regras

RAIZ = Path(__file__).resolve().parents[2] / 'app' / 'musica'
TODOS = sorted(idiomas.IDIOMAS)
FORA_DO_BRASIL = [i for i in TODOS if i != idiomas.IDIOMA_PADRAO]
RESPOSTAS_MX = {'para_quem': 'Mamá', 'nome': 'Guadalupe', 'apelido': 'Lupita', 'lembrancas': 'Pozole los domingos',
                'de': 'Patricia', 'ocasiao': '10 de mayo (Día de las Madres)', 'estilo': 'mariachi',
                'clima': 'emocionante', 'voz': 'masculina'}


# ------------------------------------------------------- conteúdo completo

def _chaves(d, prefixo=''):
    """Os caminhos de um dict ('quiz.js.contador'), sem as notas (_como_usar)."""
    saida = {}
    for k, v in d.items():
        if k.startswith('_'):
            continue
        caminho = f'{prefixo}{k}'
        saida[caminho] = v
        if isinstance(v, dict) and k not in ('recusas', 'paginas'):
            saida.update(_chaves(v, caminho + '.'))
    return saida


@pytest.mark.parametrize('idioma', FORA_DO_BRASIL)
def test_textos_tem_todas_as_frases_do_brasil(idioma):
    """Frase que falta cairia no português (idiomas.texto); no JS, viraria "undefined" na tela."""
    pt, outro = _chaves(idiomas.textos('pt-BR')), _chaves(idiomas.textos(idioma))
    faltam = sorted(set(pt) - set(outro))
    assert not faltam, faltam
    for caminho, valor in pt.items():
        if isinstance(valor, list) and caminho not in ('landing.exemplos', 'landing.principais', 'landing.duvidas',
                                                       'landing.oferta_inclui'):
            assert len(outro[caminho]) == len(valor), caminho   # medidor, contador, etapas, nomes de exemplo
        if isinstance(valor, str):
            for marca in ('{para}', '{titulo}', '{nome}', '{n}', '{ajustes}', '{cheio}', '{economia}', '{link}',
                          '{marca}', '{whatsapp}', '{musica}', '{rotulo}'):
                if marca in valor:
                    assert marca in outro[caminho], (caminho, marca)


@pytest.mark.parametrize('idioma', TODOS)
def test_arquivos_de_conteudo_existem(idioma):
    pasta = idiomas.pasta(idioma)
    for nome in ('estilos.json', 'instrucoes_letra.md', 'quiz.py', 'textos.json'):
        assert (pasta / nome).exists(), (idioma, nome)
    assert (RAIZ / 'templates' / 'musica' / 'legal' / f'{idioma}.html').exists()


# ------------------------------------------------------- quiz e estilos coerentes

@pytest.mark.parametrize('idioma', TODOS)
def test_estilos_tons_e_vozes_do_quiz_existem_no_estilos_json(idioma):
    quiz, tabela = _quiz.do_idioma(idioma), idiomas.estilos(idioma)
    assert {e for e, _ in quiz.ESTILOS} == set(tabela['estilos'])
    assert {t['valor'] for t in quiz.TONS} <= set(tabela['clima'])
    assert set(quiz.VOZES) <= set(tabela['voz'])
    for estilo, _ in quiz.ESTILOS:
        assert set(quiz.vozes_para(estilo)) <= set(quiz.VOZES), estilo
    assert set(tabela.get('negativo_estilo', {})) <= set(tabela['estilos'])
    assert {e for e in tabela.get('voz_estilo', {}) if not e.startswith('_')} <= set(tabela['estilos'])


@pytest.mark.parametrize('idioma', TODOS)
def test_toda_relacao_tem_ocasiao_e_tom_e_toda_opcao_aparece(idioma):
    quiz = _quiz.do_idioma(idioma)
    relacoes = [r['valor'] for r in quiz.RELACOES]
    for r in relacoes:
        ocasioes = quiz.ocasioes_para(r)
        assert ocasioes, r
        assert all(quiz.tons_para(r, o) for o in ocasioes), r
    for o in quiz.OCASIOES:
        assert any(o['valor'] in quiz.ocasioes_para(r) for r in relacoes), o['valor']
    for t in quiz.TONS:
        assert any(t['valor'] in quiz.tons_para(r, o) for r in relacoes for o in quiz.ocasioes_para(r)), t['valor']
    assert quiz.OUTRA_PESSOA in relacoes and quiz.MAIS_DE_UMA in relacoes and quiz.PARA_MIM in relacoes
    assert quiz.OUTRA_OCASIAO in [o['valor'] for o in quiz.OCASIOES]
    for t in quiz.TONS:   # os tons que excluem uma ocasião apontam para uma que existe
        assert set(t.get('exceto_ocasioes', [])) <= {o['valor'] for o in quiz.OCASIOES}, t['valor']


@pytest.mark.parametrize('idioma', TODOS)
def test_paginas_de_ocasiao_da_landing_combinam_com_o_quiz(idioma):
    """Botões "Pra quem é a música?" do topo e das páginas de ocasião: relação que o quiz conhece e que combina com a
    ocasião da página (no quiz, "Pai" + "Dia das Mães" não existe)."""
    quiz, landing = _quiz.do_idioma(idioma), idiomas.textos(idioma)['landing']
    relacoes, ocasioes = {r['valor'] for r in quiz.RELACOES}, {o['valor'] for o in quiz.OCASIOES}
    por_ocasiao = quiz.relacoes_por_ocasiao()
    assert set(landing['principais']) <= relacoes
    for slug, pg in {**landing['paginas'], '_padrao': landing['pagina_padrao']}.items():
        assert not pg['quiz'] or pg['quiz'] in ocasioes, (slug, pg['quiz'])
        assert not pg['quiz'] or por_ocasiao[pg['quiz']], slug
        for quem in pg.get('quem', []):
            assert quem in relacoes, (slug, quem)
            assert not pg['quiz'] or pg['quiz'] in quiz.ocasioes_para(quem), (slug, quem)
        assert (RAIZ / 'static' / 'img' / pg['img']).exists(), (slug, pg['img'])
    for ex in landing['exemplos']:
        assert ex['slug'] in ocasioes, ex['slug']
        assert (RAIZ / 'static' / 'exemplos' / ex['audio']).exists(), ex['audio']


def test_mexico_canta_em_espanhol_do_mexico_e_nao_em_portugues():
    tabela = idiomas.estilos('es-MX')
    assert 'Portuguese' in tabela['negativo'] and 'Spain Spanish accent' in tabela['negativo']
    assert 'Spanish' not in tabela['negativo'].replace('Spain Spanish accent', '')   # o Brasil proíbe espanhol; aqui não
    for estilo, texto in tabela['estilos'].items():
        assert 'Spanish' in texto, estilo
    assert 'Spanish' in idiomas.estilos('pt-BR')['negativo']   # o Brasil continua proibindo


def test_geracao_do_mexico_genero_primeiro_e_voz_do_estilo():
    quiz = _quiz.do_idioma('es-MX')
    pedido = regras.montar_geracao(RESPOSTAS_MX, 'Lupita', 'letra', idiomas.estilos('es-MX'), quiz)
    assert pedido.estilo.startswith('Mexican mariachi ranchera')
    assert 'grito' in pedido.estilo and pedido.genero_vocal == 'm'
    assert pedido.negativo.startswith('Portuguese') and 'flamenco' in pedido.negativo
    # voz que não combina com o estilo (dueto no mariachi) vira a primeira permitida
    pedido = regras.montar_geracao(dict(RESPOSTAS_MX, voz='dueto'), 'x', 'l', idiomas.estilos('es-MX'), quiz)
    assert pedido.genero_vocal == 'f'
    assert 'dueto' in quiz.vozes_para('banda') and 'trio' in quiz.vozes_para('bolero')


def test_quiz_do_brasil_continua_o_mesmo_pelos_atalhos_do_modulo():
    assert _quiz.RELACOES is _quiz.do_idioma('pt-BR').RELACOES
    assert _quiz.ocasioes_para('Mãe') == _quiz.do_idioma().ocasioes_para('Mãe')
    assert _quiz.do_idioma('xx-XX').idioma == 'pt-BR'   # idioma desconhecido = Brasil


# ------------------------------------------------------- celular

@pytest.mark.parametrize('digitado,esperado', [
    ('55 1234 5678', '525512345678'), ('+52 55 1234 5678', '525512345678'), ('521 55 1234 5678', '525512345678'),
    ('(81) 1234-5678', '528112345678'), ('11 91234-5678', ''), ('123', ''), ('', ''),
])
def test_celular_do_mexico(digitado, esperado):
    assert regras.celular_mx(digitado) == esperado
    assert regras.celular_do_idioma(digitado, 'mx') == esperado


def test_celular_do_brasil_continua_so_o_brasileiro():
    assert regras.celular_do_idioma('11 91234-5678', 'br') == '5511912345678'
    assert regras.celular_do_idioma('55 1234 5678', 'br') == ''


# ------------------------------------------------------- a música usa o idioma dela

class EscritorEspiao:
    modelo = 'espiao'

    def __init__(self):
        self.chamadas = []

    def escrever(self, instrucoes, respostas, letra_anterior=None, ajuste=None, idioma=None):
        from musica.dominio.modelos import Letra
        self.chamadas.append({'instrucoes': instrucoes, 'idioma': idioma})
        return Letra('Lupita', '[Chorus]\nTe quiero', '[Chorus]\nTe quiero', '')


class GeradorEspiao:
    nome = 'simulado'

    def __init__(self):
        self.pedidos = []

    def criar(self, pedido, webhook_url):
        self.pedidos.append(pedido)
        return 'simulado-0'


def test_musica_do_mexico_grava_o_idioma_e_usa_letra_e_som_do_mexico(s):
    s.escritor, s.gerador = EscritorEspiao(), GeradorEspiao()
    musica = uc.criar_musica(s, 30, dict(RESPOSTAS_MX), 'lupita@ejemplo.com', '525512345678', '1.2.3.4', idioma='es-MX')
    assert musica['idioma'] == 'es-MX'
    uc.escrever_letra(s, musica['id'])
    assert s.escritor.chamadas[0]['idioma'] == 'es-MX'
    assert s.escritor.chamadas[0]['instrucoes'].startswith('# Instrucciones para la IA')
    uc.gerar(s, musica['token'], '1.2.3.4')
    assert s.gerador.pedidos[0].estilo.startswith('Mexican mariachi')


def test_musica_do_brasil_continua_com_o_conteudo_dos_servicos(s):
    s.escritor, s.gerador = EscritorEspiao(), GeradorEspiao()
    from tests.musica.conftest import RESPOSTAS
    musica = uc.criar_musica(s, 17, dict(RESPOSTAS), 'a@b.com', '', '1.2.3.4')
    assert musica['idioma'] == 'pt-BR'
    uc.escrever_letra(s, musica['id'])
    assert s.escritor.chamadas[0]['instrucoes'] == s.instrucoes_letra
    uc.gerar(s, musica['token'], '1.2.3.4')
    assert s.gerador.pedidos[0].estilo.startswith('modern Brazilian sertanejo')


def test_links_da_musica_tem_o_prefixo_do_idioma():
    mx = {'token': 'a' * 32, 'dominio': 'site.com', 'idioma': 'es-MX'}
    br = {'token': 'a' * 32, 'dominio': 'site.com'}
    assert links.previa(mx) == f'https://site.com/mx/cancion/p/{"a" * 32}'
    assert links.sem_lembretes(mx).endswith('/mx/cancion/p/' + 'a' * 32 + '/sem-lembretes')
    assert links.previa(br) == f'https://site.com/musica/p/{"a" * 32}'


def test_lembrete_em_espanhol():
    assunto, corpo = mensagens.lembrete('previa', 1, 'Patricia', 'Lupita', 'https://x/p', 'https://x/sair', 'es-MX')
    assert assunto == '¿Te gustó la canción de Lupita? 🎶'
    assert '¡Hola, Patricia!' in corpo and 'Haz clic aquí' in corpo and 'https://x/sair' in corpo
    assunto, corpo = mensagens.lembrete('letra', 2, '', '', 'https://x/p', 'https://x/sair', 'es-MX')
    assert 'quien más quieres' in assunto and 'Ya hiciste lo más difícil' in corpo


def test_lembrete_do_brasil_nao_mudou():
    assunto, corpo = mensagens.lembrete('previa', 1, 'Patrícia', 'Lena', 'https://x/p', 'https://x/sair')
    assert assunto == 'Gostou da música de Lena? 🎶'
    assert 'Oi, Patrícia!' in corpo and 'Não quer mais estes lembretes?' in corpo


def test_janela_dos_lembretes_e_a_do_pais_da_musica():
    """10h em Brasília = 7h na Cidade do México: o Brasil envia, o México espera as 8h de lá."""
    serie = {'inicio': datetime(2026, 11, 18, 9, 0), 'desde': datetime(2026, 11, 18, 9, 0), 'enviados': 0}
    agora = datetime(2026, 11, 18, 10, 0)
    hora_mx = uc._hora_local('es-MX', agora)
    assert hora_mx == 7 and uc._hora_local('pt-BR', agora) is None
    assert regras.proximo_lembrete(serie, None, agora, (15,), (8, 22), 3)[0] == 'enviar'
    assert regras.proximo_lembrete(serie, None, agora, (15,), (8, 22), 3, hora_local=hora_mx) == (None, 0)


@pytest.mark.parametrize('idioma,respostas,assunto,link', [
    ('es-MX', RESPOSTAS_MX, '¿Te gustó la canción de Lupita? 🎶', '/mx/cancion/p/'),
    ('pt-BR', None, 'Ficou alguma dúvida no pagamento?', '/pay/30?'),
])
def test_fora_do_brasil_o_checkout_aberto_conta_como_previa_nos_lembretes(s, monkeypatch, idioma, respostas, assunto,
                                                                           link):
    monkeypatch.setitem(idiomas.IDIOMAS['es-MX'], 'vende', True)   # como vai ser com a Hotmart
    """Fora do Brasil o pagamento é na Hotmart: o link do nosso checkout não serve. A música conta como prévia (o
    lembrete leva à prévia, no idioma dela) — sem travar a série da pessoa. O Brasil continua com o do checkout."""
    from tests.musica.conftest import RESPOSTAS
    agora = datetime(2026, 11, 18, 15, 0)
    s.repositorio.agora = agora - timedelta(hours=1)
    musica = uc.criar_musica(s, 30, dict(respostas or RESPOSTAS), 'lupita@ejemplo.com', '', '1.2.3.4', idioma=idioma)
    s.repositorio.atualizar(musica['id'], status='previa_pronta', checkout_aberto_em=agora - timedelta(hours=1))
    for minutos in (0, 20):
        monkeypatch.setattr(uc, '_agora', lambda m=minutos: agora + timedelta(minutes=m))
        uc.enviar_lembretes(s)
    assert len(s.notificador.emails) == 1
    assert s.notificador.emails[0]['assunto'] == assunto and link in s.notificador.emails[0]['html']


def test_textos_de_um_idioma_caem_no_portugues_quando_falta_a_frase():
    assert idiomas.texto('es-MX', 'geral.refrao') == '(Coro)'
    assert idiomas.texto('es-MX', 'chave.que.nao.existe') == 'chave.que.nao.existe'
    assert idiomas.texto('xx-XX', 'geral.refrao') == '(Refrão)'


def test_quiz_dados_sao_o_mesmo_json_que_o_navegador_recebe():
    """config_do_navegador do México é serializável (vai para a página como JSON)."""
    json.dumps(_quiz.do_idioma('es-MX').config_do_navegador())


def test_nosso_checkout_em_reais_nao_vende_musica_de_fora_do_brasil(s, monkeypatch):
    from musica import integracao
    monkeypatch.setattr(integracao, 'servicos', lambda: s)
    for idioma, respostas, produto in (('es-MX', RESPOSTAS_MX, 30), ('pt-BR', None, 17)):
        from tests.musica.conftest import RESPOSTAS
        musica = uc.criar_musica(s, produto, dict(respostas or RESPOSTAS), 'a@b.com', '', '1.2.3.4', idioma=idioma)
        s.repositorio.atualizar(musica['id'], status='previa_pronta')
        if idioma == 'es-MX':
            with pytest.raises(uc.Recusa, match='não é vendida neste checkout'):
                integracao.conferir_para_checkout(musica['token'], produto)
        else:
            integracao.conferir_para_checkout(musica['token'], produto)   # o Brasil passa


@pytest.mark.parametrize('idioma', FORA_DO_BRASIL)
def test_erros_traduzidos_existem_no_codigo(idioma):
    """A tradução dos erros é pelo texto em português (textos.json → recusas): se a frase mudar em casos_de_uso.py,
    a tradução para de valer em silêncio. Este teste acusa."""
    codigo = (RAIZ / 'casos_de_uso.py').read_text(encoding='utf-8')
    for original in idiomas.textos(idioma)['recusas']:
        if not original.startswith('_'):
            assert f"Recusa('{original}'" in codigo, original


def test_idioma_que_ainda_nao_vende_nao_recebe_lembrete(s, monkeypatch):
    """O México sem checkout: lembrete "volte e compre" levaria a "no estamos vendiendo"."""
    assert idiomas.cfg('es-MX')['vende'] is False
    agora = datetime(2026, 11, 18, 15, 0)
    s.repositorio.agora = agora - timedelta(hours=1)
    musica = uc.criar_musica(s, 30, dict(RESPOSTAS_MX), 'lupita@ejemplo.com', '', '1.2.3.4', idioma='es-MX')
    s.repositorio.atualizar(musica['id'], status='previa_pronta')
    for minutos in (0, 20, 200):
        monkeypatch.setattr(uc, '_agora', lambda m=minutos: agora + timedelta(minutes=m))
        uc.enviar_lembretes(s)
    assert not s.notificador.emails


def test_consulta_dos_lembretes_traz_o_idioma():
    """O repositório falso dos testes devolve a música inteira; o SQL de verdade escolhe as colunas. Sem o idioma,
    a música do México recebia o lembrete do Brasil (achado no code review de 18/11/2026)."""
    import inspect
    from musica.adaptadores.repositorio_mysql import RepositorioMysql
    assert 'm.idioma' in inspect.getsource(RepositorioMysql.candidatas_lembrete)


def test_pronuncia_vai_para_a_ia_no_idioma():
    q = _quiz.do_idioma('es-MX')
    bruto = {'para_quem': 'Mamá', 'pessoas': [{'nome': 'Xóchitl', 'pronuncia': 'Sóchitl'}]}
    assert regras.montar_respostas(bruto, q.CHAVES_VALIDAS, q.MAX_PESSOAS, q, ' y ', ' se dice ')['pronuncia'] == \
        'Xóchitl se dice Sóchitl'
    pt = _quiz.do_idioma()
    bruto = {'para_quem': 'Mãe', 'pessoas': [{'nome': 'Theo', 'pronuncia': 'Téo'}]}
    assert regras.montar_respostas(bruto, pt.CHAVES_VALIDAS, pt.MAX_PESSOAS)['pronuncia'] == 'Theo se fala Téo'
