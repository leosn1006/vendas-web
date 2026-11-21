"""O fluxo da Música com adaptadores falsos: antes de pagar, checkout, liberação, presente e videoclipe."""
import io
from datetime import datetime, timedelta

import pytest

from musica import casos_de_uso as uc
from musica import config
from musica.casos_de_uso import Recusa
from musica.dominio.modelos import GERACAO_FALHOU, ErroGerador, ErroLetra, ResultadoGeracao
from tests.musica.conftest import RESPOSTAS

PRODUTO = 20


def _nova(s, **campos):
    musica = uc.criar_musica(s, PRODUTO, dict(RESPOSTAS), 'patricia@exemplo.com', '', '1.2.3.4', 99, 'site.com.br')
    if campos:
        s.repositorio.atualizar(musica['id'], **campos)
    return s.repositorio.por_id(musica['id'])


def _com_previa(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])
    uc.gerar(s, musica['token'], '1.2.3.4')
    uc.consultar(s, musica['id'])
    return s.repositorio.por_id(musica['id'])


def _pagar(s, musica, pedido_id=500, recursos=('musica',), guid='g-500'):
    s.repositorio.pedidos[pedido_id] = {'id': pedido_id, 'guid': guid, 'email': 'patricia@exemplo.com',
                                        'estado_id': 1000, 'dns_origem': 'site.com.br'}
    s.repositorio.itens[pedido_id] = list(recursos)
    uc.vincular_ao_pedido(s, musica['token'], pedido_id, PRODUTO)
    return uc.liberar_do_pedido(s, pedido_id)


# ============================================================ antes de pagar

def test_criar_agenda_a_letra(s):
    musica = _nova(s)
    assert musica['status'] == 'escrevendo' and musica['pedido_origem_id'] == 99
    assert s.agenda.chamadas == [('letra', musica['id'], None)]


@pytest.mark.parametrize('falta', ['nome', 'lembrancas', 'de'])
def test_criar_exige_o_essencial(s, falta):
    respostas = {k: v for k, v in RESPOSTAS.items() if k != falta}
    with pytest.raises(Recusa):
        uc.criar_musica(s, PRODUTO, respostas, 'a@b.com', '', 'ip')


def test_letra_pronta_e_erro_da_ia(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])
    pronta = s.repositorio.por_id(musica['id'])
    assert pronta['status'] == 'letra_pronta' and 'Dona Lena' in pronta['titulo'] and pronta['modelo_letra'] == 'simulado'

    outra = _nova(s)

    class EscritorQueFalha:
        modelo = 'x'

        def escrever(self, *a, **k):
            raise ErroLetra('fora do ar')
    s.escritor = EscritorQueFalha()
    uc.escrever_letra(s, outra['id'])
    assert s.repositorio.por_id(outra['id'])['status'] == 'erro_letra'
    assert s.notificador.alertas


def test_ajuste_reescreve_com_a_letra_anterior_e_tem_limite(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])
    for _ in range(config.LIMITE_AJUSTES_LETRA):
        uc.pedir_ajuste(s, musica['token'], 'Troque Lele por Lena')
        assert s.agenda.chamadas[-1] == ('letra', musica['id'], 'Troque Lele por Lena')
        uc.escrever_letra(s, musica['id'], 'Troque Lele por Lena')
    with pytest.raises(Recusa, match='todos os ajustes'):
        uc.pedir_ajuste(s, musica['token'], 'mais um')


def test_gerar_ate_a_previa(s):
    musica = _com_previa(s)
    assert musica['status'] == 'previa_pronta' and musica['geracoes'] == 1 and musica['provedor'] == 'simulado'
    assert [f['numero'] for f in musica['faixas']] == [1, 2]
    assert s.arquivos.previa(musica['token'], 1).read_bytes() == b'35:40'   # 40 s a partir do refrão
    assert s.arquivos.completa(musica['token'], 2).exists()


