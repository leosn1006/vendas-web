-- notificacoes_conta_whatsapp nasceu write-only (fase 1, sem UI). Agora que vai ter tela
-- própria, precisa de um resumo legível igual notificacoes_telefone já tem, em vez de só
-- payload_raw cru.
ALTER TABLE notificacoes_conta_whatsapp
    ADD COLUMN mensagem TEXT NULL;
