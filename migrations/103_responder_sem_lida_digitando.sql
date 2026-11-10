-- Fluxo Responder: deixa de marcar a mensagem como lida e de mostrar "digitando" (app/fluxos/fluxo_responder.py).
-- Quando a IA escalava (ex.: pedido de estorno), a cliente via os tiques azuis sem resposta e achava que
-- estávamos ignorando o pedido. O fluxo é fixo no código; estas linhas só alimentam a tela do admin.
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
-- Antes, em produção, confira que cada produto tem só UMA linha no responder fora marcar_lida/digitando
-- (senão o UPDATE abaixo bate na uk_afp):
--   SELECT produto_id, COUNT(*) FROM acoes_fluxo_produto
--    WHERE fluxo = 'responder' AND acao NOT IN ('marcar_lida', 'digitando')
--    GROUP BY produto_id HAVING COUNT(*) > 1;   -- deve voltar vazio

START TRANSACTION;

DELETE FROM acoes_fluxo_produto
 WHERE fluxo = 'responder' AND acao IN ('marcar_lida', 'digitando');

-- sobra só a mensagem gerada pela IA: passa a ser a ação 1
UPDATE acoes_fluxo_produto
   SET ordem = 1
 WHERE fluxo = 'responder' AND acao = 'enviar_mensagem';

COMMIT;
