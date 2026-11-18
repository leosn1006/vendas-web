"""Quiz da Música no espanhol do México (/mx/cancion): perguntas, opções e o que aparece para cada resposta. Mesmo
formato do conteudo/pt-BR/quiz.py (leia lá o que cada campo faz); as regras ficam em musica/dominio/quiz.py.

Transcriação, não tradução (18/11/2026, aguardando a revisão de um mexicano): "tú", vocabulário do México (mamá,
carro, celular, lavar los trastes, "entre más"), ocasiões de lá (10 de mayo, XV años, Primera Comunión, Día del
Niño, 14 de febrero com amigos) e padrinhos, que no México pesam como família.

Os VALORES (ex.: "Mamá", "10 de mayo (Día de las Madres)") vão gravados nas respostas e para a IA da letra.
As chaves de tom, estilo e voz são as do conteudo/es-MX/estilos.json.

Marcas nos textos (gramática em textos.json, quiz.js.gramatica):
    {nome}          apelido (ou nome) de quem recebe; em grupo, "Ana, Bia y Carla"
    {da_sua_pessoa} "tu mamá", "tu papá"... ou "la persona que la va a recibir"
    {ela} {dela}    "ella/de ella", "él/de él", "cada persona/de cada persona", "esa persona/de esa persona"
    {de}            o nome de quem dá o presente
"""

MAIS_DE_UMA = 'Más de una persona'
PARA_MIM = 'Para mí'
OUTRA_PESSOA = 'Otra persona'   # relação sem marcador próprio (filtro padrão)
OUTRA_OCASIAO = 'Otra ocasión'   # abre o campo "¿Cuál?"
MAX_PESSOAS = 4
TODOS = '*'

# Relação → gênero (f/m/g = grupo/x = indefinido) e marcadores (os mesmos nomes do Brasil: filtram ocasiões e tons).
# "rotulo": como a relação entra em "tu ___" (padrão: o valor em minúsculas). Madrina/Padrino: novos, só do México.
RELACOES = [
    {'valor': 'Mamá', 'genero': 'f', 'marcas': ['mae', 'familia']},
    {'valor': 'Papá', 'genero': 'm', 'marcas': ['pai', 'familia']},
    {'valor': 'Esposa', 'genero': 'f', 'marcas': ['casal', 'mae']},
    {'valor': 'Esposo', 'genero': 'm', 'marcas': ['casal', 'pai']},
    {'valor': 'Novia', 'genero': 'f', 'marcas': ['casal', 'namoro']},
    {'valor': 'Novio', 'genero': 'm', 'marcas': ['casal', 'namoro']},
    {'valor': 'Hija', 'genero': 'f', 'marcas': ['filhos', 'familia']},
    {'valor': 'Hijo', 'genero': 'm', 'marcas': ['filhos', 'familia']},
    {'valor': 'Nieta', 'genero': 'f', 'marcas': ['filhos', 'familia']},
    {'valor': 'Nieto', 'genero': 'm', 'marcas': ['filhos', 'familia']},
    {'valor': 'Hermana', 'genero': 'f', 'marcas': ['irmaos', 'familia']},
    {'valor': 'Hermano', 'genero': 'm', 'marcas': ['irmaos', 'familia']},
    {'valor': 'Abuelita', 'genero': 'f', 'marcas': ['mae', 'avos', 'familia']},
    {'valor': 'Abuelito', 'genero': 'm', 'marcas': ['pai', 'avos', 'familia']},
    {'valor': 'Suegra', 'genero': 'f', 'marcas': ['mae', 'familia']},
    {'valor': 'Suegro', 'genero': 'm', 'marcas': ['pai', 'familia']},
    {'valor': 'Madrina', 'genero': 'f', 'marcas': ['padrinos', 'familia']},
    {'valor': 'Padrino', 'genero': 'm', 'marcas': ['padrinos', 'familia']},
    {'valor': 'Amiga', 'genero': 'f', 'marcas': ['amigos']},
    {'valor': 'Amigo', 'genero': 'm', 'marcas': ['amigos']},
    # Ex: reconquistar o hacer las paces. No es "casal": no ve boda, aniversario, revelación ni jubilación.
    {'valor': 'Mi ex (ella)', 'genero': 'f', 'marcas': ['ex'], 'rotulo': 'ex'},
    {'valor': 'Mi ex (él)', 'genero': 'm', 'marcas': ['ex'], 'rotulo': 'ex'},
    {'valor': MAIS_DE_UMA, 'genero': 'g', 'marcas': ['grupo', 'familia', 'mae', 'pai', 'casal_pais']},
    {'valor': PARA_MIM, 'genero': 'x', 'marcas': ['eu']},
    {'valor': OUTRA_PESSOA, 'genero': 'x', 'marcas': ['outra']},
]

