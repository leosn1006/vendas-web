"""Perguntas do quiz e quais opções aparecem para cada resposta. Para mudar texto, ordem ou opções, edite só aqui.

Tipos de tela: "opcoes" (botões), "pessoas" (nome, apelido e pronúncia de 1 a 4 pessoas), "lembrancas" (3 perguntas
guiadas), "texto" (uma linha), "contato" (seu nome, e-mail e WhatsApp opcional).
O campo "chave" é o nome que vai para a IA da letra.

As opções dependem das respostas anteriores (para não aparecer "amigo + Dia das Mães" ou "samba + dupla sertaneja"):
cada relação tem marcadores (RELACOES) e cada ocasião/tom diz para quais marcadores aparece ("para") e quando não
aparece ("exceto"). As vozes dependem do estilo (VOZES_POR_ESTILO).

Marcas nos textos, trocadas na tela pelas respostas anteriores (quiz.html, personalizar):
    {nome}          apelido (ou nome) de quem recebe; em grupo, "Ana, Bia e Carla". Ex.: "Dona Lena"
    {da_sua_pessoa} "da sua mãe", "do seu pai"... ou "de quem vai receber"
    {ela} {dela}    "ela/dela", "ele/dele", "eles/deles" (grupo) ou "essa pessoa/dessa pessoa"
    {de}            o nome de quem dá o presente
Telas com "titulo_grupo" / "titulo_eu" usam esse texto em "Mais de uma pessoa" / "Para mim".
"""

MAIS_DE_UMA = 'Mais de uma pessoa'
PARA_MIM = 'Para mim'
MAX_PESSOAS = 4
TODOS = '*'

# Relação → gênero (f/m/g = grupo/x = indefinido) e marcadores usados para filtrar ocasiões e tons.
# "rotulo": como a relação entra em "da sua ___" / "sua ___ Ju" (padrão: o valor em minúsculas).
RELACOES = [
    {'valor': 'Mãe', 'genero': 'f', 'marcas': ['mae', 'familia']},
    {'valor': 'Pai', 'genero': 'm', 'marcas': ['pai', 'familia']},
    {'valor': 'Esposa', 'genero': 'f', 'marcas': ['casal', 'mae']},
    {'valor': 'Marido', 'genero': 'm', 'marcas': ['casal', 'pai']},
    {'valor': 'Namorada', 'genero': 'f', 'marcas': ['casal', 'namoro']},
    {'valor': 'Namorado', 'genero': 'm', 'marcas': ['casal', 'namoro']},
    {'valor': 'Filha', 'genero': 'f', 'marcas': ['filhos', 'familia']},
    {'valor': 'Filho', 'genero': 'm', 'marcas': ['filhos', 'familia']},
    {'valor': 'Neta', 'genero': 'f', 'marcas': ['filhos', 'familia']},
    {'valor': 'Neto', 'genero': 'm', 'marcas': ['filhos', 'familia']},
    {'valor': 'Irmã', 'genero': 'f', 'marcas': ['irmaos', 'familia']},
    {'valor': 'Irmão', 'genero': 'm', 'marcas': ['irmaos', 'familia']},
    {'valor': 'Avó', 'genero': 'f', 'marcas': ['mae', 'avos', 'familia']},
    {'valor': 'Avô', 'genero': 'm', 'marcas': ['pai', 'avos', 'familia']},
    {'valor': 'Sogra', 'genero': 'f', 'marcas': ['mae', 'familia']},
    {'valor': 'Sogro', 'genero': 'm', 'marcas': ['pai', 'familia']},
    {'valor': 'Amiga', 'genero': 'f', 'marcas': ['amigos']},
    {'valor': 'Amigo', 'genero': 'm', 'marcas': ['amigos']},
    # Ex: reconquista ou fazer as pazes. Não é "casal": não vê bodas, casamento, chá revelação nem aposentadoria.
    {'valor': 'Minha ex', 'genero': 'f', 'marcas': ['ex'], 'rotulo': 'ex'},
    {'valor': 'Meu ex', 'genero': 'm', 'marcas': ['ex'], 'rotulo': 'ex'},
    {'valor': MAIS_DE_UMA, 'genero': 'g', 'marcas': ['grupo', 'familia', 'mae', 'pai', 'casal_pais']},
    {'valor': PARA_MIM, 'genero': 'x', 'marcas': ['eu']},
    {'valor': 'Outra pessoa', 'genero': 'x', 'marcas': ['outra']},
]

