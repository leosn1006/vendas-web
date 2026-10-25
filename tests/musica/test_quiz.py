"""Quiz da Música: as opções combinam entre si, os dados batem com o estilos.json e as respostas são montadas certo."""
import json
import re
from pathlib import Path

import pytest

from musica.dominio import quiz, regras

CONTEUDO = Path(__file__).resolve().parents[2] / 'app' / 'musica' / 'conteudo'
TABELA = json.loads((CONTEUDO / 'estilos.json').read_text(encoding='utf-8'))
LANDING = (Path(__file__).resolve().parents[2] / 'app' / 'musica' / 'templates' / 'musica' / 'inicio.html').read_text(
    encoding='utf-8')


# --------------------------------------------------------- dados coerentes

def test_todo_estilo_tom_e_voz_existe_no_estilos_json():
    assert {e for e, _ in quiz.ESTILOS} <= set(TABELA['estilos'])
    assert {t['valor'] for t in quiz.TONS} <= set(TABELA['clima'])
    assert set(quiz.VOZES) <= set(TABELA['voz'])
    for estilo in TABELA['estilos']:
        assert set(quiz.vozes_para(estilo)) <= set(quiz.VOZES)


def test_tom_nao_carrega_genero_que_engole_o_estilo():
    """'ballad' no tom puxava todo gênero (rock, gospel) para balada."""
    for chave, texto in TABELA['clima'].items():
        assert 'ballad' not in texto.lower(), chave


def test_toda_relacao_tem_ocasiao_e_tom():
    for r in quiz.RELACOES:
        assert quiz.ocasioes_para(r['valor']), r['valor']
        assert quiz.tons_para(r['valor'], 'Aniversário'), r['valor']


def test_toda_ocasiao_e_tom_aparecem_para_alguem():
    relacoes = [r['valor'] for r in quiz.RELACOES]
    for o in quiz.OCASIOES:
        assert any(o['valor'] in quiz.ocasioes_para(r) for r in relacoes), o['valor']
    for t in quiz.TONS:
        assert any(t['valor'] in quiz.tons_para(r, 'Aniversário') for r in relacoes), t['valor']


def test_botoes_do_topo_da_landing_sao_relacoes_do_quiz():
    """Os botões "Pra quem é a música?" do topo levam ?para_quem=...; valor fora do quiz abriria a 1ª tela."""
    relacoes = {r['valor'] for r in quiz.RELACOES}
    for lista in re.findall(r'"quem": \[([^\]]+)\]', LANDING) + re.findall(r'pg\.quem or \[([^\]]+)\]', LANDING):
        for quem in re.findall(r'"([^"]+)"', lista):
            assert quem in relacoes, quem


def test_botoes_de_cada_pagina_combinam_com_a_ocasiao_dela():
    """Na página do Dia das Mães, o botão "Pai" levaria a uma combinação que o quiz recusa."""
    for quiz_ocasiao, lista in re.findall(r'"quiz": "([^"]*)", "quem": \[([^\]]+)\]', LANDING):
        for quem in re.findall(r'"([^"]+)"', lista):
            assert not quiz_ocasiao or quiz_ocasiao in quiz.ocasioes_para(quem), (quiz_ocasiao, quem)


def test_toda_pagina_de_ocasiao_tem_botoes():
    """A página de uma ocasião usa relacoes_por_ocasiao()[ocasião] (sem ela, o topo da página ficaria vazio)."""
    por_ocasiao = quiz.relacoes_por_ocasiao()
    for usada in set(re.findall(r'"quiz": "([^"]+)"', LANDING)):
        assert por_ocasiao.get(usada), usada
    assert 'Pai' not in por_ocasiao['Dia das Mães'] and 'Minha ex' in por_ocasiao['Dia dos Namorados']


def test_ex_tem_tom_romantico_e_perguntas_proprias():
    assert 'romantica' in quiz.tons_para('Minha ex', 'Dia dos Namorados')
    cfg = quiz.config_do_navegador()
    assert cfg['guia_lembrancas']['Meu ex'] == 'ex' and cfg['rotulo']['Minha ex'] == 'ex'
    assert cfg['rotulo']['Mãe'] == 'mãe'


def test_ocasioes_das_paginas_da_landing_existem():
    valores = {o['valor'] for o in quiz.OCASIOES}
    for usada in set(re.findall(r'"quiz": "([^"]+)"', LANDING)) | set(re.findall(r'"slug": "([^"]+)"', LANDING)):
        assert usada in valores, usada


