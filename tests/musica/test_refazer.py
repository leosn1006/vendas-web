"""Admin → refazer a música de uma compra: rascunho (sem e-mail nem pedido) com as escolhas editáveis e a letra atual
dela de partida; só "usar" troca o conteúdo da música da cliente — mesmo token, pedido e presente; o vídeo é refeito
se ela tinha fotos (docs/MUSICA.md "Refazer a música de uma compra")."""
import pytest

from musica import casos_de_uso as uc
from musica.casos_de_uso import Recusa
from tests.musica.test_casos_de_uso import _com_previa, _pagar


def _paga(s, recursos=('musica',)):
    musica = _com_previa(s)
    assert _pagar(s, musica, recursos=recursos)
    return s.repositorio.por_id(musica['id'])


def _gerar(s, rascunho):
    uc.gerar_rascunho(s, rascunho['id'])
    uc.consultar(s, rascunho['id'])
    return s.repositorio.por_id(rascunho['id'])


def test_rascunho_comeca_com_a_letra_dela_e_nao_mexe_na_original(s):
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {'voz': 'masculina', 'apelido': 'Lena', 'ocasiao': 'Aniversário'})
    assert rascunho['rascunho_de'] == original['id'] and rascunho['email'] is None and rascunho['pedido_id'] is None
    assert rascunho['status'] == 'letra_pronta' and rascunho['letra_suno'] == original['letra_suno']
    assert rascunho['respostas']['voz'] == 'masculina' and rascunho['respostas']['apelido'] == 'Lena'
    assert s.repositorio.por_id(original['id']) == original
    with pytest.raises(Recusa, match='Já existe'):
        uc.criar_rascunho(s, original['id'], {})


def test_letra_nova_do_zero_manda_escrever(s):
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {}, letra_nova=True)
    assert rascunho['status'] == 'escrevendo' and ('letra', rascunho['id'], None) in s.agenda.chamadas


def test_musica_de_quiz_antigo_corrige_letra_sem_travar(s):
    """Sem ocasião (quiz antigo): mexer só no apelido/pronúncia não trava pela combinação."""
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {'pronuncia': 'Helena se fala Elena'})
    assert rascunho['respostas']['pronuncia'] == 'Helena se fala Elena'


def test_musica_de_quiz_antigo_troca_a_voz_sem_travar(s):
    """Sem ocasião (quiz antigo): trocar a voz confere só voz × estilo."""
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {'voz': 'masculina'})
    assert rascunho['respostas']['voz'] == 'masculina'
    with pytest.raises(Recusa, match='voz'):
        uc.editar_escolhas_rascunho(s, rascunho['id'], {'voz': 'coral'})   # coral só no gospel


def test_campos_da_cliente_e_combinacoes_invalidas(s):
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {'email': 'outra@x.com', 'whatsapp': '999', 'pedido_id': 1})
    assert 'email' not in rascunho['respostas'] and rascunho['email'] is None   # campos travados: ignorados
    completa = {'ocasiao': 'Aniversário', 'clima': 'emocionante'}   # as respostas de teste vêm sem ocasião (quiz antigo)
    with pytest.raises(Recusa, match='voz'):
        uc.editar_escolhas_rascunho(s, rascunho['id'], {**completa, 'estilo': 'samba', 'voz': 'dupla'})   # dupla: só sertanejo
    uc.editar_escolhas_rascunho(s, rascunho['id'], {**completa, 'estilo': 'sertanejo', 'voz': 'dupla'})
    assert s.repositorio.por_id(rascunho['id'])['respostas']['voz'] == 'dupla'
    with pytest.raises(Recusa, match='nome'):
        uc.editar_escolhas_rascunho(s, rascunho['id'], {'nome': ''})


def test_ajuste_da_ia_sem_limite_e_letra_a_mao(s):
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {})
    for _ in range(4):   # a cliente tem 2; o admin não tem limite
        uc.ajustar_rascunho(s, rascunho['id'], 'trocar Ju por Juju no refrão')
        uc.escrever_letra(s, rascunho['id'], 'trocar Ju por Juju no refrão')
    uc.editar_letra_rascunho(s, rascunho['id'], 'Pra Você, Juju', 'Juju, você é luz', '[Chorus]\nJuju, você é luz')
    r = s.repositorio.por_id(rascunho['id'])
    assert (r['titulo'], r['letra_suno'], r['status']) == ('Pra Você, Juju', '[Chorus]\nJuju, você é luz', 'letra_pronta')
    assert s.repositorio.por_id(original['id'])['letra_suno'] == original['letra_suno']


