"""Regras do produto Música que não dependem de nada externo (testáveis isoladas)."""
import re
from datetime import datetime, timedelta

from musica.dominio.modelos import PedidoGeracao
from musica.dominio.quiz import MAIS_DE_UMA, PARA_MIM, RELACOES, estilo_atual, rotulo, vozes_para


def montar_geracao(respostas: dict, titulo: str, letra_suno: str, tabela_estilos: dict) -> PedidoGeracao:
    """Junta estilo + clima + voz (conteudo/estilos.json) no pedido para o gerador. O gênero vem primeiro (é o que
    mais pesa no Suno); o clima só descreve o sentimento. A voz precisa combinar com o estilo (quiz.VOZES_POR_ESTILO):
    uma resposta incoerente (ex.: dupla num samba, de antes dessa regra) vira a primeira voz permitida."""
    estilo = respostas.get('estilo') if respostas.get('estilo') in tabela_estilos['estilos'] else 'pop'
    permitidas = vozes_para(estilo)
    chave_voz = respostas.get('voz') if respostas.get('voz') in permitidas else permitidas[0]
    voz = tabela_estilos['voz'].get(chave_voz, tabela_estilos['voz']['feminina'])
    texto_voz = tabela_estilos.get('voz_estilo', {}).get(estilo, {}).get(chave_voz) or voz['texto']
    partes = [
        tabela_estilos['estilos'][estilo],
        tabela_estilos['clima'].get(respostas.get('clima'), tabela_estilos['clima']['emocionante']),
        texto_voz,
    ]
    negativo = ', '.join(n for n in (tabela_estilos['negativo'],
                                     tabela_estilos.get('negativo_estilo', {}).get(estilo, '')) if n)
    return PedidoGeracao(titulo=titulo or 'Música de presente', letra=letra_suno, estilo=', '.join(partes),
                         genero_vocal=voz['genero_vocal'], negativo=negativo)


def juntar_nomes(nomes: list[str]) -> str:
    """['Ana', 'Bia', 'Carla'] → 'Ana, Bia e Carla'."""
    nomes = [n for n in nomes if n]
    return nomes[0] if len(nomes) == 1 else (', '.join(nomes[:-1]) + ' e ' + nomes[-1] if nomes else '')


def montar_respostas(bruto: dict, chaves_validas: set, max_pessoas: int) -> dict:
    """Respostas do quiz como a IA e o resto do sistema esperam, a partir do que o navegador mandou:
    `pessoas` (1 a max_pessoas, cada uma com nome/apelido/pronuncia) vira nome, apelido e pronuncia juntos
    ("Ana, Bia e Carla"), e a lista fica para a IA tratar o plural; `lembrancas_partes` (pergunta guiada + resposta)
    vira o texto de `lembrancas`. "Para mim": quem dá o presente é a própria pessoa."""
    respostas = {k: str(v).strip()[:1500] for k, v in bruto.items() if k in chaves_validas and isinstance(v, (str, int))}
    pessoas = []
    lista_pessoas = bruto.get('pessoas') if isinstance(bruto.get('pessoas'), list) else []
    for p in lista_pessoas[:max_pessoas]:
        if isinstance(p, dict) and str(p.get('nome') or '').strip():
            pessoas.append({k: str(p.get(k) or '').strip()[:80] for k in ('nome', 'apelido', 'pronuncia')})
    if pessoas:
        respostas['nome'] = juntar_nomes([p['nome'] for p in pessoas])
        if any(p['apelido'] for p in pessoas):
            respostas['apelido'] = juntar_nomes([p['apelido'] or p['nome'] for p in pessoas])
        if any(p['pronuncia'] for p in pessoas):
            respostas['pronuncia'] = '; '.join(f"{p['nome']} se fala {p['pronuncia']}" for p in pessoas if p['pronuncia'])
        if len(pessoas) > 1:
            respostas['pessoas'] = pessoas
    lista_partes = bruto.get('lembrancas_partes') if isinstance(bruto.get('lembrancas_partes'), list) else []
    partes = [p for p in lista_partes[:3] if isinstance(p, dict)]
    textos = [f"{str(p.get('pergunta') or '').strip()[:150]}: {str(p.get('resposta') or '').strip()[:1200]}"
              for p in partes if str(p.get('resposta') or '').strip()]
    if textos:
        respostas['lembrancas'] = '\n'.join(textos)
    if respostas.get('para_quem') == PARA_MIM and not respostas.get('de'):
        respostas['de'] = respostas.get('nome', '')
    return respostas_atuais(respostas)