def test_gerar_tem_limite_por_dia_e_nao_gasta_em_dobro(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])
    s.repositorio.geracoes_24h = config.LIMITE_PREVIAS_DIA
    with pytest.raises(Recusa) as r:
        uc.gerar(s, musica['token'], 'ip')
    assert r.value.status == 429
    s.repositorio.geracoes_24h = 0
    uc.gerar(s, musica['token'], 'ip')
    with pytest.raises(Recusa, match='já está sendo criada'):   # clique duplo
        uc.gerar(s, musica['token'], 'ip')


def test_gerador_recusou_volta_para_a_letra(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])

    class GeradorFora:
        nome = 'x'

        def criar(self, *a):
            raise ErroGerador('sem crédito')
    s.gerador = GeradorFora()
    with pytest.raises(Recusa) as r:
        uc.gerar(s, musica['token'], 'ip')
    assert r.value.status == 503 and s.repositorio.por_id(musica['id'])['status'] == 'letra_pronta'
    assert any('sem crédito' in a for a in s.notificador.alertas)


def test_falha_do_gerador_tenta_de_novo_ate_o_limite(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])
    uc.gerar(s, musica['token'], 'ip')
    for _ in range(config.MAX_TENTATIVAS_GERACAO):
        uc.tratar_resultado(s, s.repositorio.por_id(musica['id']), ResultadoGeracao(GERACAO_FALHOU, erro='x'))
    final = s.repositorio.por_id(musica['id'])
    assert final['status'] == 'erro' and final['geracoes'] == config.MAX_TENTATIVAS_GERACAO
    assert any('não gerou' in a for a in s.notificador.alertas)


def test_geracao_travada_conta_como_falha(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])

    class GeradorLento:
        nome = 'lento'

        def criar(self, *a):
            return 'job-lento'

        def consultar(self, job_id):
            return ResultadoGeracao('gerando')
    s.gerador = GeradorLento()
    uc.gerar(s, musica['token'], 'ip')
    assert uc.consultar(s, musica['id']) is True          # ainda compondo: consultar de novo
    s.repositorio.atualizar(musica['id'], gerando_desde=datetime.now() - timedelta(minutes=config.MINUTOS_PARA_TRAVA + 1))
    uc.consultar(s, musica['id'])
    assert s.repositorio.por_id(musica['id'])['geracoes'] == 2   # travou → mandou gerar de novo


def test_download_falhou_volta_para_gerando(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])
    uc.gerar(s, musica['token'], 'ip')
    s.audio.falhar = True
    assert uc.consultar(s, musica['id']) is True   # a tarefa agenda a próxima (uma cadeia só)
    assert s.repositorio.por_id(musica['id'])['status'] == 'gerando'
    s.repositorio.atualizar(musica['id'],
                            gerando_desde=datetime.now() - timedelta(minutes=3 * config.MINUTOS_PARA_TRAVA + 1))
    assert uc.consultar(s, musica['id']) is False   # falha que persiste: para de tentar
    assert s.repositorio.por_id(musica['id'])['status'] == 'erro'


def test_outra_versao_que_falhou_mantem_a_previa(s):
    musica = _com_previa(s)
    uc.outra_versao(s, musica['token'])
    atual = s.repositorio.por_id(musica['id'])
    s.repositorio.atualizar(musica['id'], geracoes=config.MAX_TENTATIVAS_GERACAO)
    uc.tratar_resultado(s, s.repositorio.por_id(musica['id']), ResultadoGeracao(GERACAO_FALHOU, erro='x'))
    assert atual['faixas'] and s.repositorio.por_id(musica['id'])['status'] == 'previa_pronta'


def test_ajuste_que_falhou_mantem_a_letra(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])
    uc.pedir_ajuste(s, musica['token'], 'Troque Lele por Lena')

    class EscritorQueFalha:
        modelo = 'x'

        def escrever(self, *a, **k):
            raise ErroLetra('fora do ar')
    s.escritor = EscritorQueFalha()
    uc.escrever_letra(s, musica['id'], 'Troque Lele por Lena')
    assert s.repositorio.por_id(musica['id'])['status'] == 'letra_pronta'


def test_outra_versao_so_uma_vez(s):
    musica = _com_previa(s)
    uc.outra_versao(s, musica['token'])
    uc.consultar(s, musica['id'])
    with pytest.raises(Recusa):
        uc.outra_versao(s, musica['token'])


