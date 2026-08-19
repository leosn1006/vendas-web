-- Migration 053: Base para conversas por e-mail (pedidos web 1000-1004)
-- gmail_thread_id ancora as respostas do cliente ao pedido certo (threading nativo do Gmail,
-- mais robusto que regex no assunto). email_bloqueado é independente de pedidos.bloqueado
-- (que é exclusivo do fluxo WhatsApp) — bloquear a IA num canal não deve silenciar o outro.
-- prompt_vendas_email permite calibrar o tom/instruções do agente de e-mail por produto sem
-- reaproveitar prompt_vendas (moldado para o tom de chat do WhatsApp).

ALTER TABLE pedidos
    ADD COLUMN gmail_thread_id VARCHAR(255) NULL
        COMMENT 'threadId do Gmail da conversa de e-mail deste pedido (thread da entrega + respostas)',
    ADD COLUMN email_bloqueado TINYINT(1) NOT NULL DEFAULT 0
        COMMENT 'Bloqueia a IA de responder e-mail deste pedido — independente de pedidos.bloqueado (WhatsApp)';

ALTER TABLE produtos
    ADD COLUMN prompt_vendas_email TEXT NULL
        COMMENT 'Prompt do agente de e-mail para este produto; se vazio, usa prompt_vendas + instruções padrão de tom/HTML (ver fluxos/agente_resposta_email_produto.py)';
