-- Migration 018: Renomear template WhatsApp de 'entrega_pedido_venda' para 'entrega_pedido'
-- O nome do template foi alterado no WhatsApp Business Manager.
-- Esta migration atualiza o campo mensagem em acoes_fluxo_produto para refletir o novo nome.

USE vendasdb;
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Atualiza o nome do template em todas as ações que usam o template antigo
UPDATE acoes_fluxo_produto
SET mensagem = 'entrega_pedido'
WHERE mensagem = 'entrega_pedido_venda'
  AND acao = 'enviar_produto_whatsapp';

-- Verifica se a atualização foi aplicada
SELECT
    id,
    produto_id,
    fluxo,
    ordem,
    acao,
    mensagem AS template_name,
    param1,
    param2
FROM acoes_fluxo_produto
WHERE acao = 'enviar_produto_whatsapp';