# ================================================================== checkout

def test_checkout_so_vende_musica_pronta_do_produto(s):
    musica = _nova(s)
    with pytest.raises(Recusa, match='ainda não ficou pronta'):
        uc.musica_para_checkout(s, musica['token'], PRODUTO)
    musica = _com_previa(s)
    with pytest.raises(Recusa, match='Não encontramos'):
        uc.musica_para_checkout(s, musica['token'], PRODUTO + 1)
    with pytest.raises(Recusa):
        uc.musica_para_checkout(s, '', PRODUTO)
    assert uc.musica_para_checkout(s, musica['token'], PRODUTO)['id'] == musica['id']


def test_musica_comprada_nao_vai_de_novo_ao_checkout(s):
    musica = _com_previa(s)
    assert _pagar(s, musica)
    with pytest.raises(Recusa, match='já foi comprada'):
        uc.musica_para_checkout(s, musica['token'], PRODUTO)


# ================================================================= liberação

def test_liberar_e_idempotente(s):
    musica = _com_previa(s)
    assert _pagar(s, musica) is True
    assert uc.liberar_do_pedido(s, 500) is False
    liberada = s.repositorio.por_id(musica['id'])
    assert liberada['liberada_em'] and liberada['pedido_id'] == 500


def test_nao_libera_pedido_nao_pago_nem_sem_item_de_musica(s):
    musica = _com_previa(s)
    s.repositorio.pedidos[501] = {'id': 501, 'guid': 'g', 'email': 'x', 'estado_id': 1002}
    s.repositorio.itens[501] = ['musica']
    uc.vincular_ao_pedido(s, musica['token'], 501, PRODUTO)
    assert uc.liberar_do_pedido(s, 501) is False                    # PIX ainda não pago
    s.repositorio.pedidos[502] = {'id': 502, 'guid': 'g2', 'email': 'x', 'estado_id': 1000}
    assert uc.liberar_do_pedido(s, 502) is False                    # pedido de e-book: nada a fazer
    assert not s.notificador.alertas


def test_dois_pix_da_mesma_musica_o_primeiro_pago_libera(s):
    musica = _com_previa(s)
    s.repositorio.pedidos[600] = {'id': 600, 'guid': 'g600', 'email': 'x', 'estado_id': 1002}
    s.repositorio.itens[600] = ['musica']
    uc.vincular_ao_pedido(s, musica['token'], 600, PRODUTO)        # gerou um PIX e não pagou
    assert _pagar(s, musica, pedido_id=601, guid='g601')            # gerou outro e pagou este
    s.repositorio.pedidos[600]['estado_id'] = 1000                  # e depois pagou o primeiro também
    assert uc.liberar_do_pedido(s, 600) is False
    assert any('paga de novo' in a for a in s.notificador.alertas)   # atendimento avalia a devolução


def test_pago_sem_musica_avisa_a_equipe(s):
    s.repositorio.pedidos[700] = {'id': 700, 'guid': 'g', 'email': 'x', 'estado_id': 1000}
    s.repositorio.itens[700] = ['musica']
    assert uc.liberar_do_pedido(s, 700) is False
    assert any('sem música' in a for a in s.notificador.alertas)


def test_manutencao_libera_pago_que_ficou_para_tras(s):
    musica = _com_previa(s)
    s.repositorio.pedidos[800] = {'id': 800, 'guid': 'g800', 'email': 'x', 'estado_id': 1000}
    s.repositorio.itens[800] = ['musica']
    uc.vincular_ao_pedido(s, musica['token'], 800, PRODUTO)        # a tarefa do e-mail não rodou
    assert uc.manutencao(s)['liberadas'] == 1
    assert s.repositorio.por_id(musica['id'])['liberada_em']


