"""
Sistema de notificações de erro via WhatsApp.
"""
import os
import time
from datetime import datetime, timedelta
from typing import Optional
from functools import wraps
from flask import request
import requests
from config import WHATSAPP_API_URL


class GerenciadorNotificacoes:
    """
    Gerencia o envio de notificações de erro via WhatsApp.
    Implementa rate limiting para evitar spam.
    """

    def __init__(self):
        self.telefone_admin = os.getenv('ADMIN_WHATSAPP_NUMBER')
        self.whatsapp_token = os.getenv('WHATSAPP_ACCESS_TOKEN')
        self.phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        self.url_api = WHATSAPP_API_URL

        # Rate limiting: máximo de notificações por período
        self.max_notificacoes_por_hora = 10
        self.historico_notificacoes = []

        # Cache de erros já notificados (evita duplicatas)
        self.erros_recentes = {}
        self.tempo_cache_erro = 300  # 5 minutos

    def _limpar_historico_antigo(self):
        """Remove notificações antigas do histórico."""
        uma_hora_atras = datetime.now() - timedelta(hours=1)
        self.historico_notificacoes = [
            ts for ts in self.historico_notificacoes
            if ts > uma_hora_atras
        ]

    def _pode_enviar(self) -> tuple[bool, Optional[str]]:
        """
        Verifica se pode enviar uma notificação.
        Retorna (pode_enviar, motivo_se_nao).
        """
        # Verifica configuração
        if not self.telefone_admin:
            return False, "ADMIN_WHATSAPP_NUMBER não configurado"

        if not self.whatsapp_token or not self.phone_number_id:
            return False, "Credenciais do WhatsApp não configuradas"

        # Limpa histórico antigo
        self._limpar_historico_antigo()

        # Verifica rate limit
        if len(self.historico_notificacoes) >= self.max_notificacoes_por_hora:
            return False, f"Limite de {self.max_notificacoes_por_hora} notificações/hora atingido"

        return True, None

    def _erro_ja_notificado(self, mensagem_erro: str) -> bool:
        """Verifica se um erro similar já foi notificado recentemente."""
        agora = time.time()

        # Limpa erros antigos do cache
        erros_validos = {
            msg: timestamp
            for msg, timestamp in self.erros_recentes.items()
            if agora - timestamp < self.tempo_cache_erro
        }
        self.erros_recentes = erros_validos

        # Verifica se erro já foi notificado
        if mensagem_erro in self.erros_recentes:
            return True

        return False

    def enviar_notificacao(self, mensagem: str, forcar: bool = False) -> bool:
        """
        Envia uma notificação via WhatsApp para o admin.

        Args:
            mensagem: Texto da notificação
            forcar: Se True, ignora rate limiting (usar com cuidado)

        Returns:
            True se enviou com sucesso, False caso contrário
        """
        # Verifica se já notificou erro similar recentemente
        if not forcar and self._erro_ja_notificado(mensagem):
            print(f"[NOTIFICAÇÃO] Erro já notificado recentemente, pulando...")
            return False

        # Verifica se pode enviar
        pode_enviar, motivo = self._pode_enviar()
        if not pode_enviar and not forcar:
            print(f"[NOTIFICAÇÃO] Não enviada: {motivo}")
            return False

        try:
            url = f"{self.url_api}{self.phone_number_id}/messages"

            headers = {
                "Authorization": f"Bearer {self.whatsapp_token}",
                "Content-Type": "application/json"
            }

            # Remove o + do número se existir
            numero_limpo = self.telefone_admin.replace('+', '')

            payload = {
                "messaging_product": "whatsapp",
                "to": numero_limpo,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": mensagem
                }
            }

            response = requests.post(url, json=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                # Registra no histórico
                self.historico_notificacoes.append(datetime.now())
                self.erros_recentes[mensagem] = time.time()
                print(f"[NOTIFICAÇÃO] ✅ Enviada com sucesso para {self.telefone_admin}")
                return True
            else:
                print(f"[NOTIFICAÇÃO] ❌ Erro ao enviar: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"[NOTIFICAÇÃO] ❌ Exceção ao enviar: {e}")
            return False

    def notificar_erro(self, erro: Exception, contexto_adicional: Optional[dict] = None):
        """
        Notifica um erro via WhatsApp.
        Trata tanto exceções customizadas quanto padrão.
        """
        from excecoes import ErroNotificavel

        # Se for uma exceção customizada, usa a formatação dela
        if isinstance(erro, ErroNotificavel):
            if not erro.notificar:
                return

            mensagem = erro.formatar_para_whatsapp()
        else:
            # Exceção padrão - mensagem simples
            hora = datetime.now().strftime('%H:%M:%S')
            endpoint = ""
            if contexto_adicional and 'Endpoint' in contexto_adicional:
                endpoint = f" em {contexto_adicional['Endpoint']}"

            mensagem = f"⚠️ *Erro no sistema*\n\n"
            mensagem += f"{type(erro).__name__}{endpoint} às {hora}\n\n"
            mensagem += f"Acesse o sistema para verificar os logs."

        self.enviar_notificacao(mensagem)


# Instância global do gerenciador
notificador = GerenciadorNotificacoes()


def notificar_erro(forcar: bool = False):
    """
    Decorator para capturar e notificar erros em funções/rotas.

    Args:
        forcar: Se True, ignora rate limiting

    Uso:
        @notificar_erro()
        def minha_funcao():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Captura contexto da requisição se disponível
                contexto = {}
                try:
                    if request:
                        contexto['Endpoint'] = request.endpoint
                        contexto['Método'] = request.method
                        contexto['IP'] = request.remote_addr
                except:
                    pass

                # Notifica o erro
                notificador.notificar_erro(e, contexto_adicional=contexto)

                # Re-levanta a exceção para que o Flask possa processar
                raise

        return wrapper
    return decorator