# --------------------------------------------- opções que combinam entre si

@pytest.mark.parametrize('relacao,aparece,nao_aparece', [
    ('Amigo', ['Aniversário', 'Agradecer de coração'], ['Dia das Mães', 'Dia dos Namorados', 'Pedido de casamento']),
    ('Mãe', ['Dia das Mães', 'Natal'], ['Dia dos Pais', 'Dia dos Namorados']),
    ('Esposa', ['Dia das Mães', 'Dia dos Namorados', 'Aniversário de casamento ou namoro'], ['Dia dos Pais', 'Pedido de casamento']),
    ('Namorado', ['Pedido de casamento', 'Dia dos Namorados'], ['Dia das Mães']),
    ('Para mim', ['Celebrar a minha história', 'Celebrar uma conquista'], ['Pedido de desculpas', 'Homenagem a quem já partiu']),
    ('Mais de uma pessoa', ['Dia das Mães', 'Aniversário de casamento ou namoro'], ['Pedido de casamento']),
    ('Minha ex', ['Pedido de desculpas', 'Matar a saudade', 'Dia dos Namorados', 'Só porque eu amo'],
     ['Casamento', 'Chá revelação', 'Dia das Mães', 'Aniversário de casamento ou namoro', 'Pedido de casamento',
      'Formatura', 'Aposentadoria']),
    ('Meu ex', ['Pedido de desculpas', 'Matar a saudade', 'Dia dos Namorados'],
     ['Casamento', 'Chá revelação', 'Dia dos Pais', 'Aniversário de casamento ou namoro', 'Aposentadoria']),
])
def test_ocasioes_pela_relacao(relacao, aparece, nao_aparece):
    ocasioes = quiz.ocasioes_para(relacao)
    assert set(aparece) <= set(ocasioes)
    assert not set(nao_aparece) & set(ocasioes)


def test_tons_pela_relacao_e_ocasiao():
    assert 'romantica' in quiz.tons_para('Esposa', 'Aniversário')
    assert 'romantica' not in quiz.tons_para('Mãe', 'Aniversário')
    assert 'engracado' not in quiz.tons_para('Pai', 'Homenagem a quem já partiu')
    assert 'animada' not in quiz.tons_para('Pai', 'Homenagem a quem já partiu')
    assert 'engracado' not in quiz.tons_para('Esposa', 'Pedido de desculpas')


def test_vozes_pelo_estilo():
    assert quiz.vozes_para('samba') == ['feminina', 'masculina']
    assert 'dupla' in quiz.vozes_para('sertanejo_raiz')
    assert 'coral' in quiz.vozes_para('gospel') and 'dupla' not in quiz.vozes_para('gospel')


# ------------------------------------------------------- pedido ao gerador

def test_genero_primeiro_e_negativo_do_estilo():
    g = regras.montar_geracao({'estilo': 'gospel', 'clima': 'emocionante', 'voz': 'coral'}, 'T', 'letra', TABELA)
    assert g.estilo.startswith(TABELA['estilos']['gospel'])
    assert 'choir' in g.estilo and 'sertanejo' in g.negativo and TABELA['negativo'] in g.negativo


def test_voz_propria_do_estilo():
    g = regras.montar_geracao({'estilo': 'gospel', 'clima': 'emocionante', 'voz': 'feminina'}, 'T', 'letra', TABELA)
    assert 'worship vocals' in g.estilo and 'warm female vocals' not in g.estilo
    assert 'warm female vocals' in regras.montar_geracao({'estilo': 'pop', 'voz': 'feminina'}, 'T', 'l', TABELA).estilo


def test_voz_incoerente_vira_a_primeira_permitida():
    """Música antiga: samba com dupla sertaneja (antes da regra) sai com voz feminina."""
    g = regras.montar_geracao({'estilo': 'samba', 'clima': 'animada', 'voz': 'dupla'}, 'T', 'letra', TABELA)
    assert 'duo' not in g.estilo and g.genero_vocal == 'f'


def test_tom_antigo_alegre_continua_valendo():
    g = regras.montar_geracao({'estilo': 'pop', 'clima': 'alegre'}, 'T', 'letra', TABELA)
    assert TABELA['clima']['animada'] in g.estilo


# --------------------------------------------------- respostas do navegador