def test_compra_e_pagina_do_presente(s):
    musica = _com_previa(s)
    with pytest.raises(Recusa):
        uc.musica_liberada(s, musica['token'])                       # antes de pagar, nada de música completa
    _pagar(s, musica, recursos=('musica', 'qrcode'))
    pedido, m, recursos = uc.compra(s, 'g-500')
    assert m['id'] == musica['id'] and recursos == {'musica', 'qrcode'}
    assert uc.musica_liberada(s, musica['token'])[0]['id'] == musica['id']
    with pytest.raises(Recusa):
        uc.compra(s, 'guid-que-nao-existe')


# ================================================================ presente

def test_presente_por_email_so_com_o_bump(s):
    musica = _com_previa(s)
    _pagar(s, musica)
    with pytest.raises(Recusa) as r:
        uc.agendar_presente(s, 'g-500', 'Lena', 'lena@exemplo.com', '', None)
    assert r.value.status == 403


def test_presente_agora_vai_com_copia_para_quem_comprou(s):
    musica = _com_previa(s)
    _pagar(s, musica, recursos=('musica', 'entrega_email'))
    uc.agendar_presente(s, 'g-500', 'Dona Lena', 'lena@exemplo.com', 'Feliz aniversário!', None)
    assert s.agenda.chamadas[-1] == ('presentes',)
    assert uc.enviar_presentes(s) == 1
    email = s.notificador.emails[0]
    assert email['destino'] == 'lena@exemplo.com' and email['cc'] == 'patricia@exemplo.com'
    assert f"/musica/m/{musica['token']}" in email['html'] and 'Feliz aniversário!' in email['html']
    assert 'Patrícia' in email['assunto']
    assert uc.enviar_presentes(s) == 0                                # nunca envia duas vezes
    with pytest.raises(Recusa, match='já foi enviada'):
        uc.agendar_presente(s, 'g-500', 'Lena', 'lena@exemplo.com', '', None)


def test_presente_agendado_espera_a_hora(s):
    musica = _com_previa(s)
    _pagar(s, musica, recursos=('musica', 'entrega_email'))
    uc.agendar_presente(s, 'g-500', 'Lena', 'lena@exemplo.com', '', datetime.now() + timedelta(days=2))
    assert ('presentes',) not in s.agenda.chamadas
    assert uc.enviar_presentes(s) == 0
    s.repositorio.atualizar(musica['id'], presente_em=datetime.now() - timedelta(minutes=1))
    assert uc.enviar_presentes(s) == 1


def _presente_enviado(s):
    musica = _com_previa(s)
    _pagar(s, musica, recursos=('musica', 'entrega_email'))
    uc.agendar_presente(s, 'g-500', 'Lena', 'lena@exemplo.com', '', None)
    assert uc.enviar_presentes(s) == 1
    return s.repositorio.por_id(musica['id'])


def _vencer_espera(s, musica_id):
    s.repositorio.atualizar(musica_id, presente_em=datetime.now() - timedelta(minutes=1))


def test_erro_no_envio_tenta_de_novo_daqui_a_1h(s):
    musica = _com_previa(s)
    _pagar(s, musica, recursos=('musica', 'entrega_email'))
    uc.agendar_presente(s, 'g-500', 'Lena', 'lena@exemplo.com', '', None)
    original = s.notificador.email

    def falha(*a, **k):
        raise RuntimeError('Gmail fora')
    s.notificador.email = falha
    assert uc.enviar_presentes(s) == 0
    m = s.repositorio.por_id(musica['id'])
    assert m['presente_enviado_em'] is None and m['presente_tentativas'] == 1
    assert timedelta(minutes=55) < m['presente_em'] - datetime.now() <= timedelta(hours=1)
    assert uc.enviar_presentes(s) == 0                      # antes da hora, não tenta
    s.notificador.email = original
    _vencer_espera(s, musica['id'])
    assert uc.enviar_presentes(s) == 1