# Ocasiões: "para" = marcadores que veem a opção (TODOS = qualquer relação); "exceto" = marcadores que não veem.
# Os 8 primeiros valores são os das páginas de ocasião da landing (/musica/?ocasiao=...): não mudar o texto.
OCASIOES = [
    {'valor': 'Aniversário', 'para': TODOS},
    {'valor': 'Dia das Mães', 'para': ['mae']},
    {'valor': 'Dia dos Pais', 'para': ['pai']},
    {'valor': 'Dia dos Namorados', 'para': ['casal', 'ex']},
    {'valor': 'Casamento', 'para': TODOS, 'exceto': ['ex']},
    {'valor': 'Pedido de desculpas', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'Formatura', 'para': ['filhos', 'irmaos', 'amigos', 'casal', 'eu', 'grupo', 'outra']},
    {'valor': 'Só porque eu amo', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'Natal', 'para': TODOS},
    {'valor': 'Aniversário de casamento ou namoro', 'para': ['casal', 'casal_pais']},
    {'valor': 'Pedido de casamento', 'para': ['namoro']},
    {'valor': 'Agradecer de coração', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'Dar força e incentivar', 'para': TODOS},
    {'valor': 'Celebrar uma conquista', 'para': TODOS},
    {'valor': 'Matar a saudade', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'Homenagem a quem já partiu', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'Chá revelação', 'para': ['casal', 'filhos', 'grupo', 'eu', 'outra'], 'exceto': ['ex']},
    {'valor': 'Batizado', 'para': ['filhos', 'grupo', 'outra']},
    {'valor': 'Aposentadoria', 'para': ['mae', 'pai', 'casal', 'irmaos', 'amigos', 'eu', 'grupo', 'outra']},
    {'valor': 'Celebrar a minha história', 'para': ['eu']},
    {'valor': 'Outra ocasião', 'para': TODOS, 'texto': True},   # abre um campo "Qual?"
]

# Tons: o valor é a chave do "clima" em conteudo/estilos.json. "exceto_ocasioes": não aparece nessas ocasiões.
TONS = [
    {'valor': 'romantica', 'texto': 'Romântica 💕', 'para': ['casal', 'ex']},
    {'valor': 'emocionante', 'texto': 'Emocionante 🥹', 'para': TODOS},
    {'valor': 'animada', 'texto': 'Animada 🎉', 'para': TODOS, 'exceto_ocasioes': ['Homenagem a quem já partiu']},
    {'valor': 'inspiradora', 'texto': 'Inspiradora ✨', 'para': TODOS},
    {'valor': 'engracado', 'texto': 'Engraçada 😂', 'para': TODOS,
     'exceto_ocasioes': ['Homenagem a quem já partiu', 'Pedido de desculpas']},
    {'valor': 'reflexiva', 'texto': 'Reflexiva 🌅', 'para': TODOS},
]

ESTILOS = [
    ['sertanejo', 'Sertanejo romântico'], ['sertanejo_universitario', 'Sertanejo universitário'],
    ['sertanejo_raiz', 'Modão / Sertanejo raiz'], ['gospel', 'Gospel'], ['pagode', 'Pagode'], ['samba', 'Samba'],
    ['forro', 'Forró'], ['piseiro', 'Piseiro'], ['arrocha', 'Arrocha'], ['mpb', 'MPB'], ['pop', 'Pop'],
    ['romantica', 'Balada romântica'], ['bossa', 'Bossa nova'], ['rock', 'Rock'], ['axe', 'Axé'], ['funk', 'Funk'],
    ['reggae', 'Reggae'], ['rap', 'Rap / Hip-hop'], ['valsa', 'Valsa'], ['infantil', 'Infantil'],
]

VOZES = {'feminina': 'Voz feminina', 'masculina': 'Voz masculina', 'dupla': 'Dupla sertaneja',
         'coral': 'Voz feminina com coral'}
VOZES_PADRAO = ['feminina', 'masculina']
VOZES_POR_ESTILO = {
    'sertanejo': ['feminina', 'masculina', 'dupla'],
    'sertanejo_universitario': ['feminina', 'masculina', 'dupla'],
    'sertanejo_raiz': ['dupla', 'masculina', 'feminina'],
    'arrocha': ['feminina', 'masculina', 'dupla'],
    'gospel': ['feminina', 'masculina', 'coral'],
}

