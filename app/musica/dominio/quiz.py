"""O motor do quiz: quais opções aparecem para cada resposta e o que combina entre si. Igual para todos os idiomas;
as perguntas e as opções de cada um ficam em app/musica/conteudo/<idioma>/quiz.py (ver musica/idiomas.py).

    do_idioma('es-MX').ocasioes_para('Mamá')     # o quiz de um idioma
    ocasioes_para('Mãe')                         # atalhos do módulo = o quiz do Brasil (pt-BR)

A lógica não depende do texto das opções: grupo e "para mim" vêm de MAIS_DE_UMA / PARA_MIM do idioma, e os filtros
dos marcadores de cada relação ('eu', 'grupo', 'casal'...).
"""
from functools import lru_cache

from musica import idiomas

# Chaves aceitas nas respostas (o resto que vier do navegador é ignorado). Iguais em todos os idiomas: são os nomes
# que a IA da letra recebe.
# Tamanho máximo da história (a caixa de lembranças; a fala do microfone sai longa). Mesmo valor na tela e no servidor.
MAX_LETRAS_LEMBRANCAS = 2500

CHAVES_VALIDAS = {'para_quem', 'nome', 'apelido', 'pronuncia', 'ocasiao', 'ocasiao_outra', 'lembrancas',
                  'frase_obrigatoria', 'clima', 'estilo', 'voz', 'de'}


class Quiz:
    """As regras do quiz sobre os dados de um idioma (o módulo conteudo/<idioma>/quiz.py)."""

    def __init__(self, dados, idioma):
        self.idioma = idioma
        self.dados = dados
        d = dados
        self.MAIS_DE_UMA, self.PARA_MIM, self.MAX_PESSOAS, self.TODOS = d.MAIS_DE_UMA, d.PARA_MIM, d.MAX_PESSOAS, d.TODOS
        self.OUTRA_PESSOA, self.OUTRA_OCASIAO = d.OUTRA_PESSOA, d.OUTRA_OCASIAO
        self.RELACOES, self.OCASIOES, self.TONS, self.ESTILOS = d.RELACOES, d.OCASIOES, d.TONS, d.ESTILOS
        self.ESTILOS_ANTIGOS = getattr(d, 'ESTILOS_ANTIGOS', {})
        self.VOZES, self.VOZES_PADRAO, self.VOZES_POR_ESTILO = d.VOZES, d.VOZES_PADRAO, d.VOZES_POR_ESTILO
        self.LEMBRANCAS, self.MIN_LETRAS_LEMBRANCAS, self.PERGUNTAS = d.LEMBRANCAS, d.MIN_LETRAS_LEMBRANCAS, d.PERGUNTAS
        self.EXEMPLOS_LEMBRANCAS = getattr(d, 'EXEMPLOS_LEMBRANCAS', {})
        self.CHAVES_VALIDAS = CHAVES_VALIDAS

    def genero(self, para_quem: str) -> str:
        """f / m / g (grupo) / x (indefinido)."""
        return next((r['genero'] for r in self.RELACOES if r['valor'] == para_quem), 'x')

    def rotulo(self, para_quem: str) -> str:
        """Como a relação entra no texto: "mãe" ("da sua mãe"), "ex" ("da sua ex", não "da sua minha ex")."""
        r = next((r for r in self.RELACOES if r['valor'] == para_quem), None)
        return (r.get('rotulo') or r['valor'].lower()) if r else ''

    def marcas_da_relacao(self, para_quem: str) -> set:
        return next((set(r['marcas']) for r in self.RELACOES if r['valor'] == para_quem), {'outra'})

    def ocasioes_para(self, para_quem: str) -> list[str]:
        marcas = self.marcas_da_relacao(para_quem)
        return [o['valor'] for o in self.OCASIOES
                if (o['para'] == self.TODOS or marcas & set(o['para'])) and not marcas & set(o.get('exceto', []))]

    def relacoes_por_ocasiao(self) -> dict[str, list[str]]:
        """Ocasião → relações que a veem (os botões "Pra quem é a música?" da página de cada ocasião na landing)."""
        relacoes = [r['valor'] for r in self.RELACOES]
        return {o['valor']: [r for r in relacoes if o['valor'] in self.ocasioes_para(r)] for o in self.OCASIOES}

    def tons_para(self, para_quem: str, ocasiao: str) -> list[str]:
        marcas = self.marcas_da_relacao(para_quem)
        return [t['valor'] for t in self.TONS
                if (t['para'] == self.TODOS or marcas & set(t['para'])) and ocasiao not in t.get('exceto_ocasioes', [])]

    def estilo_atual(self, estilo: str) -> str:
        """O estilo de hoje para um valor gravado (ex.: "arrocha" → "sertanejo"); os atuais passam iguais."""
        return self.ESTILOS_ANTIGOS.get(estilo, estilo)

    def vozes_para(self, estilo: str) -> list[str]:
        return self.VOZES_POR_ESTILO.get(estilo, self.VOZES_PADRAO)

    def combinacao_invalida(self, respostas: dict) -> str | None:
        """O que não combina nas respostas (mesma regra que a tela usa), ou None. O navegador já filtra; isto é a
        conferência do servidor contra um envio feito à mão."""
        return self.relacao_invalida(respostas) or self.estilo_voz_invalido(respostas)

    def relacao_invalida(self, respostas: dict) -> str | None:
        """1ª parte da regra: relação, ocasião e tom entre si."""
        para_quem = respostas.get('para_quem')
        if para_quem not in {r['valor'] for r in self.RELACOES}:
            return 'para_quem'
        if respostas.get('ocasiao') not in self.ocasioes_para(para_quem):
            return 'ocasiao'
        if respostas.get('clima') not in self.tons_para(para_quem, respostas.get('ocasiao')):
            return 'clima'
        return None

    def estilo_voz_invalido(self, respostas: dict) -> str | None:
        """2ª parte da regra: estilo e voz entre si."""
        if respostas.get('estilo') not in {e for e, _ in self.ESTILOS}:
            return 'estilo'
        if respostas.get('voz') not in self.vozes_para(respostas.get('estilo')):
            return 'voz'
        return None

    def guia_lembrancas(self, relacao: str) -> str:
        """A guia da tela de lembranças (frases para começar, medidor, exemplo) pelo marcador da relação."""
        marcas = self.marcas_da_relacao(relacao)
        return next((g for g in ('eu', 'grupo', 'casal', 'ex') if g in marcas), 'padrao')

    def exemplos_lembrancas(self, relacao: str) -> list[str]:
        """Os exemplos de "Ver um exemplo": os da relação; senão os da guia; senão os do padrão ([] = sem botão)."""
        e = self.EXEMPLOS_LEMBRANCAS
        return e.get(relacao) or e.get('_' + self.guia_lembrancas(relacao)) or e.get('_padrao') or []

    def config_do_navegador(self) -> dict:
        """O que o quiz.html precisa, com os filtros JÁ CALCULADOS aqui (fonte única: as funções acima): ocasiões por
        relação, tons por relação e ocasião, vozes por estilo, gênero, a guia e os exemplos das lembranças por relação."""
        relacoes = [r['valor'] for r in self.RELACOES]
        ocasioes = [o['valor'] for o in self.OCASIOES]
        return {
            'genero': {r['valor']: r['genero'] for r in self.RELACOES},
            'rotulo': {r: self.rotulo(r) for r in relacoes},
            'ocasioes_por_relacao': {r: self.ocasioes_para(r) for r in relacoes},
            'tons_por_relacao': {r: {o: self.tons_para(r, o) for o in ocasioes} for r in relacoes},
            'vozes_por_estilo': {e: self.vozes_para(e) for e, _ in self.ESTILOS},
            'estilos_antigos': self.ESTILOS_ANTIGOS,
            'guia_lembrancas': {r: self.guia_lembrancas(r) for r in relacoes},
            'exemplos_lembrancas': {r: self.exemplos_lembrancas(r) for r in relacoes},
            'lembrancas': self.LEMBRANCAS, 'min_letras_lembrancas': self.MIN_LETRAS_LEMBRANCAS,
            'max_letras_lembrancas': MAX_LETRAS_LEMBRANCAS,
            'max_pessoas': self.MAX_PESSOAS, 'mais_de_uma': self.MAIS_DE_UMA, 'para_mim': self.PARA_MIM,
        }


