-- Fila de atendimento por e-mail (caixa admin@lsnlivros.com.br): um registro leve por e-mail
-- recebido de cliente/empresa, SEM copiar o corpo — o conteúdo é lido do Gmail na hora (tela do
-- admin). Aqui ficam só as decisões: triagem, vínculo com pedido (pode não existir), resposta
-- sugerida e status. Os marcadores do Gmail são espelho do `estado` (fonte da verdade é o banco).
--
-- Diferente de notificacoes_pedido (pedido_id/produto_id NOT NULL): boa parte dos e-mails chega
-- sem pedido identificado (ex: e-mail em branco para a chave PIX) e precisa aparecer na fila.
CREATE TABLE IF NOT EXISTS emails_atendimento (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    gmail_message_id    VARCHAR(64)  NOT NULL,
    gmail_thread_id     VARCHAR(64)  NOT NULL,
    rfc_message_id      VARCHAR(255) NULL COMMENT 'Header Message-ID: vira In-Reply-To da resposta',
    remetente_email     VARCHAR(150) NOT NULL,
    remetente_nome      VARCHAR(150) NULL,
    destinatario        VARCHAR(255) NULL COMMENT 'Alias que recebeu (ex: pudim@ = chave PIX do produto)',
    assunto             VARCHAR(255) NULL,
    recebido_em         DATETIME     NOT NULL,

    tipo                ENUM('vendas','administrativo','ruido') NOT NULL,
    categoria           VARCHAR(30)  NOT NULL COMMENT 'chave_pix, acesso_estante, pagou_e_cobrado, pagamento, reclamacao, quer_comprar, duvida_uso, agradecimento, administrativo, ruido, outros',
    motivo_triagem      VARCHAR(255) NULL,

    pedido_id           INT NULL,
    produto_id          INT NULL,
    metodo_vinculo      ENUM('thread','numero_pedido','email','telefone','cpf','comprovante','nome','humano') NULL,
    candidatos          JSON NULL COMMENT 'Pedidos candidatos quando o vínculo foi ambíguo (humano escolhe)',

    estado              ENUM('a_responder','aguardando_aprovacao','aguardando_cliente','respondido','sem_acao') NOT NULL,
    resposta_tipo       VARCHAR(30)  NULL COMMENT 'estante_pago, estante_nao_pago_wpp, pagina_vendas_nao_pago, chave_pix, pedir_dados, ia',
    resposta_html       MEDIUMTEXT   NULL COMMENT 'Corpo interno sugerido/enviado (sem a moldura da marca)',
    resposta_automatica TINYINT(1)   NOT NULL DEFAULT 0,
    respondido_em       DATETIME     NULL,
    respondido_por      VARCHAR(150) NULL COMMENT 'e-mail do usuário do admin, sistema, gmail ou substituido',

    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_emails_atendimento_msg (gmail_message_id),
    INDEX idx_emails_atendimento_estado (estado, recebido_em),
    INDEX idx_emails_atendimento_thread (gmail_thread_id),
    INDEX idx_emails_atendimento_remetente (remetente_email, respondido_em),
    FOREIGN KEY (pedido_id)  REFERENCES pedidos(id),
    FOREIGN KEY (produto_id) REFERENCES produtos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
