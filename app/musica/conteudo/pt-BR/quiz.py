"""Quiz da Música em português do Brasil (/musica): perguntas, opções e o que aparece para cada resposta. Para
mudar texto, ordem ou opções, edite só aqui. As regras que usam estes dados ficam em musica/dominio/quiz.py (o
motor, igual para todos os idiomas).

Os VALORES (ex.: "Mãe", "Dia das Mães") são gravados nas respostas e vão para a IA da letra: mudar um valor
muda o que as músicas antigas mostram no admin. Os 8 primeiros valores de OCASIOES são os das páginas de ocasião
da landing (textos.json: landing.paginas.*.quiz).

Tipos de tela: "opcoes" (botões), "pessoas" (nome, apelido e pronúncia de 1 a 4 pessoas), "lembrancas" (3 perguntas
guiadas), "texto" (uma linha), "contato" (seu nome, e-mail e WhatsApp opcional).
O campo "chave" é o nome que vai para a IA da letra.

As opções dependem das respostas anteriores (para não aparecer "amigo + Dia das Mães" ou "samba + dupla sertaneja"):
cada relação tem marcadores (RELACOES) e cada ocasião/tom diz para quais marcadores aparece ("para") e quando não
aparece ("exceto"). As vozes dependem do estilo (VOZES_POR_ESTILO).

Marcas nos textos, trocadas na tela pelas respostas anteriores (quiz.html, personalizar; gramática em textos.json):
    {nome}          apelido (ou nome) de quem recebe; em grupo, "Ana, Bia e Carla". Ex.: "Dona Lena"
    {da_sua_pessoa} "da sua mãe", "do seu pai"... ou "de quem vai receber"
    {ela} {dela}    "ela/dela", "ele/dele", "eles/deles" (grupo) ou "essa pessoa/dessa pessoa"
    {de}            o nome de quem dá o presente
Telas com "titulo_grupo" / "titulo_eu" usam esse texto em "Mais de uma pessoa" / "Para mim".
"""

MAIS_DE_UMA = 'Mais de uma pessoa'
PARA_MIM = 'Para mim'
OUTRA_PESSOA = 'Outra pessoa'   # relação sem marcador próprio (filtro padrão)
OUTRA_OCASIAO = 'Outra ocasião'   # abre o campo "Qual?"
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

# Ordem = os mais escolhidos primeiro (produção, até 25/10/2026). A família sertaneja virou um "Sertanejo" só
# (26/10/2026): o som de hoje, de sofrência e de dupla.
ESTILOS = [
    ['sertanejo', 'Sertanejo'], ['rock', 'Rock'], ['gospel', 'Gospel'], ['mpb', 'MPB'], ['pagode', 'Pagode'],
    ['rap', 'Rap / Hip-hop'], ['infantil', 'Infantil'], ['romantica', 'Balada romântica'], ['forro', 'Forró'],
    ['pop', 'Pop'], ['samba', 'Samba'], ['axe', 'Axé'], ['funk', 'Funk'], ['reggae', 'Reggae'],
    ['bossa', 'Bossa nova'], ['valsa', 'Valsa'],
]
# Estilos que saíram do quiz → o que os substitui (rascunhos abertos, "outra versão" de músicas antigas).
ESTILOS_ANTIGOS = {'sertanejo_universitario': 'sertanejo', 'sertanejo_raiz': 'sertanejo', 'arrocha': 'sertanejo',
                   'piseiro': 'forro'}

VOZES = {'feminina': 'Voz feminina', 'masculina': 'Voz masculina', 'dupla': 'Dupla sertaneja',
         'coral': 'Voz feminina com coral'}
VOZES_PADRAO = ['feminina', 'masculina']
VOZES_POR_ESTILO = {
    'sertanejo': ['feminina', 'masculina', 'dupla'],
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