def test_devolucao_caixa_lotada_reenvia_com_esperas_e_desiste_no_quarto(s):
    musica = _presente_enviado(s)
    assert musica['presente_thread_id'] == 'thread-1'
    esperas = []
    for _ in range(3):   # 3 devoluções: reenvia em 1 h, 2 h e 4 h, sempre com cópia para quem comprou
        assert uc.presente_devolvido(s, s.repositorio.por_id(musica['id'])['presente_thread_id'],
                                     ['lena@exemplo.com']) is True
        m = s.repositorio.por_id(musica['id'])
        esperas.append(round((m['presente_em'] - datetime.now()).total_seconds() / 3600))
        _vencer_espera(s, musica['id'])
        assert uc.enviar_presentes(s) == 1
    assert esperas == [1, 2, 4]
    presentes = [e for e in s.notificador.emails if e['destino'] == 'lena@exemplo.com']
    assert len(presentes) == 4 and all(e['cc'] == 'patricia@exemplo.com' for e in presentes)
    # 4ª devolução: desiste, avisa quem comprou (com o link para mandar por conta própria) e a equipe
    assert uc.presente_devolvido(s, s.repositorio.por_id(musica['id'])['presente_thread_id'], ['lena@exemplo.com'])
    m = s.repositorio.por_id(musica['id'])
    assert m['presente_falhou_em'] and m['presente_enviado_em']
    aviso = s.notificador.emails[-1]
    assert aviso['destino'] == 'patricia@exemplo.com' and f"/musica/m/{musica['token']}" in aviso['html']
    assert any('não chegou' in a for a in s.notificador.alertas)
    assert uc.enviar_presentes(s) == 0                      # nunca mais tenta
    assert uc.presente_devolvido(s, m['presente_thread_id'], ['lena@exemplo.com']) is False


def test_depois_de_desistir_ela_pode_corrigir_o_email(s):
    musica = _presente_enviado(s)
    for _ in range(4):
        uc.presente_devolvido(s, 'thread-1', ['lena@exemplo.com'])
        s.repositorio.atualizar(musica['id'], presente_em=datetime.now() - timedelta(minutes=1))
        uc.enviar_presentes(s)
    assert s.repositorio.por_id(musica['id'])['presente_falhou_em']
    uc.agendar_presente(s, 'g-500', 'Lena', 'lena.certo@exemplo.com', '', None)   # o e-mail tinha erro de digitação
    m = s.repositorio.por_id(musica['id'])
    assert m['presente_falhou_em'] is None and m['presente_tentativas'] == 0
    assert uc.enviar_presentes(s) == 1 and s.notificador.emails[-1]['destino'] == 'lena.certo@exemplo.com'


def test_envio_interrompido_e_reenviado(s):
    musica = _presente_enviado(s)
    s.repositorio.musicas[musica['id']]['_envio_interrompido'] = True   # o worker caiu antes do Gmail
    s.repositorio.musicas[musica['id']]['presente_thread_id'] = None      # (o e-mail não chegou a sair)
    assert uc.manutencao(s)['presentes'] == 1                            # a mesma rodada já reenvia
    assert [e['destino'] for e in s.notificador.emails] == ['lena@exemplo.com', 'lena@exemplo.com']


def test_devolucao_da_copia_de_quem_comprou_nao_reenvia(s):
    musica = _presente_enviado(s)
    assert uc.presente_devolvido(s, 'thread-1', ['patricia@exemplo.com']) is True
    m = s.repositorio.por_id(musica['id'])
    assert m['presente_tentativas'] == 1 and m['presente_enviado_em']   # o presente chegou: nada muda


def test_devolucao_que_nao_e_de_presente(s):
    assert uc.presente_devolvido(s, 'thread-de-outro-email', ['fulano@x.com']) is False
    assert uc.presente_devolvido(s, '', ['ana@x.com']) is False      # 'ana@x.com' não casa com 'joana@x.com'


def test_devolucao_sem_destinatario_no_thread_do_presente_reenvia(s):
    """Devolução que não diz quem recusou, no thread do presente: o pago é a entrega, então tenta de novo."""
    musica = _presente_enviado(s)
    assert uc.presente_devolvido(s, 'thread-1', []) is True
    assert s.repositorio.por_id(musica['id'])['presente_enviado_em'] is None


def test_limite_diario_nao_conta_as_tentativas_automaticas(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])
    uc.gerar(s, musica['token'], 'ip')
    for _ in range(config.MAX_TENTATIVAS_GERACAO - 1):     # o gerador falhou: nós tentamos de novo
        uc.tratar_resultado(s, s.repositorio.por_id(musica['id']), ResultadoGeracao(GERACAO_FALHOU, erro='x'))
    assert s.repositorio.por_id(musica['id'])['geracoes'] == config.MAX_TENTATIVAS_GERACAO