# Ocasiões: "para" = marcadores que veem a opção (TODOS = qualquer relação); "exceto" = marcadores que não veem.
# Os valores usados pelas páginas de ocasião da landing (textos.json: landing.paginas.*.quiz) não podem mudar sozinhos.
OCASIOES = [
    {'valor': 'Cumpleaños', 'para': TODOS},
    {'valor': '10 de mayo (Día de las Madres)', 'para': ['mae']},
    {'valor': 'Día del Padre', 'para': ['pai']},
    {'valor': '14 de febrero (Amor y Amistad)', 'para': ['casal', 'ex', 'amigos']},
    {'valor': 'Boda', 'para': TODOS, 'exceto': ['ex']},
    {'valor': 'Pedir perdón', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'Graduación', 'para': ['filhos', 'irmaos', 'amigos', 'casal', 'eu', 'grupo', 'outra']},
    {'valor': 'Solo porque te quiero', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'Navidad', 'para': TODOS},
    {'valor': 'XV años', 'para': ['filhos', 'irmaos', 'amigos', 'outra']},
    {'valor': 'Aniversario de bodas o de novios', 'para': ['casal', 'casal_pais']},
    {'valor': 'Propuesta de matrimonio', 'para': ['namoro']},
    {'valor': 'Para agradecer', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'Para echarle ganas', 'para': TODOS},
    {'valor': 'Celebrar un logro', 'para': TODOS},
    {'valor': 'Para decirte que te extraño', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'En memoria de quien ya partió', 'para': TODOS, 'exceto': ['eu']},
    {'valor': 'Primera Comunión', 'para': ['filhos', 'grupo', 'outra']},
    {'valor': 'Bautizo', 'para': ['filhos', 'grupo', 'outra']},
    {'valor': 'Revelación de género', 'para': ['casal', 'filhos', 'grupo', 'eu', 'outra'], 'exceto': ['ex']},
    {'valor': 'Día del Niño', 'para': ['filhos', 'grupo', 'outra']},
    {'valor': 'Jubilación', 'para': ['mae', 'pai', 'casal', 'irmaos', 'amigos', 'padrinos', 'eu', 'grupo', 'outra']},
    {'valor': 'Celebrar mi historia', 'para': ['eu']},
    {'valor': OUTRA_OCASIAO, 'para': TODOS, 'texto': True},   # abre un campo "¿Cuál?"
]

# Tons: o valor é a chave do "clima" em conteudo/es-MX/estilos.json (as mesmas chaves do Brasil).
TONS = [
    {'valor': 'romantica', 'texto': 'Romántica 💕', 'para': ['casal', 'ex']},
    {'valor': 'emocionante', 'texto': 'Emotiva 🥹', 'para': TODOS},
    {'valor': 'animada', 'texto': 'Alegre y fiestera 🎉', 'para': TODOS,
     'exceto_ocasioes': ['En memoria de quien ya partió']},
    {'valor': 'inspiradora', 'texto': 'Inspiradora ✨', 'para': TODOS},
    {'valor': 'engracado', 'texto': 'Divertida 😂', 'para': TODOS,
     'exceto_ocasioes': ['En memoria de quien ya partió', 'Pedir perdón']},
    {'valor': 'reflexiva', 'texto': 'Nostálgica 🌅', 'para': TODOS},
]

# Ordem = a aposta de venda (a serenata e o regional romântico na frente); reordenar com os dados, como no Brasil.
ESTILOS = [
    ['mariachi', 'Mariachi / Ranchera'], ['banda', 'Banda romántica'], ['grupera', 'Grupera romántica'],
    ['balada', 'Balada romántica'], ['norteno', 'Norteño'], ['bolero', 'Bolero (trío romántico)'], ['cumbia', 'Cumbia'],
    ['corrido', 'Corrido tumbado'], ['pop', 'Pop latino'], ['rock', 'Rock en español'], ['bachata', 'Bachata'],
    ['reggaeton', 'Reguetón'], ['cristiana', 'Cristiana / Alabanza'], ['infantil', 'Infantil'], ['vals', 'Vals'],
]
ESTILOS_ANTIGOS = {}

VOZES = {'femenina': 'Voz femenina', 'masculina': 'Voz masculina', 'dueto': 'Dueto', 'trio': 'Trío romántico',
         'coro': 'Voz femenina con coro'}
VOZES_PADRAO = ['femenina', 'masculina']
VOZES_POR_ESTILO = {
    'banda': ['femenina', 'masculina', 'dueto'],
    'norteno': ['femenina', 'masculina', 'dueto'],
    'grupera': ['femenina', 'masculina', 'dueto'],
    'bolero': ['femenina', 'masculina', 'trio'],
    'cristiana': ['femenina', 'masculina', 'coro'],
}

