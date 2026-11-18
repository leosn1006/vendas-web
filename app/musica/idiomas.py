"""Idiomas da Música (docs/MUSICA.md, seção "Idiomas"). Cada idioma = idioma + país (pt-BR, es-MX; depois es-US,
en-US) e tem:

  - um endereço próprio (o mesmo blueprint registrado com outro prefixo e nome);
  - uma pasta de conteúdo, app/musica/conteudo/<idioma>/:
        estilos.json          o som de cada estilo para o gerador (Suno)
        instrucoes_letra.md   o que a IA da letra recebe
        quiz.py               perguntas e opções do quiz (as regras ficam em dominio/quiz.py)
        textos.json           as frases do site, dos e-mails e das mensagens de erro
  - um produto próprio no banco (produtos.idioma).

A música grava o idioma na criação (musicas.idioma): tudo depois dela usa o idioma DA MÚSICA, nunca o da URL.
Idioma novo = pasta de conteúdo + uma linha em IDIOMAS + o produto no banco.
"""
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

IDIOMA_PADRAO = 'pt-BR'

IDIOMAS = {
    'pt-BR': {
        'prefixo': '/musica', 'blueprint': 'musica', 'html_lang': 'pt-BR', 'fuso': 'America/Sao_Paulo',
        'pagina_analytics': 'musica-v2', 'telefone': 'br', 'moeda': 'BRL', 'bandeira': '🇧🇷', 'pais': 'Brasil',
        'pasta_amostras': '',            # static/estilos/<estilo>.mp3 (o Brasil veio primeiro)
    },
    'es-MX': {
        'prefixo': '/mx/cancion', 'blueprint': 'musica_mx', 'html_lang': 'es-MX', 'fuso': 'America/Mexico_City',
        'pagina_analytics': 'musica-mx', 'telefone': 'mx', 'moeda': 'MXN', 'bandeira': '🇲🇽', 'pais': 'México',
        'pasta_amostras': 'es-MX/',      # static/estilos/es-MX/<estilo>.mp3
        # endereços em espanhol para as mesmas páginas (rotas.py: _rota troca o nome)
        'endpoints': {'criar': 'crear', 'termos': 'terminos', 'privacidade': 'privacidad'},
        # Fora do seletor de país do rodapé até o lançamento: o produto do México pode estar ativo para mostrar o
        # site a quem vai dar opinião, sem aparecer um link para o México na landing que vende no Brasil.
        'no_seletor': False,
        # Ainda sem checkout (a Hotmart vem em outra frente): sem lembretes por e-mail, que convidariam a comprar
        # algo que a prévia diz que não está à venda. Ligar junto com o checkout.
        'vende': False,
    },
}

PASTA_CONTEUDO = Path(__file__).resolve().parent / 'conteudo'


def valido(idioma) -> str:
    """O idioma, se conhecido; senão o padrão (música antiga, sem idioma gravado, é do Brasil)."""
    return idioma if idioma in IDIOMAS else IDIOMA_PADRAO


def do_blueprint(nome_blueprint) -> str:
    return next((i for i, cfg in IDIOMAS.items() if cfg['blueprint'] == nome_blueprint), IDIOMA_PADRAO)


def cfg(idioma) -> dict:
    return IDIOMAS[valido(idioma)]


def pasta(idioma) -> Path:
    return PASTA_CONTEUDO / valido(idioma)


@lru_cache(maxsize=None)
def estilos(idioma) -> dict:
    return json.loads((pasta(idioma) / 'estilos.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=None)
def instrucoes_letra(idioma) -> str:
    return (pasta(idioma) / 'instrucoes_letra.md').read_text(encoding='utf-8')


@lru_cache(maxsize=None)
def textos(idioma) -> dict:
    return json.loads((pasta(idioma) / 'textos.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=None)
def dados_quiz(idioma):
    """O módulo conteudo/<idioma>/quiz.py (a pasta tem hífen, por isso o import pelo caminho)."""
    idioma = valido(idioma)
    spec = importlib.util.spec_from_file_location(f"musica_conteudo_quiz_{idioma.replace('-', '_')}",
                                                  pasta(idioma) / 'quiz.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def texto(idioma, chave, **valores) -> str:
    """Uma frase do textos.json pelo caminho ("erros.limite_letras"), com {marcas} trocadas. Chave que falta no
    idioma cai no pt-BR (nunca uma tela quebrada por uma frase esquecida)."""
    for fonte in (textos(idioma), textos(IDIOMA_PADRAO)):
        atual = fonte
        for parte in chave.split('.'):
            atual = atual.get(parte) if isinstance(atual, dict) else None
        if isinstance(atual, str):
            return atual.format(**valores) if valores else atual
    return chave
