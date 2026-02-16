"""
Exceções customizadas do sistema com notificação automática via WhatsApp.
"""
from datetime import datetime
from typing import Optional
import traceback


class ErroNotificavel(Exception):
    """
    Exceção base que automaticamente envia notificação via WhatsApp.

    Atributos:
        mensagem: Mensagem de erro amigável
        contexto: Dicionário com informações adicionais do erro
        severidade: 'CRÍTICO', 'ALTO', 'MÉDIO', 'BAIXO'
        notificar: Se deve enviar notificação (padrão: True)
    """

    def __init__(
        self,
        mensagem: str,
        contexto: Optional[dict] = None,
        severidade: str = 'ALTO',
        notificar: bool = True
    ):
        self.mensagem = mensagem
        self.contexto = contexto or {}
        self.severidade = severidade
        self.notificar = notificar
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc()

        super().__init__(mensagem)

    def formatar_para_whatsapp(self) -> str:
        """Formata o erro em uma mensagem simples para WhatsApp."""
        emoji_severidade = {
            'CRÍTICO': '🚨',
            'ALTO': '⚠️',
            'MÉDIO': '⚡',
            'BAIXO': 'ℹ️'
        }

        emoji = emoji_severidade.get(self.severidade, '❗')
        hora = self.timestamp.strftime('%H:%M:%S')

        # Mensagem simples e direta
        mensagem = f"{emoji} *Erro no sistema*\n\n"
        mensagem += f"{type(self).__name__} às {hora}\n\n"
        mensagem += f"Acesse o sistema para verificar os logs."

        return mensagem


class ErroBancoDados(ErroNotificavel):
    """Erro relacionado ao banco de dados."""

    def __init__(self, mensagem: str, query: Optional[str] = None, **kwargs):
        contexto = kwargs.get('contexto', {})
        if query:
            contexto['Query'] = query[:100] + '...' if len(query) > 100 else query
        kwargs['contexto'] = contexto
        kwargs.setdefault('severidade', 'CRÍTICO')
        super().__init__(mensagem, **kwargs)


class ErroWhatsApp(ErroNotificavel):
    """Erro na integração com WhatsApp."""

    def __init__(self, mensagem: str, numero_destino: Optional[str] = None, **kwargs):
        contexto = kwargs.get('contexto', {})
        if numero_destino:
            contexto['Número Destino'] = numero_destino
        kwargs['contexto'] = contexto
        kwargs.setdefault('severidade', 'ALTO')
        super().__init__(mensagem, **kwargs)


class ErroOpenAI(ErroNotificavel):
    """Erro na integração com OpenAI."""

    def __init__(self, mensagem: str, modelo: Optional[str] = None, **kwargs):
        contexto = kwargs.get('contexto', {})
        if modelo:
            contexto['Modelo'] = modelo
        kwargs['contexto'] = contexto
        kwargs.setdefault('severidade', 'ALTO')
        super().__init__(mensagem, **kwargs)


class ErroConfiguracao(ErroNotificavel):
    """Erro de configuração do sistema."""

    def __init__(self, mensagem: str, variavel: Optional[str] = None, **kwargs):
        contexto = kwargs.get('contexto', {})
        if variavel:
            contexto['Variável'] = variavel
        kwargs['contexto'] = contexto
        kwargs.setdefault('severidade', 'CRÍTICO')
        super().__init__(mensagem, **kwargs)