# Perguntas guiadas das lembranças, pelo marcador da relação (a primeira que bater; senão "padrao").
LEMBRANCAS = {
    'casal': [
        {'pergunta': 'Como vocês se conheceram ou um momento que marcou vocês', 'exemplo': 'Ex.: A gente se conheceu num baile em 1998 e dançamos a noite toda.'},
        {'pergunta': 'Um jeito ou mania {dela} que você ama', 'exemplo': 'Ex.: Canta alto no carro e erra todas as letras.'},
        {'pergunta': 'O que você quer que {ela} sinta ouvindo a música', 'exemplo': 'Ex.: Que depois de 25 anos eu escolheria tudo de novo.'},
    ],
    'ex': [
        {'pergunta': 'Um momento de vocês que você nunca esqueceu', 'exemplo': 'Ex.: A viagem pra praia em que choveu os três dias e a gente riu de tudo.'},
        {'pergunta': 'Um jeito {dela} de que você sente falta', 'exemplo': 'Ex.: O jeito que cantava alto no carro, errando a letra.'},
        {'pergunta': 'O que você quer que {ela} saiba hoje', 'exemplo': 'Ex.: Que eu errei, aprendi, e que ainda penso em você.'},
    ],
    'grupo': [
        {'pergunta': 'Uma lembrança de vocês', 'exemplo': 'Ex.: As férias na casa da vó, todo mundo dormindo na sala.'},
        {'pergunta': 'O jeito de cada pessoa (pode ser uma palavra para cada)', 'exemplo': 'Ex.: Ana é a brincalhona, Bia a conselheira, Carla a que cuida de todo mundo.'},
        {'pergunta': 'O que você quer dizer com essa música', 'exemplo': 'Ex.: Que mesmo longe a gente é uma só.'},
    ],
    'eu': [
        {'pergunta': 'Um momento que marcou a sua vida', 'exemplo': 'Ex.: Quando me mudei sozinha para São Paulo com 18 anos.'},
        {'pergunta': 'Uma conquista ou superação sua', 'exemplo': 'Ex.: Me formei em enfermagem depois dos 40, trabalhando de dia e estudando à noite.'},
        {'pergunta': 'O que você quer celebrar agora', 'exemplo': 'Ex.: Que hoje eu me orgulho de quem eu me tornei.'},
    ],
    'padrao': [
        {'pergunta': 'Uma lembrança marcante com {ela}', 'exemplo': 'Ex.: Todo domingo fazia bolo de fubá para a família inteira.'},
        {'pergunta': 'Um jeito, mania ou frase {dela}', 'exemplo': 'Ex.: Canta hinos lavando a louça e sempre diz "Deus proverá".'},
        {'pergunta': 'O que você quer agradecer ou dizer', 'exemplo': 'Ex.: Obrigada por ter criado a gente sozinha, com tanto amor.'},
    ],
}
MIN_LETRAS_LEMBRANCAS = 40   # somando as 3 respostas

PERGUNTAS = [
    {
        'chave': 'para_quem', 'tipo': 'opcoes',
        'titulo': 'Pra quem é a música?',
        'opcoes': [r['valor'] for r in RELACOES],
    },
    {
        'chave': 'pessoas', 'tipo': 'pessoas',
        'titulo': 'Qual o nome {da_sua_pessoa}?',
        'titulo_grupo': 'Quais os nomes de quem vai receber?',
        'titulo_eu': 'Qual o seu nome?',
        'ajuda': 'Esse nome vai aparecer na letra da música.',
        'ajuda_grupo': f'Até {MAX_PESSOAS} pessoas. Todos os nomes vão aparecer na música.',
    },
    {
        'chave': 'ocasiao', 'tipo': 'opcoes',
        'titulo': 'Qual é a ocasião da música de {nome}?',
        'titulo_eu': 'Qual é a ocasião da sua música?',
        'opcoes': [o['valor'] for o in OCASIOES],
    },
    {
        'chave': 'lembrancas', 'tipo': 'lembrancas',
        'titulo': 'Agora a parte mais importante 💛',
        'ajuda': 'Conte a história de {nome}. Quanto mais detalhes, mais a música vai parecer com vocês.',
        'ajuda_eu': 'Conte a sua história. Quanto mais detalhes, mais a música vai parecer com você.',
    },
    {
        'chave': 'frase_obrigatoria', 'tipo': 'texto',
        'titulo': 'Tem alguma frase que não pode faltar na música de {nome}?',
        'titulo_eu': 'Tem alguma frase que não pode faltar na sua música?',
        'exemplo': 'Ex.: Deus é fiel (pode deixar em branco)',
    },
    {
        'chave': 'clima', 'tipo': 'opcoes',
        'titulo': 'Qual o tom da música?',
        'ajuda': 'O sentimento que a música vai passar.',
        'opcoes': [[t['valor'], t['texto']] for t in TONS],
    },
    {
        'chave': 'estilo', 'tipo': 'opcoes',
        'titulo': 'Qual estilo {nome} mais gosta?',
        'titulo_eu': 'Qual estilo você mais gosta?',
        'opcoes': ESTILOS,
    },
    {
        'chave': 'voz', 'tipo': 'opcoes',
        'titulo': 'Quem vai cantar?',
        'opcoes': [[k, v] for k, v in VOZES.items()],
    },
    {
        'chave': 'contato', 'tipo': 'contato',
        'titulo': 'Para onde mandamos a sua música?',
        'ajuda': 'Avisamos assim que ela ficar pronta.',
    },
]

