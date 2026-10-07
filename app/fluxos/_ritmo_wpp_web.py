"""Ritmo dos followups nos chips do gateway WhatsApp Web.

Os followups param às 22h e voltam às 7h, então a primeira rodada da manhã soltava de uma vez tudo o que
acumulou durante a noite, em sequência pelo mesmo chip: o padrão de disparo em massa que levou um chip do
gateway a ser banido. Nos chips do gateway, cada rodada envia no máximo um número fixo de pedidos por chip,
os mais antigos primeiro. O que fica de fora continua elegível e sai nas rodadas seguintes. Os números da
API oficial da Meta não passam por aqui.

Só conta para o limite o pedido que de fato enviou alguma ação: um pedido que falha em toda rodada (erro,
produto sem ações configuradas) não pode ocupar a vaga do chip e travar a fila dele até sair da janela.
"""
import logging
from collections import defaultdict

from database import get_provedor_numero

logger = logging.getLogger(__name__)

# Pedidos por chip em cada rodada. O de pagamento roda a cada 30 min (até 10/h por chip); os de interesse
# rodam a cada 5 min (até 12/h por chip em cada um).
LIMITE_FOLLOWUP_PAGAMENTO = 5
LIMITE_FOLLOWUP_INTERESSE = 1


class RitmoWppWeb:
    """Uso numa rodada: `for pedido in ritmo.ordenar(pedidos)`, pular quando `not ritmo.pode_enviar(pedido)`
    e chamar `ritmo.registrar_envio(pedido)` depois que alguma ação saiu."""

    def __init__(self, limite_por_chip: int, tag: str):
        self.limite_por_chip = limite_por_chip
        self.tag = tag
        self._enviados = defaultdict(int)
        self._adiados = 0

    @staticmethod
    def ordenar(pedidos: list) -> list:
        return sorted(pedidos, key=lambda p: p['id'])

    def _chip_do_gateway(self, pedido) -> str | None:
        chip = pedido.get('phone_number_id')
        return chip if get_provedor_numero(chip) == 'wpp_web' else None

    def pode_enviar(self, pedido) -> bool:
        chip = self._chip_do_gateway(pedido)
        if chip and self._enviados[chip] >= self.limite_por_chip:
            self._adiados += 1
            return False
        return True

    def registrar_envio(self, pedido) -> None:
        chip = self._chip_do_gateway(pedido)
        if chip:
            self._enviados[chip] += 1

    def resumir(self) -> None:
        if self._adiados:
            logger.info(
                f"[{self.tag}] ⏳ {self._adiados} pedido(s) do WhatsApp Web adiado(s) para as próximas rodadas "
                f"(ritmo anti-ban).")