def test_gerar_e_usar_troca_o_conteudo_da_original_pelo_mesmo_link(s):
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {'voz': 'masculina', 'ocasiao': 'Aniversário'})
    uc.editar_letra_rascunho(s, rascunho['id'], 'Título novo', 'Letra nova', '[Verse]\nLetra nova')
    rascunho = _gerar(s, rascunho)
    assert rascunho['status'] == 'previa_pronta' and rascunho['faixas']
    with pytest.raises(Recusa, match='não existe ou já foi usado'):
        uc.usar_rascunho(s, original['id'])                                       # id da original não é rascunho
    resultado = uc.usar_rascunho(s, rascunho['id'], avisar=True)
    nova = s.repositorio.por_id(original['id'])
    assert (nova['token'], nova['pedido_id']) == (original['token'], original['pedido_id'])
    assert (nova['titulo'], nova['letra_suno'], nova['respostas']['voz']) == ('Título novo', '[Verse]\nLetra nova', 'masculina')
    assert nova['refeita_em'] and s.repositorio.por_id(rascunho['id'])['rascunho_usado_em']
    assert s.arquivos.completa(original['token'], 1).read_bytes() == s.arquivos.completa(rascunho['token'], 1).read_bytes()
    assert resultado == {'video': False, 'avisada': True}
    assert 'foi atualizada' in s.notificador.emails[-1]['assunto']
    assert s.repositorio.rascunho_ativo(original['id']) is None
    with pytest.raises(Recusa):
        uc.usar_rascunho(s, rascunho['id'])                                        # já usado


def test_sem_aviso_quando_a_caixinha_esta_desmarcada(s):
    original = _paga(s)
    rascunho = _gerar(s, uc.criar_rascunho(s, original['id'], {}))
    antes = len(s.notificador.emails)
    assert uc.usar_rascunho(s, rascunho['id'], avisar=False)['avisada'] is False
    assert len(s.notificador.emails) == antes


def test_refaz_o_video_com_as_fotos_dela(s):
    original = _paga(s, recursos=('musica', 'videoclipe'))
    fotos = s.arquivos.pasta_video(original['token']) / 'fotos'
    fotos.mkdir(parents=True)
    (fotos / '00.jpg').write_bytes(b'jpg')
    s.repositorio.atualizar(original['id'], video_status='pronto', video_versao=2)
    rascunho = _gerar(s, uc.criar_rascunho(s, original['id'], {}))
    assert uc.usar_rascunho(s, rascunho['id'], avisar=False)['video'] is True
    nova = s.repositorio.por_id(original['id'])
    assert nova['video_status'] == 'fazendo' and ('video', original['id']) in s.agenda.chamadas


def test_nao_usa_rascunho_sem_musica_e_nao_refaz_musica_nao_paga(s):
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {})
    with pytest.raises(Recusa, match='Crie a música'):
        uc.usar_rascunho(s, rascunho['id'])
    nao_paga = _com_previa(s)
    with pytest.raises(Recusa, match='já paga'):
        uc.criar_rascunho(s, nao_paga['id'], {})


def test_descartar_apaga_so_o_rascunho(s):
    original = _paga(s)
    rascunho = _gerar(s, uc.criar_rascunho(s, original['id'], {}))
    assert uc.descartar_rascunho(s, rascunho['id']) == original['id']
    assert s.repositorio.por_id(rascunho['id']) is None and s.repositorio.por_id(original['id'])['liberada_em']
    assert s.arquivos.completa(original['token'], 1).exists()


def test_rascunho_fora_dos_lembretes(s):
    original = _paga(s)
    uc.criar_rascunho(s, original['id'], {})
    assert all(not m.get('rascunho_de') for m in s.repositorio.candidatas_lembrete())


def test_rascunho_nao_aparece_pelo_token(s):
    """Página, checkout e presente chegam pelo token: o rascunho não pode ser comprado nem aberto."""
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {})
    assert s.repositorio.por_token(rascunho['token']) is None
    assert s.repositorio.por_token(original['token'])['id'] == original['id']