# ============================================================== videoclipe

def test_videoclipe_so_no_plano_com_video(s):
    musica = _com_previa(s)
    _pagar(s, musica)
    with pytest.raises(Recusa) as r:
        uc.receber_foto(s, 'g-500', io.BytesIO(b'foto'), True)
    assert r.value.status == 403


def test_videoclipe_foto_por_foto_e_monta(s):
    musica = _com_previa(s)
    _pagar(s, musica, recursos=('musica', 'videoclipe'))
    with pytest.raises(Recusa, match='pelo menos uma foto'):
        uc.iniciar_video(s, 'g-500', 1, False)
    assert uc.receber_foto(s, 'g-500', io.BytesIO(b'f1'), True) == 1
    assert uc.receber_foto(s, 'g-500', io.BytesIO(b'f2'), False) == 2
    assert uc.receber_foto(s, 'g-500', io.BytesIO(b'f3'), True) == 1          # recomeçou a seleção
    assert uc.receber_foto(s, 'g-500', io.BytesIO(b'f4'), False) == 2
    uc.iniciar_video(s, 'g-500', 2, False)
    assert s.agenda.chamadas[-1] == ('video', musica['id'])
    with pytest.raises(Recusa, match='já está sendo feito'):
        uc.receber_foto(s, 'g-500', io.BytesIO(b'f5'), True)
    uc.fazer_video(s, musica['id'])
    feito = s.repositorio.por_id(musica['id'])
    assert feito['video_status'] == 'pronto' and feito['video_versao'] == 2
    assert s.video.montados == [(2, feito['titulo'], 'Dona Lena', 'Patrícia')]
    assert s.arquivos.videoclipe(musica['token']).exists()


def test_videoclipe_limite_de_fotos(s):
    musica = _com_previa(s)
    _pagar(s, musica, recursos=('musica', 'videoclipe'))
    for i in range(20):
        uc.receber_foto(s, 'g-500', io.BytesIO(b'f'), i == 0)
    with pytest.raises(Recusa, match='até 20'):
        uc.receber_foto(s, 'g-500', io.BytesIO(b'f'), False)


def test_videoclipe_preso_retoma_uma_vez_e_depois_libera(s):
    musica = _com_previa(s)
    _pagar(s, musica, recursos=('musica', 'videoclipe'))
    uc.receber_foto(s, 'g-500', io.BytesIO(b'f'), True)
    uc.iniciar_video(s, 'g-500', 1, False)
    s.repositorio.musicas[musica['id']]['_parado'] = True       # o worker reiniciou no meio da montagem
    uc.manutencao(s)
    assert s.agenda.chamadas[-1] == ('video', musica['id'])
    uc.manutencao(s)                                             # parou de novo
    m = s.repositorio.por_id(musica['id'])
    assert m['video_status'] == 'erro' and any('parou duas vezes' in a for a in s.notificador.alertas)
    uc.receber_foto(s, 'g-500', io.BytesIO(b'f'), True)          # e ela pode tentar outra vez


# ============================================================== revisão

def test_consulta_que_quebra_cai_na_trava(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])

    class GeradorQuebrado:
        nome = 'quebrado'

        def criar(self, *a):
            return 'job-x'

        def consultar(self, job_id):
            raise KeyError('audioUrl')
    s.gerador = GeradorQuebrado()
    uc.gerar(s, musica['token'], 'ip')
    assert uc.consultar(s, musica['id']) is True                 # ainda dentro do tempo: tenta de novo
    s.repositorio.atualizar(musica['id'], gerando_desde=datetime.now() - timedelta(minutes=config.MINUTOS_PARA_TRAVA + 1))
    uc.consultar(s, musica['id'])
    assert s.repositorio.por_id(musica['id'])['geracoes'] == 2  # travou → nova tentativa (e, no fim, erro + aviso)


