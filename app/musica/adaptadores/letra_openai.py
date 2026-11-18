"""EscritorLetra pela OpenAI, no mesmo padrão dos nossos agentes (agente_resposta_produto.py): cliente
OpenAI() com a OPENAI_API_KEY do sistema, chat.completions, e os erros da API viram ErroLetra.
A saída é JSON pelo json_schema (o modelo só pode devolver título + letras + observação)."""
import json
import logging

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, OpenAI, RateLimitError

from musica.dominio.modelos import ErroLetra, Letra

logger = logging.getLogger(__name__)

FORMATO = {
    'type': 'json_schema',
    'json_schema': {
        'name': 'letra',
        'strict': True,
        'schema': {
            'type': 'object',
            'properties': {
                'titulo': {'type': 'string'},
                'letra_exibicao': {'type': 'string'},
                'letra_suno': {'type': 'string'},
                'observacao': {'type': 'string'},
            },
            'required': ['titulo', 'letra_exibicao', 'letra_suno', 'observacao'],
            'additionalProperties': False,
        },
    },
}


def mensagem_do_quiz(respostas: dict, letra_anterior: str | None, ajuste: str | None, idioma: str | None = None) -> str:
    """O pedido para a IA: as respostas em JSON e, num ajuste, a letra anterior. O texto em volta é o do idioma
    (textos.json: letra.*), o mesmo das instruções que ela recebe."""
    from musica.idiomas import texto as t
    texto = t(idioma, 'letra.respostas') + '\n```json\n' + json.dumps(dict(respostas), ensure_ascii=False, indent=2) + '\n```'
    if letra_anterior and ajuste:
        texto += ('\n\n' + t(idioma, 'letra.anterior') + '\n```\n' + letra_anterior + '\n```\n'
                  + t(idioma, 'letra.ajuste') + '\n' + ajuste)
    return texto


class LetraOpenAI:
    def __init__(self, modelo: str, esforco: str = 'medium'):
        self.modelo, self.esforco = modelo, esforco
        self._cliente = None

    def _openai(self):
        if self._cliente is None:
            self._cliente = OpenAI(timeout=120.0)
        return self._cliente

    def escrever(self, instrucoes, respostas, letra_anterior=None, ajuste=None, idioma=None) -> Letra:
        # Modelos antigos (gpt-4o, gpt-4.1...) não têm raciocínio e recusam o parâmetro.
        extras = {} if self.modelo.startswith('gpt-4') else {'reasoning_effort': self.esforco}
        try:
            resposta = self._openai().chat.completions.create(
                model=self.modelo,
                messages=[{'role': 'system', 'content': instrucoes},
                          {'role': 'user', 'content': mensagem_do_quiz(respostas, letra_anterior, ajuste, idioma)}],
                response_format=FORMATO,
                max_completion_tokens=16000,
                **extras,
            )
        except (RateLimitError, AuthenticationError, APIConnectionError, APITimeoutError) as exc:
            logger.error(f'[MUSICA-LETRA] ❌ Erro OpenAI ({type(exc).__name__}): {exc}')
            raise ErroLetra(f'OpenAI fora do ar ({type(exc).__name__})') from exc
        except APIStatusError as exc:
            logger.error(f'[MUSICA-LETRA] ❌ OpenAI recusou ({exc.status_code}): {exc}')
            raise ErroLetra(f'erro da IA ({exc.status_code})') from exc

        escolha = resposta.choices[0]
        uso = resposta.usage
        logger.info(f'[MUSICA-LETRA] modelo {resposta.model}, {uso.prompt_tokens} tokens de entrada, '
                    f'{uso.completion_tokens} de saída')
        if escolha.finish_reason == 'length':
            raise ErroLetra('a letra ficou incompleta')
        if getattr(escolha.message, 'refusal', None) or not escolha.message.content:
            raise ErroLetra('a IA recusou o pedido')
        try:
            dados = json.loads(escolha.message.content)
        except json.JSONDecodeError as exc:
            raise ErroLetra('resposta da IA em formato inválido') from exc
        if dados.get('observacao'):
            logger.info(f"[MUSICA-LETRA] Observação da IA: {dados['observacao']}")
        return Letra(dados['titulo'], dados['letra_exibicao'], dados['letra_suno'], dados.get('observacao', ''))


class LetraSimulada:
    """Para o dev sem chave da OpenAI (e os testes)."""
    modelo = 'simulado'

    def escrever(self, instrucoes, respostas, letra_anterior=None, ajuste=None, idioma=None) -> Letra:
        nome = respostas.get('apelido') or respostas.get('nome') or 'você'
        letra = ('[Intro]\n(' + nome + '...)\n\n'
                 '[Verse 1]\nEsta é uma letra de teste\nFeita pra conferir o site\n'
                 'Quando a chave da IA chegar\nA letra de verdade vem aqui\n\n'
                 '[Chorus]\n' + nome + ', essa música é sua\nCada verso é um abraço\n'
                 'Do jeito que você merece\nCom carinho, passo a passo\n\n'
                 '[Outro]\nCom amor, ' + (respostas.get('de') or 'alguém especial'))
        if ajuste:
            letra += f'\n(ajuste pedido: {ajuste})'
        return Letra(f'Pra Você, {nome}', letra, letra)
