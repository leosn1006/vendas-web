-- Migration 073: suporte ao teste A/B da estante v2 (cross-sell) — ver plano
-- ~/.claude/plans/peaceful-seeking-pizza.md.
--
-- variante_checkout marca em qual versão do checkout o pedido nasceu (default 'v1' preserva
-- todo o histórico, mesmo padrão de migrations/051_variantes_conteudo_acoes_fluxo.sql).
-- Só é gravada 'v2' pelo fluxo novo (/pay2/<produto_id>) — como essa rota só é alcançada a
-- partir do botão "Comprar" do cross-sell da estante v2, um pedido variante_checkout='v2'
-- É, por definição, uma compra de cross-sell (não precisa de outra coluna pra marcar isso).
ALTER TABLE pedidos
    ADD COLUMN variante_checkout ENUM('v1', 'v2') NOT NULL DEFAULT 'v1' AFTER fluxo_inicial;

-- estante_visualizacoes registra cada abertura de /pedido/<guid> (v1) ou /pedido2/<guid> (v2)
-- — só pra ter o denominador da taxa de clique (visualizou → comprou) na comparação v1/v2.
-- Não é log genérico de eventos, é propositalmente essa única métrica.
CREATE TABLE estante_visualizacoes (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id  INT NOT NULL,
    variante   ENUM('v1', 'v2') NOT NULL,
    criado_em  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_estante_visualizacoes_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_estante_visualizacoes_variante_data ON estante_visualizacoes(variante, criado_em);