def test_tres_irmas_viram_nome_apelido_e_lista():
    r = regras.montar_respostas({
        'para_quem': 'Mais de uma pessoa', 'de': 'Leo',
        'pessoas': [{'nome': 'Ana'}, {'nome': 'Beatriz', 'apelido': 'Bia'}, {'nome': 'Carla', 'pronuncia': 'Cárla'},
                    {'nome': 'Duda'}, {'nome': 'Quinta, que passa do limite'}],
        'lembrancas_partes': [{'pergunta': 'Uma lembrança', 'resposta': 'Férias na casa da vó'},
                              {'pergunta': 'Um jeito de cada um', 'resposta': ''}],
    }, quiz.CHAVES_VALIDAS, quiz.MAX_PESSOAS)
    assert r['nome'] == 'Ana, Beatriz, Carla e Duda'
    assert r['apelido'] == 'Ana, Bia, Carla e Duda'
    assert r['pronuncia'] == 'Carla se fala Cárla'
    assert len(r['pessoas']) == 4
    assert r['lembrancas'] == 'Uma lembrança: Férias na casa da vó'


def test_uma_pessoa_nao_grava_lista():
    r = regras.montar_respostas({'para_quem': 'Mãe', 'pessoas': [{'nome': 'Helena', 'apelido': 'Lena'}]},
                                quiz.CHAVES_VALIDAS, quiz.MAX_PESSOAS)
    assert r['nome'] == 'Helena' and r['apelido'] == 'Lena' and 'pessoas' not in r
    assert regras.para_quem(r) == 'Lena'


def test_para_mim_quem_da_e_a_propria_pessoa():
    r = regras.montar_respostas({'para_quem': 'Para mim', 'pessoas': [{'nome': 'Patrícia'}]},
                                quiz.CHAVES_VALIDAS, quiz.MAX_PESSOAS)
    assert r['de'] == 'Patrícia'


def test_chave_desconhecida_e_tipo_errado_sao_ignorados():
    r = regras.montar_respostas({'nome': 'Ana', 'senha': 'x', 'estilo': {'injecao': 1}, 'pessoas': 'texto'},
                                quiz.CHAVES_VALIDAS, quiz.MAX_PESSOAS)
    assert r == {'nome': 'Ana'}


# ------------------------------------------------- revisão de 22/10/2026

def test_payload_torto_nao_derruba():
    r = regras.montar_respostas({'nome': 'Ana', 'pessoas': {'a': 1}, 'lembrancas_partes': 'texto'},
                                quiz.CHAVES_VALIDAS, quiz.MAX_PESSOAS)
    assert r == {'nome': 'Ana'}


@pytest.mark.parametrize('respostas,campo', [
    ({'para_quem': 'Amigo', 'ocasiao': 'Dia das Mães', 'clima': 'animada', 'estilo': 'samba', 'voz': 'feminina'}, 'ocasiao'),
    ({'para_quem': 'Mãe', 'ocasiao': 'Natal', 'clima': 'romantica', 'estilo': 'samba', 'voz': 'feminina'}, 'clima'),
    ({'para_quem': 'Mãe', 'ocasiao': 'Natal', 'clima': 'animada', 'estilo': 'samba', 'voz': 'dupla'}, 'voz'),
    ({'para_quem': 'Chefe', 'ocasiao': 'Natal', 'clima': 'animada', 'estilo': 'samba', 'voz': 'feminina'}, 'para_quem'),
    ({'para_quem': 'Mãe', 'ocasiao': 'Natal', 'clima': 'animada', 'estilo': 'samba', 'voz': 'feminina'}, None),
])
def test_servidor_confere_a_combinacao(respostas, campo):
    assert quiz.combinacao_invalida(respostas) == campo


def test_navegador_recebe_as_listas_prontas_da_mesma_regra():
    cfg = quiz.config_do_navegador()
    assert cfg['ocasioes_por_relacao']['Amigo'] == quiz.ocasioes_para('Amigo')
    assert cfg['tons_por_relacao']['Esposa']['Pedido de desculpas'] == quiz.tons_para('Esposa', 'Pedido de desculpas')
    assert cfg['vozes_por_estilo']['gospel'] == quiz.vozes_para('gospel')
    assert cfg['guia_lembrancas'] == {**{r['valor']: cfg['guia_lembrancas'][r['valor']] for r in quiz.RELACOES}}
    assert cfg['guia_lembrancas']['Mais de uma pessoa'] == 'grupo' and cfg['guia_lembrancas']['Para mim'] == 'eu'
    assert cfg['guia_lembrancas']['Esposa'] == 'casal' and cfg['guia_lembrancas']['Mãe'] == 'padrao'
