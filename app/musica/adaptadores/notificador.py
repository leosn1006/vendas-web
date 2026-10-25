"""Notificador: e-mail pelo Gmail do sistema (fluxos/_email_gmail), WhatsApp pelo número só de avisos da Música
(API oficial da Meta, templates aprovados) e alerta para a equipe.

Fora de produção NADA é enviado por e-mail (vai só para o log), como nos apps: o dev tem banco isolado, mas o envio
pelo Gmail é real. O WhatsApp só envia com MUSICA_WHATSAPP_ATIVO=1; no dev, mesmo ligado, o endereço da Meta é o
endereço morto do config.py (regra do projeto) e o envio falha.
"""
import html
import logging
import os

import config
from musica.portas import ErroPassageiro

logger = logging.getLogger(__name__)

# Templates aprovados na conta "Canção de Presente" (WABA 1060756910314417), conferidos na Meta em 22/10/2026.
# Parâmetros posicionais ({{1}}, {{2}}...) na ordem da lista `variaveis`; idioma pt_BR; rodapé fixo.
MODELOS_WHATSAPP = {
    'musica_pronta': {'categoria': 'UTILITY', 'parametros': 3},       # quem comprou, para quem, link
    'presente_surpresa': {'categoria': 'MARKETING', 'parametros': 2,  # quem ganha, quem mandou
                          'botao': 'Ouvir minha música'},             # resposta rápida (payload = token da música)
    'entrega_feita': {'categoria': 'MARKETING', 'parametros': 2},     # quem comprou, quem ganhou
}


class Notificador:
    def __init__(self, repositorio, whatsapp_ativo: bool = False):
        self.repositorio, self.whatsapp_ativo = repositorio, whatsapp_ativo

    def email(self, produto_id, destino, assunto, html_corpo, cc=None):
        if not config.EH_PRODUCAO:
            logger.info(f'[MUSICA][DEV] E-mail NÃO enviado para {destino} (cc {cc}): {assunto}')
            return 'dev-sem-envio'   # "enviado" no dev: a manutenção não o reenvia como envio interrompido
        from fluxos._email_gmail import enviar, wrapper_html
        produto = self.repositorio.remetente_do_produto(produto_id)
        nome = produto.get('email_nome_remetente') or produto.get('nome') or 'Canção de Presente'
        remetente = produto.get('email_remetente') or os.getenv('EMAIL_FROM', '')
        cor = produto.get('email_cor_primaria') or '#E11D48'
        pagina = wrapper_html(titulo_header=html.escape(nome), corpo_interno_html=html_corpo, nome_remetente=nome,
                              cor_primaria=cor, cor_secundaria=produto.get('email_cor_secundaria') or cor,
                              rodape=f'Dúvidas? É só responder este e-mail. {html.escape(nome)}')
        resultado = enviar(destinatario=destino, remetente=remetente, nome_remetente=nome, subject=assunto, html=pagina,
                           cc=cc) or {}
        return resultado.get('threadId')

    def _numero(self, produto_id=None):
        """O número de avisos do produto da música (pausado ou não); sem produto, o da Música à venda."""
        if not produto_id:
            produto_id = (self.repositorio.produto_musica() or {}).get('id')
        numero = self.repositorio.numero_avisos(produto_id) if produto_id else None
        if not numero:
            raise RuntimeError('Produto Música sem número só de avisos cadastrado (telefones_produto, responde_mensagens = 0)')
        return numero

    def whatsapp(self, telefone, modelo, variaveis, payload_botao=None, produto_id=None):
        """Template aprovado; devolve o wamid. None = WhatsApp da Música desligado (MUSICA_WHATSAPP_ATIVO)."""
        if not self.whatsapp_ativo:
            logger.info(f'[MUSICA] WhatsApp desligado: {modelo} para ...{str(telefone)[-4:]} não enviado')
            return None
        info = MODELOS_WHATSAPP[modelo]
        if len(variaveis) != info['parametros']:
            raise ValueError(f'{modelo} pede {info["parametros"]} parâmetros, vieram {len(variaveis)}')
        from whatsapp import ErroTransienteWhatsApp, enviar_template
        # A Meta recusa parâmetro vazio ou com quebra de linha: garante texto curto de uma linha.
        parametros = [(' '.join(str(v or '-').split()) or '-')[:300] for v in variaveis]
        try:
            return enviar_template(self._numero(produto_id), telefone, modelo, parametros,
                                   payload_botao=payload_botao if info.get('botao') else None)
        except ErroTransienteWhatsApp as e:
            raise ErroPassageiro(str(e)) from e

    def whatsapp_texto(self, telefone, texto, produto_id=None):
        """Texto livre pelo número de avisos (vale dentro da janela de 24 h que a pessoa abriu ao tocar no botão)."""
        if not self.whatsapp_ativo:
            logger.info(f'[MUSICA] WhatsApp desligado: texto para ...{str(telefone)[-4:]} não enviado')
            return None
        from whatsapp import enviar_mensagem
        return enviar_mensagem({'phone_number_id': self._numero(produto_id), 'contact_phone': telefone}, texto)

    def equipe(self, mensagem):
        logger.error(f'[MUSICA][ALERTA] {mensagem}')
        try:
            from whatsapp import notificar_admin_erro_sistema
            notificar_admin_erro_sistema(f'MUSICA | {mensagem}'[:300], log='log_worker')
        except Exception as e:
            logger.error(f'[MUSICA] Falha ao avisar a equipe: {e}')
