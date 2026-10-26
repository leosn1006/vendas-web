"""O que o resto do sistema (checkout, tasks, e-mail de entrega, Estante 2) usa da Música.
Fachada fina sobre os casos de uso: quem está fora do módulo não conhece portas nem adaptadores."""
import re

from musica import casos_de_uso
from musica.casos_de_uso import Recusa
from musica.dominio.recursos import plano_vende_musica
from musica.fabrica import servicos

__all__ = ['Recusa', 'plano_vende_musica', 'conferir_para_checkout', 'vincular_ao_pedido', 'liberar_do_pedido',
           'musica_do_pedido_pago', 'presente_devolvido', 'token_do_pedido', 'dados_para_checkout', 'webhook_whatsapp']


def conferir_para_checkout(token: str, produto_id: int) -> None:
    """Recusa (com a mensagem para a tela) se a música do link não pode ser comprada neste produto."""
    casos_de_uso.musica_para_checkout(servicos(), token, produto_id)


def vincular_ao_pedido(token: str, pedido_id: int, produto_id: int, whatsapp: str = '', ddi: str = '55') -> None:
    casos_de_uso.vincular_ao_pedido(servicos(), token, pedido_id, produto_id, whatsapp, ddi)


def liberar_do_pedido(pedido_id: int) -> bool:
    return casos_de_uso.liberar_do_pedido(servicos(), pedido_id)


def musica_do_pedido_pago(pedido: dict, exigir_liberada: bool = True) -> dict | None:
    """Para o e-mail de entrega e a Estante 2: {titulo, para, caminho} da música liberada por este pedido
    (caminho relativo da área da compra; quem chama põe o endereço do site na frente, se precisar).
    `exigir_liberada=False` (e-mail de entrega, que só sai uma vez): devolve a música do pedido mesmo que a
    liberação ainda não tenha rodado — a área da compra libera na hora ou mostra "sendo liberada"."""
    s = servicos()
    musica = s.repositorio.do_pedido(pedido['id'])
    if not musica or (exigir_liberada and not musica['liberada_em']):
        return None
    from musica.dominio.regras import para_quem
    return {'titulo': musica['titulo'] or 'Sua música', 'para': para_quem(musica['respostas']),
            'caminho': f"/musica/compra/{pedido['guid']}"}


def presente_devolvido(thread_id: str, recusados: list[str]) -> bool:
    """Para a leitura da caixa do admin@: uma devolução (mailer-daemon) que é de um presente da Música.
    `recusados` = endereços que a devolução diz que recusaram (vazio se ela não disser)."""
    return casos_de_uso.presente_devolvido(servicos(), thread_id, recusados)


def token_do_pedido(pedido_id: int) -> str | None:
    """A música já gravada neste pedido. Só para contextos em que o pedido é comprovadamente da cliente (cookie do
    próprio navegador, e-mail enviado a ela): o token dá acesso à música — nunca a partir de um id vindo da requisição."""
    musica = servicos().repositorio.do_pedido(pedido_id)
    return musica['token'] if musica else None


def dados_para_checkout(token: str) -> dict:
    """O e-mail e o WhatsApp do quiz, para o checkout já abrir preenchido (quem tem o token é quem fez o quiz;
    o JS do checkout tira o 55 e põe a máscara). O nome não: o quiz pede só o primeiro nome, e o checkout precisa
    do nome completo de quem paga."""
    musica = servicos().repositorio.por_token(token)
    return {'email': musica['email'] or '', 'whatsapp': _celular_br(musica.get('whatsapp'))} if musica else {}


def _celular_br(numero) -> str:
    """Só celular brasileiro (55 + DDD + 9 + 8 dígitos; o quiz antigo gravou sem o 55): o campo do checkout tem o
    +55 fixo, e um número de fora viraria um brasileiro errado. Outro formato = '' (ela digita)."""
    digitos = re.sub(r'\D', '', numero or '')
    if len(digitos) == 11:
        digitos = '55' + digitos
    return digitos if len(digitos) == 13 and digitos.startswith('55') and digitos[4] == '9' else ''


def webhook_whatsapp(valor: dict) -> None:
    """Para o orquestrador: o `value` de um webhook da Meta vindo do número só de avisos da Música (status de
    entrega, toque no botão, mensagens — que são ignoradas)."""
    casos_de_uso.webhook_whatsapp(servicos(), valor)