@lru_cache(maxsize=None)
def do_idioma(idioma=None) -> Quiz:
    idioma = idiomas.valido(idioma)
    return Quiz(idiomas.dados_quiz(idioma), idioma)


# Atalhos do módulo = o quiz do Brasil (o código e os testes de antes dos idiomas continuam valendo).
_PT = do_idioma(idiomas.IDIOMA_PADRAO)
MAIS_DE_UMA, PARA_MIM, MAX_PESSOAS, TODOS = _PT.MAIS_DE_UMA, _PT.PARA_MIM, _PT.MAX_PESSOAS, _PT.TODOS
RELACOES, OCASIOES, TONS, ESTILOS, ESTILOS_ANTIGOS = _PT.RELACOES, _PT.OCASIOES, _PT.TONS, _PT.ESTILOS, _PT.ESTILOS_ANTIGOS
VOZES, VOZES_PADRAO, VOZES_POR_ESTILO = _PT.VOZES, _PT.VOZES_PADRAO, _PT.VOZES_POR_ESTILO
LEMBRANCAS, MIN_LETRAS_LEMBRANCAS, PERGUNTAS = _PT.LEMBRANCAS, _PT.MIN_LETRAS_LEMBRANCAS, _PT.PERGUNTAS
FEMININO = {r['valor'] for r in RELACOES if r['genero'] == 'f'}
MASCULINO = {r['valor'] for r in RELACOES if r['genero'] == 'm'}
rotulo, marcas_da_relacao, ocasioes_para = _PT.rotulo, _PT.marcas_da_relacao, _PT.ocasioes_para
relacoes_por_ocasiao, tons_para, estilo_atual, vozes_para = (_PT.relacoes_por_ocasiao, _PT.tons_para,
                                                            _PT.estilo_atual, _PT.vozes_para)
combinacao_invalida, relacao_invalida, estilo_voz_invalido = (_PT.combinacao_invalida, _PT.relacao_invalida,
                                                              _PT.estilo_voz_invalido)
config_do_navegador = _PT.config_do_navegador