# Chaves aceitas nas respostas (o resto que vier do navegador é ignorado).
CHAVES_VALIDAS = {'para_quem', 'nome', 'apelido', 'pronuncia', 'ocasiao', 'ocasiao_outra', 'lembrancas',
                  'frase_obrigatoria', 'clima', 'estilo', 'voz', 'de'}

# Para trocar {da_sua_pessoa}, {ela} e {dela} (o gênero está em RELACOES).
FEMININO = {r['valor'] for r in RELACOES if r['genero'] == 'f'}
MASCULINO = {r['valor'] for r in RELACOES if r['genero'] == 'm'}


def rotulo(para_quem: str) -> str:
    """Como a relação entra no texto: "mãe" ("da sua mãe"), "ex" ("da sua ex", não "da sua minha ex")."""
    r = next((r for r in RELACOES if r['valor'] == para_quem), None)
    return (r.get('rotulo') or r['valor'].lower()) if r else ''


def marcas_da_relacao(para_quem: str) -> set:
    return next((set(r['marcas']) for r in RELACOES if r['valor'] == para_quem), {'outra'})


def ocasioes_para(para_quem: str) -> list[str]:
    marcas = marcas_da_relacao(para_quem)
    return [o['valor'] for o in OCASIOES
            if (o['para'] == TODOS or marcas & set(o['para'])) and not marcas & set(o.get('exceto', []))]


def relacoes_por_ocasiao() -> dict[str, list[str]]:
    """Ocasião → relações que a veem (os botões "Pra quem é a música?" da página de cada ocasião na landing)."""
    relacoes = [r['valor'] for r in RELACOES]
    return {o['valor']: [r for r in relacoes if o['valor'] in ocasioes_para(r)] for o in OCASIOES}


def tons_para(para_quem: str, ocasiao: str) -> list[str]:
    marcas = marcas_da_relacao(para_quem)
    return [t['valor'] for t in TONS
            if (t['para'] == TODOS or marcas & set(t['para'])) and ocasiao not in t.get('exceto_ocasioes', [])]


def vozes_para(estilo: str) -> list[str]:
    return VOZES_POR_ESTILO.get(estilo, VOZES_PADRAO)


def combinacao_invalida(respostas: dict) -> str | None:
    """O que não combina nas respostas (mesma regra que a tela usa), ou None. O navegador já filtra; isto é a
    conferência do servidor contra um envio feito à mão."""
    para_quem = respostas.get('para_quem')
    if para_quem not in {r['valor'] for r in RELACOES}:
        return 'para_quem'
    if respostas.get('ocasiao') not in ocasioes_para(para_quem):
        return 'ocasiao'
    if respostas.get('clima') not in tons_para(para_quem, respostas.get('ocasiao')):
        return 'clima'
    if respostas.get('estilo') not in {e for e, _ in ESTILOS}:
        return 'estilo'
    if respostas.get('voz') not in vozes_para(respostas.get('estilo')):
        return 'voz'
    return None


def config_do_navegador() -> dict:
    """O que o quiz.html precisa, com os filtros JÁ CALCULADOS aqui (fonte única: as funções acima): ocasiões por
    relação, tons por relação e ocasião, vozes por estilo, gênero e grupo das perguntas guiadas por relação."""
    relacoes = [r['valor'] for r in RELACOES]
    ocasioes = [o['valor'] for o in OCASIOES]

    def guia(relacao):
        marcas = marcas_da_relacao(relacao)
        return next((g for g in ('eu', 'grupo', 'casal', 'ex') if g in marcas), 'padrao')
    return {
        'genero': {r['valor']: r['genero'] for r in RELACOES},
        'rotulo': {r: rotulo(r) for r in relacoes},
        'ocasioes_por_relacao': {r: ocasioes_para(r) for r in relacoes},
        'tons_por_relacao': {r: {o: tons_para(r, o) for o in ocasioes} for r in relacoes},
        'vozes_por_estilo': {e: vozes_para(e) for e, _ in ESTILOS},
        'guia_lembrancas': {r: guia(r) for r in relacoes},
        'lembrancas': LEMBRANCAS, 'min_letras_lembrancas': MIN_LETRAS_LEMBRANCAS,
        'max_pessoas': MAX_PESSOAS, 'mais_de_uma': MAIS_DE_UMA, 'para_mim': PARA_MIM,
    }