def test_nao_usa_enquanto_o_video_dela_esta_sendo_feito(s):
    original = _paga(s, recursos=('musica', 'videoclipe'))
    s.repositorio.atualizar(original['id'], video_status='fazendo')
    rascunho = _gerar(s, uc.criar_rascunho(s, original['id'], {}))
    with pytest.raises(Recusa, match='videoclipe'):
        uc.usar_rascunho(s, rascunho['id'])
    assert s.repositorio.rascunho_ativo(original['id'])['id'] == rascunho['id']


def test_falha_na_copia_nao_mexe_na_original(s):
    original = _paga(s)
    rascunho = _gerar(s, uc.criar_rascunho(s, original['id'], {}))
    antes = s.arquivos.completa(original['token'], 1).read_bytes()
    s.arquivos.previa(rascunho['token'], 2).unlink()   # falta um arquivo do rascunho
    with pytest.raises(Recusa, match='não mudou'):
        uc.usar_rascunho(s, rascunho['id'])
    assert s.arquivos.completa(original['token'], 1).read_bytes() == antes
    assert not list(s.arquivos.pasta(original['token']).rglob('*.novo'))
    assert s.repositorio.por_id(original['id'])['titulo'] == original['titulo']
    assert s.repositorio.rascunho_ativo(original['id'])['id'] == rascunho['id']   # pode tentar de novo


def test_sem_aviso_se_o_pedido_nao_esta_mais_pago(s, monkeypatch):
    original = _paga(s)
    rascunho = _gerar(s, uc.criar_rascunho(s, original['id'], {}))
    monkeypatch.setattr(s.repositorio, 'pedido_pago', lambda pedido_id: None)   # ex.: devolvido
    antes = len(s.notificador.emails)
    assert uc.usar_rascunho(s, rascunho['id'], avisar=True)['avisada'] is False
    assert len(s.notificador.emails) == antes


def test_clique_duplo_no_ajuste_manda_escrever_uma_vez(s):
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {})   # o que a 2ª requisição leu (letra pronta)
    uc.ajustar_rascunho(s, rascunho['id'], 'trocar Ju por Juju')
    with pytest.raises(Recusa, match='já está sendo escrita'):
        uc._escrever_rascunho(s, rascunho, 'trocar Ju por Juju')
    assert sum(1 for c in s.agenda.chamadas if c[:2] == ('letra', rascunho['id'])) == 1


def test_clique_duplo_no_usar_avisa_uma_vez(s):
    original = _paga(s)
    rascunho = _gerar(s, uc.criar_rascunho(s, original['id'], {}))
    assert s.repositorio.marcar_rascunho_usado(rascunho['id'])   # a 1ª requisição marcou
    with pytest.raises(Recusa, match='já foi usado'):
        uc.usar_rascunho(s, rascunho['id'])


def test_mudar_escolhas_depois_de_gerar_pede_gerar_de_novo(s):
    original = _paga(s)
    rascunho = _gerar(s, uc.criar_rascunho(s, original['id'], {}))
    uc.editar_escolhas_rascunho(s, rascunho['id'], {'voz': 'masculina'})
    assert s.repositorio.por_id(rascunho['id'])['status'] == 'letra_pronta'
    with pytest.raises(Recusa, match='Crie a música'):
        uc.usar_rascunho(s, rascunho['id'])


def test_nao_faz_video_que_ela_nao_pediu(s):
    original = _paga(s, recursos=('musica', 'videoclipe'))
    fotos = s.arquivos.pasta_video(original['token']) / 'fotos'
    fotos.mkdir(parents=True)
    (fotos / '00.jpg').write_bytes(b'jpg')   # mandou fotos, mas não clicou em fazer o vídeo
    rascunho = _gerar(s, uc.criar_rascunho(s, original['id'], {}))
    assert uc.usar_rascunho(s, rascunho['id'], avisar=False)['video'] is False
    assert s.repositorio.por_id(original['id'])['video_status'] is None


def test_nao_descarta_no_meio_da_geracao(s):
    original = _paga(s)
    rascunho = uc.criar_rascunho(s, original['id'], {})
    uc.gerar_rascunho(s, rascunho['id'])
    with pytest.raises(Recusa, match='sendo criada'):
        uc.descartar_rascunho(s, rascunho['id'])