def respostas_atuais(respostas: dict) -> dict:
    """Respostas com valores que saíram do quiz trocados pelos de hoje (ex.: estilo "arrocha" → "sertanejo"). Roda
    na criação (montar_respostas) e na leitura do banco (repositório): letra, música e admin veem o mesmo estilo."""
    if isinstance(respostas, dict) and respostas.get('estilo'):
        respostas['estilo'] = estilo_atual(respostas['estilo'])
    return respostas


def para_quem(respostas: dict) -> str:
    """Como chamar quem recebe: o apelido, se tiver; senão o nome (em grupo, os nomes juntos: "Ana, Bia e Carla")."""
    return (respostas or {}).get('apelido') or (respostas or {}).get('nome') or 'quem você ama'


def para_leitura(letra_texto: str) -> str:
    """Tira as marcações do Suno ([Verse 1], [Chorus]...) para a cliente ler; o refrão vira a linha '(Refrão)'."""
    linhas = []
    for linha in (letra_texto or '').splitlines():
        marcacao = re.fullmatch(r'\s*\[([^\]]+)\]\s*', linha)
        if not marcacao:
            linhas.append(linha)
        elif 'chorus' in marcacao.group(1).lower() and 'pre' not in marcacao.group(1).lower():
            linhas.append('(Refrão)')
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(linhas)).strip()


def inicio_previa(duracao_total: float | None, segundos: int) -> float:
    """A prévia começa perto do primeiro refrão (35 s); em música curta, termina no fim."""
    duracao_total = duracao_total or 0
    return 35 if duracao_total >= 35 + segundos else max(0, duracao_total - segundos)


def travou(gerando_desde: datetime | None, agora: datetime, minutos: int) -> bool:
    return bool(gerando_desde) and agora - gerando_desde > timedelta(minutes=minutos)


def validar_presente(nome: str, email: str, quando: datetime | None, agora: datetime,
                     whatsapp: str = '') -> str | None:
    """Erro (texto para a cliente) da entrega para quem recebe (e-mail e/ou WhatsApp), ou None.
    `quando` None = enviar agora. `whatsapp` já normalizado por telefone_whatsapp ('' = não informado ou inválido)."""
    if not nome:
        return 'Coloque o nome de quem vai receber.'
    if not email and not whatsapp:
        return 'Coloque o e-mail ou o WhatsApp (com DDD) de quem vai receber.'
    if email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        return 'Confira o e-mail de quem vai receber.'
    if quando and (quando < agora - timedelta(minutes=5) or quando > agora + timedelta(days=90)):
        return 'Escolha um horário a partir de agora, em até 90 dias.'
    return None


def telefone_whatsapp(texto, ddi: str = '55') -> str:
    """REGRA ÚNICA do número de WhatsApp (quiz, checkout, presente, envio): só dígitos, com o DDI, como a Meta pede.
    '' = não serve para WhatsApp. Brasil: celular com DDD e o 9 (fixo e número sem o 9 não têm WhatsApp); aceita o
    número com +55 ou com o 0 da operadora ("(061) 9..."). Outro DDI (seletor do checkout): entra o número dele. Um
    número já gravado com DDI de fora (12 a 15 dígitos, sem o 55) passa igual."""
    digitos = re.sub(r'\D', '', str(texto or ''))
    ddi = re.sub(r'\D', '', str(ddi or '')) or '55'
    if ddi != '55':
        if digitos and not digitos.startswith(ddi):
            digitos = ddi + digitos
        return digitos if len(ddi) + 6 <= len(digitos) <= 15 else ''
    digitos = digitos.lstrip('0')   # 0 da operadora / 00 internacional
    if len(digitos) in (12, 13) and digitos.startswith('55'):
        digitos = digitos[2:]
    elif 12 <= len(digitos) <= 15:
        return digitos   # já com o DDI de outro país
    return '55' + digitos if len(digitos) == 11 and digitos[2] == '9' else ''


