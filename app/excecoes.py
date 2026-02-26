"""
Exceções customizadas do sistema com notificação automática via WhatsApp.
"""
# Este módulo centraliza erros de domínio da aplicação.
# A ideia é padronizar mensagens, severidade e contexto para facilitar debug e alerta.

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
        # Dados básicos do erro
        self.mensagem = mensagem
        self.contexto = contexto or {}
        self.severidade = severidade
        self.notificar = notificar

        # Metadados úteis para trilha de auditoria e correlação de logs
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc()

        # Inicializa Exception com a mensagem principal
        super().__init__(mensagem)

    def formatar_para_whatsapp(self) -> str:
        """Formata o erro em uma mensagem simples para WhatsApp."""
        # Mapeia severidade para emoji para leitura rápida no celular
        emoji_severidade = {
            'CRÍTICO': '🚨',
            'ALTO': '⚠️',
            'MÉDIO': '⚡',
            'BAIXO': 'ℹ️'
        }

        emoji = emoji_severidade.get(self.severidade, '❗')
        hora = self.timestamp.strftime('%H:%M:%S')

        # Mensagem curta para alerta operacional (sem dados sensíveis)
        mensagem = f"{emoji} *Erro no sistema*\n\n"
        mensagem += f"{type(self).__name__} às {hora}\n\n"
        mensagem += f"Acesse o sistema para verificar os logs."

        return mensagem


class ErroBancoDados(ErroNotificavel):
    """Erro relacionado ao banco de dados."""

    def __init__(self, mensagem: str, query: Optional[str] = None, **kwargs):
        # Enriquece o contexto com parte da query para ajudar diagnóstico
        contexto = kwargs.get('contexto', {})
        if query:
            contexto['Query'] = query[:100] + '...' if len(query) > 100 else query
        kwargs['contexto'] = contexto

        # Erros de banco são tratados como críticos por padrão
        kwargs.setdefault('severidade', 'CRÍTICO')
        super().__init__(mensagem, **kwargs)


class ErroWhatsApp(ErroNotificavel):
    """Erro na integração com WhatsApp."""

    def __init__(self, mensagem: str, numero_destino: Optional[str] = None, **kwargs):
        # Adiciona número de destino no contexto quando disponível
        contexto = kwargs.get('contexto', {})
        if numero_destino:
            contexto['Número Destino'] = numero_destino
        kwargs['contexto'] = contexto

        # Integração externa: severidade alta por padrão
        kwargs.setdefault('severidade', 'ALTO')
        super().__init__(mensagem, **kwargs)


class ErroOpenAI(ErroNotificavel):
    """Erro na integração com OpenAI."""

    def __init__(self, mensagem: str, modelo: Optional[str] = None, **kwargs):
        # Informa o modelo usado para facilitar troubleshooting/custo
        contexto = kwargs.get('contexto', {})
        if modelo:
            contexto['Modelo'] = modelo
        kwargs['contexto'] = contexto
        kwargs.setdefault('severidade', 'ALTO')
        super().__init__(mensagem, **kwargs)


class ErroConfiguracao(ErroNotificavel):
    """Erro de configuração do sistema."""

    def __init__(self, mensagem: str, variavel: Optional[str] = None, **kwargs):
        # Erro de setup geralmente impede execução correta do sistema
        contexto = kwargs.get('contexto', {})
        if variavel:
            contexto['Variável'] = variavel
        kwargs['contexto'] = contexto
        kwargs.setdefault('severidade', 'CRÍTICO')
        super().__init__(mensagem, **kwargs)
