"""
Exemplos de uso do sistema de notificações de erro.

IMPORTANTE: As mensagens enviadas ao WhatsApp são SIMPLES E GENÉRICAS.
Você receberá apenas:
  - Emoji de severidade (🚨 ⚠️ ⚡ ℹ️)
  - Tipo da exceção (ex: ErroBancoDados)
  - Horário (ex: às 14:32:18)

Exemplo de notificação recebida:
  "🚨 Erro no sistema
   ErroBancoDados às 14:32:18
   Acesse o sistema para verificar os logs."

Todos os detalhes (contexto, traceback, query SQL, etc) ficam nos LOGS DO SERVIDOR
para você analisar quando acessar o sistema.
"""
import sys
import os
from datetime import datetime

# Adiciona o diretório app/ ao path para importar os módulos
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))

from excecoes import (  # type: ignore
    ErroNotificavel,
    ErroBancoDados,
    ErroWhatsApp,
    ErroOpenAI,
    ErroConfiguracao
)
from notificacoes import notificador, notificar_erro  # type: ignore
from flask import Flask

app = Flask(__name__)


# ========== EXEMPLO 1: Usar decorator em rotas críticas ==========

@app.post("/api/v1/webhook-whatsapp")
@notificar_erro()  # Qualquer erro nesta rota será notificado
def webhook_receive():
    # Seu código aqui
    # Se ocorrer qualquer erro, você será notificado no WhatsApp
    pass


# ========== EXEMPLO 2: Levantar exceções customizadas ==========

def processar_pagamento(valor: float, cliente_id: int):
    """Exemplo de função que pode levantar erro customizado."""
    try:
        # Simulando erro no banco
        # resultado = db.execute(query)
        raise Exception("Conexão perdida")
    except Exception as e:
        # Levanta erro customizado
        # Mensagem no WhatsApp será simples: "🚨 Erro no sistema / ErroBancoDados às HH:MM:SS"
        # Contexto é salvo nos logs do servidor para análise posterior
        raise ErroBancoDados(
            mensagem="Falha ao processar pagamento",
            query="UPDATE pagamentos SET status = 'pago'",
            contexto={
                'Cliente ID': cliente_id,
                'Valor': f'R$ {valor:.2f}',
            },
            severidade='CRÍTICO'
        )


# ========== EXEMPLO 3: Notificar erro manualmente ==========

def integrar_com_api_externa():
    """Exemplo de notificação manual sem levantar exceção."""
    try:
        # response = requests.post(...)
        pass
    except Exception as e:
        # Notifica mas não interrompe o fluxo
        # Você receberá: "⚡ Erro no sistema / ErroWhatsApp às HH:MM:SS"
        erro = ErroWhatsApp(
            mensagem="Falha ao enviar mensagem para cliente",
            numero_destino="5511999999999",
            severidade='MÉDIO'
        )
        notificador.notificar_erro(erro)

        # Continua executando com fallback
        return False


# ========== EXEMPLO 4: Handler global para erros não tratados ==========

@app.errorhandler(Exception)
def handle_exception(e):
    """Captura TODOS os erros não tratados da aplicação."""
    # Notifica qualquer erro (mensagem será simples)
    contexto = {'Endpoint': 'desconhecido'}
    try:
        if hasattr(e, '__traceback__'):
            contexto['Endpoint'] = getattr(e, 'endpoint', 'desconhecido')
    except:
        pass

    notificador.notificar_erro(e, contexto_adicional=contexto)

    # Retorna resposta apropriada
    return {'error': 'Erro interno do servidor'}, 500


# ========== EXEMPLO 5: Verificar configuração na inicialização ==========

def verificar_configuracao_inicial():
    """Verifica configurações críticas ao iniciar a aplicação."""
    import os

    variaveis_obrigatorias = [
        'WHATSAPP_TOKEN',
        'OPENAI_API_KEY',
        'DB_PASSWORD',
        'ADMIN_WHATSAPP_NUMBER'  # Nova variável!
    ]

    for var in variaveis_obrigatorias:
        if not os.getenv(var):
            # Você receberá: "🚨 Erro no sistema / ErroConfiguracao às HH:MM:SS"
            # Detalhes como qual variável está faltando ficam nos logs
            raise ErroConfiguracao(
                mensagem=f"Variável {var} não configurada",
                variavel=var,
                severidade='CRÍTICO'
            )


# ========== EXEMPLO 6: Diferentes níveis de severidade ==========

def exemplo_severidades():
    """Mostra os diferentes níveis de severidade."""

    # CRÍTICO - Sistema não consegue funcionar
    # WhatsApp: "🚨 Erro no sistema / ErroConfiguracao às HH:MM:SS"
    raise ErroConfiguracao(
        mensagem="Banco de dados inacessível",
        severidade='CRÍTICO'
    )

    # ALTO - Funcionalidade importante falhou
    # WhatsApp: "⚠️ Erro no sistema / ErroWhatsApp às HH:MM:SS"
    raise ErroWhatsApp(
        mensagem="Não foi possível enviar mensagem ao cliente",
        severidade='ALTO'
    )

    # MÉDIO - Problema que afeta usuários mas tem fallback
    # WhatsApp: "⚡ Erro no sistema / ErroOpenAI às HH:MM:SS"
    # MÉDIO - Problema que afeta usuários mas tem fallback
    # WhatsApp: "⚡ Erro no sistema / ErroOpenAI às HH:MM:SS"
    raise ErroOpenAI(
        mensagem="API da OpenAI lenta, usando cache",
        severidade='MÉDIO'
    )

    # BAIXO - Informativo
    # WhatsApp: "ℹ️ Erro no sistema / ErroNotificavel às HH:MM:SS"
    raise ErroNotificavel(
        mensagem="Limite de requisições próximo do máximo",
        severidade='BAIXO'
    )


# ========== EXEMPLO 7: Notificação customizada (não erro) ==========

def monitorar_metricas():
    """Envia notificação informativa customizada."""
    # Para relatórios ou mensagens customizadas, use enviar_notificacao diretamente
    mensagem = (
        "📊 *Resumo do dia*\n\n"
        "45 pedidos - R$ 2.850\n"
        "✅ Sistema estável"
    )

    # Força o envio (ignora rate limiting)
    notificador.enviar_notificacao(mensagem, forcar=True)


# ========== EXEMPLO 8: Testar o sistema de notificações ==========

def testar_notificacoes():
    """Teste rápido do sistema de notificações."""
    try:
        # Teste 1: Mensagem simples de teste
        mensagem = (
            "🧪 *Teste de notificação*\n\n"
            f"Sistema funcionando às {datetime.now().strftime('%H:%M:%S')}"
        )

        sucesso = notificador.enviar_notificacao(mensagem, forcar=True)

        if sucesso:
            print("✅ Sistema de notificações funcionando!")
        else:
            print("❌ Falha ao enviar notificação de teste")

    except Exception as e:
        print(f"❌ Erro no teste: {e}")


if __name__ == '__main__':
    # Execute este arquivo para testar
    testar_notificacoes()
