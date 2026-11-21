"""
IA do WhatsApp com contexto de pagamento (nov/2026).

Bug em produção: a cliente mandava o comprovante e logo depois "Segue" / "Coloquei 30"; a IA, sem saber que o
pedido estava pago (recebia a foto do webhook, estado 13), pedia "nome do pagador, valor e horário" ou escalava
como estorno (pedidos 457320, 458105, 444760, 450903, 454261, 461974).
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

import agente_resposta_produto as agente
from fluxos import fluxo_responder


def _webhook(texto):
    return {'entry': [{'changes': [{'value': {'messages': [{'id': 'wamid.C', 'text': {'body': texto}}]}}]}]}


@pytest.fixture
def cenario(monkeypatch):
    estado = {'pedido_banco': None, 'decisao': None, 'ia_chamada': 0, 'travas': [], 'trava_ok': True}
    agendadas, salvas = [], []

    monkeypatch.setattr(fluxo_responder, 'get_pedido', lambda _id: estado['pedido_banco'])
    monkeypatch.setattr(fluxo_responder, 'tem_notificacao_em_analise', lambda _p: False)
    cvv_reservados = set()

    def reservar_cvv(pid):
        if pid in cvv_reservados:
            return False
        cvv_reservados.add(pid)
        return True
    monkeypatch.setattr(fluxo_responder, '_reservar_cvv', reservar_cvv)
    monkeypatch.setattr(fluxo_responder, '_liberar_cvv', lambda pid: cvv_reservados.discard(pid))
    alertas_abertos = set()
    monkeypatch.setattr(fluxo_responder, 'tem_notificacao_em_analise_por_motivo',
                        lambda pid, motivo: (pid, motivo) in alertas_abertos)
    estado['alertas_abertos'], estado['cvv_reservados'] = alertas_abertos, cvv_reservados
    monkeypatch.setattr(fluxo_responder, 'contar_total_mensagens_pedido', lambda _p: 1)
    monkeypatch.setattr(fluxo_responder, 'buscar_ultima_mensagem_recebida_por_pedido', lambda *_a, **_k: None)
    monkeypatch.setattr(fluxo_responder, 'get_produto_by_id', lambda _p: {'prompt_vendas': 'x', 'nome': 'P'})
    monkeypatch.setattr(fluxo_responder, 'buscar_historico_conversa', lambda *_a, **_k: [])
    monkeypatch.setattr(fluxo_responder, 'salvar_mensagem_pedido', lambda *a, **k: salvas.append(a))

    def travar(pid, estado_atual, estado_travado):
        estado['travas'].append((pid, estado_atual, estado_travado))
        return estado['trava_ok']
    monkeypatch.setattr(fluxo_responder, 'tentar_travar_fluxo', travar, raising=False)  # não pode ser chamada

    def ia(*_a):
        estado['ia_chamada'] += 1
        return estado['decisao']
    monkeypatch.setattr(fluxo_responder, 'responder_cliente_com_historico_produto', ia)
    monkeypatch.setattr(fluxo_responder.celery_app, 'send_task',
                        lambda nome, args, kwargs=None, countdown=None: agendadas.append((nome, args, kwargs)))
    notificacoes = []
    monkeypatch.setattr(fluxo_responder, 'criar_notificacao_admin',
                        lambda _p, _pr, motivo, _m='', mesmo_em_analise=False: notificacoes.append((motivo, mesmo_em_analise)))
    estado['agendadas'], estado['salvas'], estado['notificacoes'] = agendadas, salvas, notificacoes
    return estado


PEDIDO_WEBHOOK = {'id': 7, 'produto_id': 11, 'estado_id': 13, 'valor_pago': 0}


# ─── espera do comprovante ───────────────────────────────────────────────────

def test_comprovante_em_analise_reagenda_sem_chamar_a_ia(cenario):
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 13, 'valor_pago': 0}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('Coloquei 30'))
    assert cenario['ia_chamada'] == 0
    [(nome, _args, kwargs)] = cenario['agendadas']
    assert nome == 'tasks.responder_mensagem' and kwargs == {'tentativa_espera': 1}


def test_depois_do_limite_de_espera_segue_para_a_ia(cenario):
    """A trava 13 não tem prazo: sem limite, um worker morto faria o reagendamento eterno."""
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 13, 'valor_pago': 0}
    cenario['decisao'] = {'acao': 'responder', 'texto': 'oi', 'valor': None}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('quando chega?'), tentativa_espera=5)
    assert cenario['ia_chamada'] == 1


def test_pedido_relido_ja_pago_vai_para_a_ia_com_os_dados_do_banco(cenario, monkeypatch):
    """A foto do webhook dizia 13 / não pago; o banco já diz 0 / pago. A IA recebe o do banco."""
    recebido = {}
    monkeypatch.setattr(fluxo_responder, 'responder_cliente_com_historico_produto',
                        lambda _m, _h, _p, pedido: recebido.update(pedido) or
                        {'acao': 'silenciar', 'texto': None, 'valor': None})
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 0, 'valor_pago': 30}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('Coloquei 30'))
    assert recebido['estado_id'] == 0 and recebido['valor_pago'] == 30
    assert cenario['agendadas'] == []  # silenciar: nada enviado


# ─── filtro de mensagens sem resposta ────────────────────────────────────────

def test_obrigada_nao_chama_ia_nem_envia(cenario):
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 0, 'valor_pago': 10}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('Obrigada Deus abençoe 🙏'))
    assert cenario['ia_chamada'] == 0
    assert cenario['agendadas'] == []
    assert len(cenario['salvas']) == 1  # a mensagem fica no histórico


# ─── decisões da IA ──────────────────────────────────────────────────────────

def test_pagamento_informado_agenda_o_fluxo_do_comprovante_sem_travar(cenario):
    """Não trava aqui: se a imagem do comprovante vier logo depois, ela tem prioridade (trava na task)."""
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 3, 'valor_pago': 0}
    cenario['decisao'] = {'acao': 'pagamento_informado', 'texto': None, 'valor': 20.0}
    fluxo_responder.executar({**PEDIDO_WEBHOOK, 'estado_id': 3}, _webhook('já fiz o pix de 20'))
    assert cenario['travas'] == []
    [(nome, args, _)] = cenario['agendadas']
    assert nome == 'tasks.confirmar_pagamento_informado'
    assert args[1] == 'wamid.C' and args[2] == 20.0


@pytest.mark.parametrize('em_analise', [False, True])
def test_fala_explicita_de_suicidio_responde_com_carinho_e_cvv_sem_chamar_a_ia(cenario, monkeypatch, em_analise):
    """Lista estrita do código decide (não a IA), antes de tudo, inclusive com o pedido em análise pelo admin."""
    monkeypatch.setattr(fluxo_responder, 'tem_notificacao_em_analise', lambda _p: em_analise)
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 4, 'valor_pago': 0}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('perdi a confiança da família porque tentei tira a minha vida'))
    assert cenario['ia_chamada'] == 0
    [(nome, args, _)] = cenario['agendadas']
    assert nome == 'tasks.enviar_resposta_cliente' and args[1] == agente.MENSAGEM_RISCO_VIDA_CVV
    assert '188' in args[1]
    assert cenario['notificacoes'] == [('risco_vida', True)]  # grava mesmo com outra notificação aberta


def test_fala_explicita_com_comprovante_em_analise_nao_espera(cenario):
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 13, 'valor_pago': 0}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('quero morrer'))
    [(nome, _args, _)] = cenario['agendadas']
    assert nome == 'tasks.enviar_resposta_cliente'


def test_cvv_sai_uma_vez_e_alerta_nao_duplica_enquanto_aberto(cenario, monkeypatch):
    """Cada resposta é uma mensagem cobrada e cada notificação polui a fila."""
    monkeypatch.setattr(fluxo_responder, 'tem_notificacao_em_analise', lambda _p: True)
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 0, 'valor_pago': 10}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('quero morrer'))
    cenario['alertas_abertos'].add((7, 'risco_vida'))   # o alerta criado acima continua aberto
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('vou me matar'))
    assert len(cenario['agendadas']) == 1 and len(cenario['notificacoes']) == 1
    assert len(cenario['salvas']) == 2


def test_alerta_resolvido_nova_fala_gera_novo_alerta_sem_repetir_o_cvv(cenario):
    """O humano resolveu o alerta; uma fala mais grave depois não pode passar despercebida."""
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 4, 'valor_pago': 0}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('quero morrer'))
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('tentei tirar a minha vida'))  # nenhum alerta aberto
    assert len(cenario['notificacoes']) == 2
    assert len(cenario['agendadas']) == 1   # o CVV não repete em 24 h


def test_falha_ao_agendar_libera_a_trava_do_cvv(cenario, monkeypatch):
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 4, 'valor_pago': 0}
    monkeypatch.setattr(fluxo_responder.celery_app, 'send_task',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('broker')))
    with pytest.raises(RuntimeError):
        fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('quero morrer'))
    assert 7 not in cenario['cvv_reservados']   # a próxima mensagem tenta de novo


def test_redis_fora_do_ar_envia_cvv(monkeypatch):
    """Sem Redis, repetir é melhor que não enviar (o alerta continua deduplicado pelo banco)."""
    import redis_cliente
    monkeypatch.setattr(redis_cliente, 'cliente', lambda: (_ for _ in ()).throw(RuntimeError('redis')))
    assert fluxo_responder._reservar_cvv(7) is True


def test_desabafo_escalado_pela_ia_nao_impede_o_cvv_depois(cenario, monkeypatch):
    """A IA escalou um desabafo (só carinho, notificação aberta); a fala explícita depois ainda recebe o CVV."""
    monkeypatch.setattr(fluxo_responder, 'tem_notificacao_em_analise', lambda _p: True)
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 4, 'valor_pago': 0}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('penso em me matar'))
    [(_nome, args, _)] = cenario['agendadas']
    assert args[1] == agente.MENSAGEM_RISCO_VIDA_CVV


def test_desabafo_de_saude_com_pedido_em_analise_continua_silenciado(cenario, monkeypatch):
    """Sem palavras explícitas e com humano já atendendo: não responde (nem CVV, nem IA)."""
    monkeypatch.setattr(fluxo_responder, 'tem_notificacao_em_analise', lambda _p: True)
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 4, 'valor_pago': 0}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('Hoje a pressão está alta e a diabetes também'))
    assert cenario['agendadas'] == [] and cenario['ia_chamada'] == 0


def test_pedido_em_analise_sem_risco_continua_silenciado(cenario, monkeypatch):
    monkeypatch.setattr(fluxo_responder, 'tem_notificacao_em_analise', lambda _p: True)
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 0, 'valor_pago': 10}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('cadê meu dinheiro'))
    assert cenario['agendadas'] == [] and cenario['ia_chamada'] == 0


def test_risco_vida_escala_e_responde_com_carinho(cenario):
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 3, 'valor_pago': 0}
    cenario['decisao'] = {'acao': 'risco_vida', 'texto': 'Querida, estou aqui com você 💛', 'valor': None}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('não aguento mais, quero sumir'))
    [(nome, args, _)] = cenario['agendadas']
    assert nome == 'tasks.enviar_resposta_cliente'
    assert args[1] == 'Querida, estou aqui com você 💛'


@pytest.mark.parametrize('acao', ['escalar', 'silenciar'])
def test_escalar_e_silenciar_nao_enviam(cenario, acao):
    cenario['pedido_banco'] = {'id': 7, 'estado_id': 3, 'valor_pago': 0}
    cenario['decisao'] = {'acao': acao, 'texto': None, 'valor': None}
    fluxo_responder.executar(PEDIDO_WEBHOOK, _webhook('quero meu dinheiro de volta'))
    assert cenario['agendadas'] == []


# ─── agente: prompt, histórico e ferramentas ─────────────────────────────────

PAGO = {'id': 7, 'estado_id': 0, 'valor_pago': 10, 'data_pagamento': datetime(2026, 11, 16, 14, 2)}
NAO_PAGO = {'id': 7, 'estado_id': 3, 'valor_pago': 0}


def test_prompt_de_pedido_pago_diz_que_pagou_e_vem_depois_do_faq():
    prompt = agente.montar_system_prompt('PROMPT', 'FAQ: exigir nome do pagador', '', PAGO)
    assert 'JÁ PAGOU' in prompt and '16/11 às 14:02' in prompt and 'R$ 10,00' in prompt
    assert prompt.index('JÁ PAGOU') > prompt.index('FAQ: exigir')
    assert 'NUNCA peça comprovante' in prompt


def test_prompt_de_pedido_nao_pago_orienta_pagamento_informado():
    prompt = agente.montar_system_prompt('PROMPT', '', '', NAO_PAGO)
    assert 'ainda não pagou' in prompt and 'registrar_pagamento_informado' in prompt


def test_web_pago_conta_como_pago():
    assert agente.pedido_esta_pago({'estado_id': 1000, 'valor_pago': None}) is True


def test_historico_traduz_comprovante_e_arquivo():
    historico = [
        {'role': 'user', 'content': 'Comprovante recebido: imagem_comprovante'},
        {'role': 'assistant', 'content': '[arquivo] None'},
        {'role': 'user', 'content': 'Segue'},
    ]
    legivel = agente._historico_legivel(historico)
    assert legivel[0]['content'] == '(Registro: a cliente enviou o comprovante de pagamento.)'
    assert legivel[1]['content'] == '(Registro: enviamos à cliente um arquivo PDF.)'
    assert legivel[2]['content'] == 'Segue'
    assert historico[0]['content'].startswith('Comprovante recebido')  # não altera a lista original


def _resposta_openai(nome_tool=None, args='{}', texto=None):
    if nome_tool:
        call = SimpleNamespace(function=SimpleNamespace(name=nome_tool, arguments=args))
        msg = SimpleNamespace(tool_calls=[call], content=None)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls', message=msg)])
    msg = SimpleNamespace(tool_calls=None, content=texto)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=msg)])


@pytest.fixture
def openai_falso(monkeypatch):
    chamadas, notificacoes = [], []
    resposta = {'r': None}

    def create(**kw):
        chamadas.append(kw)
        return resposta['r']
    monkeypatch.setattr(agente.client.chat.completions, 'create', create)
    monkeypatch.setattr(agente, '_notificar_se_necessario', lambda *a, **k: notificacoes.append(a))
    return chamadas, notificacoes, resposta


def _nomes_tools(chamada):
    return [t['function']['name'] for t in chamada['tools']]


def test_ferramenta_de_pagamento_so_para_pedido_do_whatsapp_aguardando_pagamento(openai_falso):
    chamadas, _, resposta = openai_falso
    resposta['r'] = _resposta_openai(texto='oi')
    web_contribuicao = {'id': 7, 'estado_id': 1008, 'valor_pago': 0, 'fluxo_inicial': 'web'}
    for pedido in (PAGO, NAO_PAGO, web_contribuicao):
        agente.responder_cliente_com_historico_produto('oi', [], {'prompt_vendas': 'x'}, pedido)
    assert 'registrar_pagamento_informado' not in _nomes_tools(chamadas[0])
    assert 'registrar_pagamento_informado' in _nomes_tools(chamadas[1])
    assert 'registrar_pagamento_informado' not in _nomes_tools(chamadas[2])
    assert 'nao_responder' in _nomes_tools(chamadas[0])
    assert chamadas[0]['parallel_tool_calls'] is False


def test_varias_ferramentas_a_mais_grave_vence(openai_falso):
    """Se o modelo devolver [nao_responder, risco_vida], o risco não pode ser descartado."""
    _, notificacoes, resposta = openai_falso
    calls = [SimpleNamespace(function=SimpleNamespace(name='nao_responder', arguments='{}')),
             SimpleNamespace(function=SimpleNamespace(name='notificar_admin',
                                                      arguments='{"motivo": "risco_vida", "resumo": "x"}'))]
    msg = SimpleNamespace(tool_calls=calls, content=None)
    resposta['r'] = SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls', message=msg)])
    d = agente.responder_cliente_com_historico_produto('...', [], {'prompt_vendas': 'x'}, PAGO)
    assert d['acao'] == 'risco_vida' and notificacoes


def test_tool_pagamento_informado_devolve_valor(openai_falso):
    _, notificacoes, resposta = openai_falso
    resposta['r'] = _resposta_openai('registrar_pagamento_informado', '{"valor": 20}')
    d = agente.responder_cliente_com_historico_produto('fiz o pix de 20', [], {'prompt_vendas': 'x'}, NAO_PAGO)
    assert d == {'acao': 'pagamento_informado', 'texto': None, 'valor': 20.0}
    assert notificacoes == []


def test_tool_nao_responder_silencia(openai_falso):
    _, _, resposta = openai_falso
    resposta['r'] = _resposta_openai('nao_responder')
    d = agente.responder_cliente_com_historico_produto('Coloquei 30', [], {'prompt_vendas': 'x'}, PAGO)
    assert d['acao'] == 'silenciar'


def test_tool_risco_vida_notifica_e_usa_o_carinho_escrito_pela_ia(openai_falso):
    """Desde nov/2026: resposta carinhosa no tom da persona e escala; CVV/SAMU é decisão humana."""
    _, notificacoes, resposta = openai_falso
    resposta['r'] = _resposta_openai('notificar_admin',
                                     '{"motivo": "risco_vida", "resumo": "x", "resposta": "Querida, estou aqui 💛"}')
    d = agente.responder_cliente_com_historico_produto('...', [], {'prompt_vendas': 'x'}, NAO_PAGO)
    assert d == {'acao': 'risco_vida', 'texto': 'Querida, estou aqui 💛', 'valor': None}
    assert notificacoes and notificacoes[0][2] == 'risco_vida'


def test_tool_risco_vida_sem_texto_da_ia_usa_mensagem_fixa_sem_cvv(openai_falso):
    _, notificacoes, resposta = openai_falso
    resposta['r'] = _resposta_openai('notificar_admin', '{"motivo": "risco_vida", "resumo": "x"}')
    d = agente.responder_cliente_com_historico_produto('...', [], {'prompt_vendas': 'x'}, NAO_PAGO)
    assert d['acao'] == 'risco_vida' and d['texto'] == agente.MENSAGEM_RISCO_VIDA
    assert '188' not in d['texto'] and '192' not in d['texto']
    assert notificacoes and notificacoes[0][2] == 'risco_vida'


def test_tool_estorno_escala_sem_texto(openai_falso):
    _, notificacoes, resposta = openai_falso
    resposta['r'] = _resposta_openai('notificar_admin', '{"motivo": "estorno", "resumo": "x"}')
    d = agente.responder_cliente_com_historico_produto('quero estorno', [], {'prompt_vendas': 'x'}, PAGO)
    assert d == {'acao': 'escalar', 'texto': None, 'valor': None}
    assert len(notificacoes) == 1


def test_historico_traduz_botao_sem_o_formato_tecnico():
    """A IA chegou a responder copiando "[botão] Receitas da Lu → https://..." do histórico."""
    [msg] = agente._historico_legivel([{'role': 'assistant', 'content': '[botão] Receitas da Lu → https://x/pedido2/a'}])
    assert msg['content'] == '(Registro: enviamos à cliente um botão "Receitas da Lu" que abre o link https://x/pedido2/a.)'
    assert '[' not in msg['content']


def test_historico_traduz_audio_e_imagem_e_nao_mexe_em_resposta_da_ia_com_colchete():
    legivel = agente._historico_legivel([
        {'role': 'assistant', 'content': '[áudio enviado]'},
        {'role': 'assistant', 'content': '[imagem enviada]'},
        {'role': 'assistant', 'content': '[Dica] use forma de 20cm'},
    ])
    assert [m['content'] for m in legivel] == [
        '(Registro: enviamos à cliente um áudio.)',
        '(Registro: enviamos à cliente uma imagem.)',
        '[Dica] use forma de 20cm',
    ]


def test_estado_0_conta_como_pago_mesmo_com_valor_zerado():
    """Há pedidos no 0 com valor_pago 0 (comprovante antigo, produto sem preço): para a IA, estão pagos."""
    assert agente.pedido_esta_pago({'estado_id': 0, 'valor_pago': 0}) is True
    assert 'JÁ PAGOU' in agente.montar_system_prompt('P', '', '', {'estado_id': 0, 'valor_pago': 0})


def test_prompt_com_comprovante_em_analise_nao_diz_que_nao_pagou():
    """Se a espera do responder acabar com o pedido ainda no 13, a IA não pode tratar a cliente como devedora."""
    prompt = agente.montar_system_prompt('P', '', '', {'id': 7, 'estado_id': 13, 'valor_pago': 0})
    assert 'sendo conferido' in prompt and 'ainda não pagou' not in prompt


def test_ferramenta_desconhecida_silencia_sem_escalar(openai_falso):
    """Escalar silencia a IA no pedido até um humano agir: ferramenta inesperada não pode fazer isso."""
    _, notificacoes, resposta = openai_falso
    resposta['r'] = _resposta_openai('ferramenta_inventada', '{}')
    d = agente.responder_cliente_com_historico_produto('oi', [], {'prompt_vendas': 'x'}, NAO_PAGO)
    assert d['acao'] == 'silenciar' and notificacoes == []


@pytest.mark.parametrize('texto', [
    'Querida, que Deus te dê forças 💛 estou aqui torcendo por você.',
    'Não deixe a esperança se apagar, querida 💛',   # "apagar" não é "pagar"
])
def test_carinho_da_ia_valido_passa(texto):
    assert agente._carinho_valido(texto) == texto


@pytest.mark.parametrize('texto', [
    'Ligue 188 se precisar', 'Nossa equipe vai falar com você', 'Quando puder, faça o Pix', 'x' * 401, '', None,
    'Fica tranquila, alguém daqui vai conversar com você logo', 'Vamos entrar em contato com você',
])
def test_carinho_da_ia_com_o_que_a_ferramenta_proibe_vira_a_mensagem_fixa(texto):
    assert agente._carinho_valido(texto) is None


def test_campo_resposta_so_na_ferramenta_do_whatsapp():
    """O agente de e-mail usa _TOOL_NOTIFICAR_ADMIN e não envia texto ao escalar."""
    props_email = agente._TOOL_NOTIFICAR_ADMIN['function']['parameters']['properties']
    props_wpp = agente._TOOL_NOTIFICAR_ADMIN_WHATSAPP['function']['parameters']['properties']
    assert 'resposta' not in props_email and 'resposta' in props_wpp