# Perguntas guiadas das lembranças, pelo marcador da relação (a primeira que bater; senão "padrao").
LEMBRANCAS = {
    'casal': [
        {'pergunta': 'Cómo se conocieron o un momento que los marcó', 'exemplo': 'Ej.: Nos conocimos en una boda en el 98 y bailamos toda la noche.'},
        {'pergunta': 'Una manía o costumbre suya que te encanta', 'exemplo': 'Ej.: Canta a todo pulmón en el carro y se equivoca en todas las letras.'},
        {'pergunta': 'Lo que quieres que {ela} sienta al escuchar la canción', 'exemplo': 'Ej.: Que después de 25 años la volvería a escoger mil veces.'},
    ],
    'ex': [
        {'pergunta': 'Un momento de ustedes que nunca olvidaste', 'exemplo': 'Ej.: El viaje a la playa en que llovió los tres días y nos reímos de todo.'},
        {'pergunta': 'Algo {dela} que extrañas', 'exemplo': 'Ej.: Cómo cantaba en el carro, siempre con la letra mal.'},
        {'pergunta': 'Lo que quieres que {ela} sepa hoy', 'exemplo': 'Ej.: Que me equivoqué, que aprendí y que todavía pienso en ti.'},
    ],
    'grupo': [
        {'pergunta': 'Un recuerdo de ustedes', 'exemplo': 'Ej.: Las vacaciones en casa de la abuelita, todos durmiendo en la sala.'},
        {'pergunta': 'Cómo es cada quien (puede ser una palabra para cada uno)', 'exemplo': 'Ej.: Ana es la bromista, Bety la que da consejos, Carmen la que cuida a todos.'},
        {'pergunta': 'Lo que les quieres decir con esta canción', 'exemplo': 'Ej.: Que aunque estemos lejos, siempre vamos a ser familia.'},
    ],
    'eu': [
        {'pergunta': 'Un momento que marcó tu vida', 'exemplo': 'Ej.: Cuando me fui sola a Monterrey a los 18 años.'},
        {'pergunta': 'Un logro o algo que superaste', 'exemplo': 'Ej.: Terminé la carrera de enfermería después de los 40, trabajando de día y estudiando de noche.'},
        {'pergunta': 'Lo que quieres celebrar hoy', 'exemplo': 'Ej.: Que hoy estoy orgullosa de la mujer que soy.'},
    ],
    'padrao': [
        {'pergunta': 'Un recuerdo especial con {ela}', 'exemplo': 'Ej.: Todos los domingos hacía pozole para toda la familia.'},
        {'pergunta': 'Una costumbre, manía o frase muy suya', 'exemplo': 'Ej.: Canta mientras lava los trastes y siempre dice "Dios proveerá".'},
        {'pergunta': 'Lo que le quieres agradecer o decir', 'exemplo': 'Ej.: Gracias por sacarnos adelante tú sola, con tanto amor.'},
    ],
}
MIN_LETRAS_LEMBRANCAS = 40   # somando as 3 respostas

PERGUNTAS = [
    {
        'chave': 'para_quem', 'tipo': 'opcoes',
        'titulo': '¿Para quién es la canción?',
        'opcoes': [r['valor'] for r in RELACOES],
    },
    {
        'chave': 'pessoas', 'tipo': 'pessoas',
        'titulo': '¿Cómo se llama {da_sua_pessoa}?',
        'titulo_grupo': '¿Cómo se llaman las personas que la van a recibir?',
        'titulo_eu': '¿Cómo te llamas?',
        'ajuda': 'Su nombre va a aparecer en la letra de la canción.',
        'ajuda_grupo': f'Hasta {MAX_PESSOAS} personas. Todos los nombres van a aparecer en la canción.',
    },
    {
        'chave': 'ocasiao', 'tipo': 'opcoes',
        'titulo': '¿Para qué ocasión es la canción de {nome}?',
        'titulo_eu': '¿Para qué ocasión es tu canción?',
        'opcoes': [o['valor'] for o in OCASIOES],
    },
    {
        'chave': 'lembrancas', 'tipo': 'lembrancas',
        'titulo': 'Ahora, lo más importante 💛',
        'ajuda': 'Cuéntanos la historia de {nome}. Entre más detalles, más se va a parecer a ustedes la canción.',
        'ajuda_eu': 'Cuéntanos tu historia. Entre más detalles, más se va a parecer a ti la canción.',
    },
    {
        'chave': 'frase_obrigatoria', 'tipo': 'texto',
        'titulo': '¿Hay alguna frase que no puede faltar en la canción de {nome}?',
        'titulo_eu': '¿Hay alguna frase que no puede faltar en tu canción?',
        'exemplo': 'Ej.: Dios te bendiga siempre (puedes dejarlo en blanco)',
    },
    {
        'chave': 'clima', 'tipo': 'opcoes',
        'titulo': '¿Qué sentimiento quieres que tenga?',
        'ajuda': 'Lo que la canción va a transmitir.',
        'opcoes': [[t['valor'], t['texto']] for t in TONS],
    },
    {
        'chave': 'estilo', 'tipo': 'opcoes',
        'titulo': '¿Qué música le gusta más a {nome}?',
        'titulo_eu': '¿Qué música te gusta más?',
        'opcoes': ESTILOS,
    },
    {
        'chave': 'voz', 'tipo': 'opcoes',
        'titulo': '¿Quién la canta?',
        'opcoes': [[k, v] for k, v in VOZES.items()],
    },
    {
        'chave': 'contato', 'tipo': 'contato',
        'titulo': '¿A dónde te mandamos tu canción?',
        'ajuda': 'Te avisamos en cuanto esté lista.',
    },
]
