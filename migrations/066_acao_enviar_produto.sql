ALTER TABLE acoes_fluxo_produto
    MODIFY COLUMN acao ENUM(
        'marcar_lida',
        'digitando',
        'enviar_audio',
        'enviar_imagem',
        'enviar_arquivo',
        'enviar_mensagem',
        'enviar_produto_whatsapp',
        'enviar_produto'
    ) NOT NULL;