def primeiro_nome(*nomes: str) -> str:
    """O primeiro nome que pareça nome (sem @ nem dígitos), com inicial maiúscula; '' se nenhum servir."""
    for nome in nomes:
        palavra = (nome or '').strip().split(' ')[0]
        if palavra and '@' not in palavra and not any(c.isdigit() for c in palavra):
            return palavra.capitalize()
    return ''


def celular_br(texto) -> str:
    """Só o celular brasileiro de telefone_whatsapp ('55' + DDD + 9 + 8 dígitos): o quiz não tem seletor de país e o
    campo do checkout abre com o +55. '' para fixo, número de fora ou inválido."""
    numero = telefone_whatsapp(texto)
    return numero if len(numero) == 13 and numero.startswith('55') else ''


def mesmo_telefone(a: str, b: str) -> bool:
    """Mesmo celular? A Meta às vezes devolve o número sem o 9 da frente (55 61 8269-6770 x 55 61 98269-6770):
    compara DDI+DDD e os 8 últimos dígitos."""
    a, b = re.sub(r'\D', '', a or ''), re.sub(r'\D', '', b or '')
    return len(a) >= 12 and len(b) >= 12 and a[:4] == b[:4] and a[-8:] == b[-8:]


def para_quem_com_relacao(respostas: dict) -> str:
    """{{2}} do template musica_pronta ("a música para ___ ficou pronta"): "sua mãe Helena", "seu amigo Celo",
    "Ana, Bia e Carla" (grupo), "você" (Para mim), só o nome (Outra pessoa)."""
    respostas = respostas or {}
    relacao, nome = respostas.get('para_quem') or '', para_quem(respostas)
    if relacao == PARA_MIM:
        return 'você'
    if relacao == MAIS_DE_UMA:
        return nome
    genero = next((r['genero'] for r in RELACOES if r['valor'] == relacao), 'x')
    if genero == 'f':
        return f'sua {rotulo(relacao)} {nome}'
    if genero == 'm':
        return f'seu {rotulo(relacao)} {nome}'
    return nome


# ------------------------------------------------------------------ lembretes (docs/MUSICA.md "Lembretes")

def etapa_lembrete(musica: dict) -> str | None:
    """Em que etapa do funil a música parou, para os lembretes: 'checkout' (abriu o checkout ou tem pedido esperando
    pagamento — `em_checkout`, calculado pelo repositório), 'previa', 'letra' ou None (paga, gerando, sem e-mail ou
    ela pediu para não receber)."""
    if musica.get('liberada_em') or musica.get('sem_lembretes') or not musica.get('email'):
        return None
    if musica.get('em_checkout'):
        return 'checkout'
    return {'previa_pronta': 'previa', 'letra_pronta': 'letra'}.get(musica.get('status'))


ORDEM_ETAPAS = {'letra': 0, 'previa': 1, 'checkout': 2}


def proximo_lembrete(etapa: str, musica: dict, agora: datetime, minutos: tuple, janela: tuple, dias: int):
    """O que fazer agora: ('zerar', 0) quando a música entrou numa etapa nova (o relógio começa agora);
    ('enviar', n) com n = o lembrete mais recente já vencido (1, 2 ou 3 — se dois venceram fora do horário, sai só o
    último, nunca dois seguidos); (None, 0) para esperar. A mesma etapa de novo ("outra versão" volta para a prévia)
    não zera, e voltar para uma etapa anterior (ex.: o PIX venceu) também não: a série dela já saiu (no máximo 3 por
    etapa, 9 no total)."""
    salva = musica.get('lembrete_etapa')
    if salva in ORDEM_ETAPAS and ORDEM_ETAPAS[etapa] < ORDEM_ETAPAS[salva]:
        return None, 0
    if etapa != salva or not musica.get('lembrete_desde'):
        return 'zerar', 0
    passou = agora - musica['lembrete_desde']
    enviados = musica.get('lembretes_enviados') or 0
    if enviados >= len(minutos) or passou > timedelta(days=dias) or not janela[0] <= agora.hour < janela[1]:
        return None, 0
    vencidos = sum(1 for m in minutos if passou >= timedelta(minutes=m))
    return ('enviar', vencidos) if vencidos > enviados else (None, 0)
