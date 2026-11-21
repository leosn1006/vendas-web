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

# Tela de lembranças (uma caixa só, desde 20/11/2026), pelo marcador da relação (a primeira que bater; senão
# "padrao"): `inicios` = frases para começar (as pílulas: tocar põe o começo na caixa), `medidor` = o que o medidor
# diz conforme ela escreve (abaixo do mínimo, < 150, < 350 e completo: segue as 3 partes de uma boa história),
# `dica` = o texto cinza da caixa vazia. {ela}/{dela}/{nome} (e {Ela} com maiúscula) vêm do personalizar do quiz.
LEMBRANCAS = {
    'casal': {
        'inicios': ['A gente se conheceu ', '{Ela} tem um jeito ', 'Quero que {ela} sinta '],
        'medidor': ['Comece contando como vocês se conheceram', 'Boa! Agora conte um jeito {dela} que você ama',
                    'Ótimo! E o que você quer que {ela} sinta?', 'Perfeita 💛'],
        'dica': 'Ex.: A gente se conheceu na igreja em 2009…',
    },
    'ex': {
        'inicios': ['Nunca esqueci quando ', 'Sinto falta do jeito que {ela} ', 'Quero que {ela} saiba que '],
        'medidor': ['Comece com um momento de vocês que você nunca esqueceu',
                    'Boa! Agora conte um jeito {dela} de que você sente falta',
                    'Ótimo! E o que você quer que {ela} saiba hoje?', 'Perfeita 💛'],
        'dica': 'Ex.: Nunca esqueci a viagem pra praia em que choveu os três dias…',
    },
    'grupo': {
        'inicios': ['Uma lembrança nossa é ', 'Cada um tem seu jeito ', 'Quero dizer pra vocês que '],
        'medidor': ['Comece com uma lembrança de vocês', 'Boa! Agora conte o jeito de cada pessoa',
                    'Ótimo! E o que você quer dizer com a música?', 'Perfeita 💛'],
        'dica': 'Ex.: Todo Natal a gente dorme junto na sala da casa da vó…',
    },
    'eu': {
        'inicios': ['Um momento que marcou a minha vida foi ', 'Tenho orgulho de ', 'Hoje eu quero celebrar '],
        'medidor': ['Comece com um momento que marcou a sua vida', 'Boa! Agora conte uma conquista ou superação sua',
                    'Ótimo! E o que você quer celebrar agora?', 'Perfeita 💛'],
        'dica': 'Ex.: Com 18 anos me mudei sozinha pra São Paulo…',
    },
    'padrao': {
        'inicios': ['Uma lembrança que eu guardo é ', '{Ela} sempre ', 'Quero agradecer por '],
        'medidor': ['Comece com uma lembrança marcante com {ela}', 'Boa! Agora conte um jeito ou mania {dela}',
                    'Ótimo! E o que você quer agradecer ou dizer?', 'Perfeita 💛'],
        'dica': 'Ex.: Todo domingo ela fazia bolo de fubá pra família inteira…',
    },
}
MIN_LETRAS_LEMBRANCAS = 40

# "Ver um exemplo" na tela de lembranças: histórias de OUTRAS pessoas (nunca o nome dela), do jeito que a cliente
# escreve — simples, com um detalhe concreto e as 3 partes. Pela relação; sem exemplo próprio, o da guia ("_casal",
# "_ex", "_grupo", "_eu", "_padrao"). Sem nenhum, o botão não aparece. Não há botão de copiar (de propósito).
EXEMPLOS_LEMBRANCAS = {
    'Esposa': [
        'A gente se conheceu no ônibus indo pro trabalho, em 2004. Ela sempre sentava na janela e eu fui tomando '
        'coragem. Ela canta alto fazendo o almoço de domingo e ri das próprias piadas. Quero que ela sinta que, '
        'depois de 20 anos, eu casaria com ela de novo.',
        'Casamos novos, sem nada, morando num quartinho. Ela segurou a casa quando fiquei desempregado e nunca '
        'reclamou. Ela me chama de "meu velho" desde os 25 anos. Quero que ela saiba que tudo que a gente tem é '
        'graças a ela.',
    ],
    'Namorada': [
        'A gente se conheceu num aniversário de um amigo e ficamos conversando até o dono da casa mandar todo mundo '
        'embora. Ela ri com o nariz e fica com vergonha. Quero que ela sinta que eu quero ela pra vida toda.',
        'Faz 2 anos que a gente namora à distância, ela em Recife e eu em São Paulo. Ela manda bom dia todo dia com '
        'uma foto do céu. Quero que ela sinta que a saudade vale a pena.',
    ],
    'Marido': [
        'Conheci o Zé num forró em 1995 e ele pisou no meu pé a noite inteira. Ele acorda cedo e deixa o café '
        'pronto pra mim todo dia. Quero que ele sinta o quanto eu sou grata por esses 30 anos.',
        'A gente se casou na igreja da minha cidade, com chuva. Ele é calado, mas resolve tudo e cuida de todo '
        'mundo. Quero que ele saiba que é o melhor pai e o melhor companheiro.',
    ],
    'Namorado': [
        'A gente se conheceu pelo aplicativo e no primeiro encontro ele chegou com uma flor do jardim da mãe dele. '
        'Ele faz piada até quando está nervoso. Quero que ele sinta que eu escolhi ele.',
    ],
    'Filha': [
        'Ela nasceu num dia de muita chuva e parou de chorar quando eu cantei pra ela. Ela é teimosa igual a mim e '
        'dança pela casa toda. Quero que ela saiba que eu tenho muito orgulho da mulher que ela virou.',
    ],
    'Filho': [
        'Ele foi o primeiro neto da família e todo mundo mimava. Ele me abraça forte e diz "calma, mãe". Quero que '
        'ele saiba que vou estar sempre aqui, mesmo de longe.',
    ],
    'Mãe': [
        'Minha mãe criou cinco filhos sozinha, costurando de madrugada. Ela canta hino lavando a louça e sempre diz '
        '"Deus proverá". Quero agradecer por tudo que ela abriu mão pela gente.',
    ],
    'Minha ex': [
        'A gente ficou junto 6 anos e viajou o Nordeste inteiro de carro. Sinto falta do jeito que ela ria das '
        'minhas manias. Quero que ela saiba que eu aprendi com os meus erros e que penso nela.',
    ],
    'Meu ex': [
        'A gente ficou junto 6 anos e viajou o Nordeste inteiro de carro. Sinto falta do jeito que ele ria das '
        'minhas manias. Quero que ele saiba que eu aprendi com os meus erros e que penso nele.',
    ],
    '_padrao': [
        'Minha madrinha me criou quando minha mãe foi trabalhar fora. Ela faz o melhor café do mundo e fala "vai dar '
        'certo" pra tudo. Quero agradecer por ela nunca ter me deixado sozinha.',
    ],
    '_grupo': [
        'Somos 3 irmãs e todo Natal a gente dorme junta na sala da casa da mãe. A Ana é a brincalhona, a Bia a '
        'conselheira. Quero dizer que, mesmo longe, a gente é uma só.',
    ],
    '_eu': [
        'Me mudei sozinha pra São Paulo com 18 anos. Me formei em enfermagem depois dos 40, estudando à noite. '
        'Quero celebrar quem eu me tornei.',
    ],
}

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
        'titulo': 'Conte a história de vocês 💛',
        'titulo_eu': 'Conte a sua história 💛',
        'ajuda': 'Do seu jeito, como se contasse para uma amiga. Não precisa escrever bonito.',
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