def test_apiframe_concluido_sem_audio_e_falha():
    from musica.adaptadores.gerador_apiframe import interpretar_job
    r = interpretar_job({'status': 'COMPLETED', 'result': {'tracks': [{'duration': 10}]}})
    assert r.status == GERACAO_FALHOU


def test_ajuste_perdido_volta_para_a_letra_anterior(s):
    musica = _nova(s)
    uc.escrever_letra(s, musica['id'])
    uc.pedir_ajuste(s, musica['token'], 'troque o apelido')
    s.repositorio.paradas = lambda status, minutos: [musica['id']] if status == 'escrevendo' else []
    uc.manutencao(s)
    m = s.repositorio.por_id(musica['id'])
    assert m['status'] == 'letra_pronta' and m['letra_suno'] and m['ajustes_letra'] == 0


def test_pago_sem_itens_gravados_libera_a_musica_e_avisa(s):
    musica = _com_previa(s)
    assert _pagar(s, musica, recursos=()) is True
    assert s.repositorio.por_id(musica['id'])['liberada_em']
    assert any('sem os itens gravados' in a for a in s.notificador.alertas)


def test_limite_de_letras_por_dia(s):
    for _ in range(config.LIMITE_LETRAS_DIA):
        _nova(s)
    with pytest.raises(Recusa) as r:
        _nova(s)
    assert r.value.status == 429


# ================================================================== webhook

def test_webhook_de_outro_provedor_e_ignorado(s):
    assert uc.aviso_do_gerador(s, 'apiframe', b'{}', {}) is False


def test_presente_corrige_o_de_ao_agendar(s):
    """"de Rose para Rose": o comprador pôs o nome de quem recebe no "Seu nome" do quiz e corrige ao agendar."""
    musica = _com_previa(s)
    s.repositorio.atualizar(musica['id'], respostas={**musica['respostas'], 'de': 'Helena'})
    _pagar(s, musica, recursos=('musica', 'entrega_email'))
    uc.agendar_presente(s, 'g-500', 'Helena', 'lena@exemplo.com', '', None, de='  Euripedes ')
    assert s.repositorio.por_id(musica['id'])['respostas']['de'] == 'Euripedes'
    uc.enviar_presentes(s)
    assert s.notificador.emails[0]['assunto'].startswith('Euripedes fez uma música')
    s.repositorio.atualizar(musica['id'], presente_enviado_em=None, presente_thread_id=None)   # campo vazio não apaga o "de"
    uc.agendar_presente(s, 'g-500', 'Helena', 'lena@exemplo.com', '', None, de='')
    assert s.repositorio.por_id(musica['id'])['respostas']['de'] == 'Euripedes'


def test_presente_para_mim_nao_muda_o_de(s):
    musica = _com_previa(s)
    s.repositorio.atualizar(musica['id'], respostas={**musica['respostas'], 'para_quem': 'Para mim', 'de': 'Helena'})
    _pagar(s, musica, recursos=('musica', 'entrega_email'))
    assert uc.pode_mudar_de(s.repositorio.por_id(musica['id'])) is False
    uc.agendar_presente(s, 'g-500', 'Helena', 'lena@exemplo.com', '', None, de='Outra')
    assert s.repositorio.por_id(musica['id'])['respostas']['de'] == 'Helena'


def test_presente_nao_muda_o_de_depois_que_um_canal_saiu_e_recusa_nome_estranho(s):
    musica = _com_previa(s)
    _pagar(s, musica, recursos=('musica', 'entrega_email'))
    with pytest.raises(Recusa, match='seu nome'):
        uc.agendar_presente(s, 'g-500', 'Helena', 'lena@exemplo.com', '', None, de='11 99999-9999')
    s.repositorio.atualizar(musica['id'], presente_wa_status='falhou', presente_thread_id='t-1')   # o e-mail já saiu
    assert uc.pode_mudar_de(s.repositorio.por_id(musica['id'])) is False
    uc.agendar_presente(s, 'g-500', 'Helena', 'lena@exemplo.com', '', None, de='Outro')
    assert s.repositorio.por_id(musica['id'])['respostas']['de'] == 'Patrícia'
