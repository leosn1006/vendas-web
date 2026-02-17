"""
Módulo de tratamento centralizado de erros da aplicação.
Contém handlers para exceções globais e códigos HTTP específicos.
"""
import logging
from flask import request, jsonify
from notificacoes import notificador

logger = logging.getLogger(__name__)


def registrar_error_handlers(app):
    """
    Registra todos os error handlers na aplicação Flask.
    
    Args:
        app: Instância do Flask
    """
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """
        Captura TODOS os erros não tratados da aplicação.
        Envia notificação simples para o WhatsApp do admin (exceto 404 de bots).
        """
        # Coleta contexto mínimo
        contexto = {}
        try:
            if request and request.endpoint:
                contexto['Endpoint'] = request.endpoint
        except:
            pass

        # Notifica o erro (mensagem será simples)
        notificador.notificar_erro(e, contexto_adicional=contexto)

        # Loga detalhes completos no servidor
        logger.error(f"[ERRO GLOBAL] {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

        # Retorna resposta apropriada
        return jsonify({
            'error': 'Erro interno do servidor',
            'message': 'Um erro ocorreu e nossa equipe foi notificada'
        }), 500


    @app.errorhandler(404)
    def handle_404(e):
        """
        Tratamento especial para 404 - NÃO notifica via WhatsApp.
        Evita spam de bots fazendo scan de vulnerabilidades.
        """
        caminho = request.path
        user_agent = request.headers.get('User-Agent', '')

        # Log apenas para análise (não notifica)
        # logger.debug(f"[404] {caminho} | UA: {user_agent[:50]}")

        # Lista expandida de padrões suspeitos de bots/scanners
        padroes_suspeitos = [
            # WordPress
            'wp-', 'wordpress', 'xmlrpc', 'wlwmanifest',
            # Ferramentas admin/debug
            'phpmyadmin', 'adminer', 'debug', 'phpinfo', 'console', 'panel',
            # Arquivos sensíveis
            'config.', 'aws-config', 'aws.', 'credentials', '.env', '.git', '.sql',
            # PHP files
            '.php', '.phtml',
            # Outros scanners
            'jasperserver', 'helpdesk', 'aspera', 'cf_scripts', 'WebObjects'
        ]

        # Se for rota suspeita, retorna resposta mínima (sem gastar recursos)
        if any(padrao in caminho.lower() for padrao in padroes_suspeitos):
            return '', 404

        # Para 404 legítimos (usuário digitou URL errada), retorna JSON amigável
        return jsonify({
            'error': 'Página não encontrada',
            'message': f'A rota {caminho} não existe'
        }), 404
    
    
    logger.info("✅ Error handlers registrados com sucesso")
