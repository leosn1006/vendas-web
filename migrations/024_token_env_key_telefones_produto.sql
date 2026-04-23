-- Adiciona coluna token_env_key em telefones_produto.
-- Armazena o NOME da variável de ambiente que contém o token da conta WhatsApp deste número.
-- Ex: 'WHATSAPP_ACCESS_TOKEN' (conta principal) ou 'WHATSAPP_ACCESS_TOKEN_2' (segunda conta).
-- Todos os registros existentes herdam o valor padrão sem quebra.

ALTER TABLE telefones_produto
  ADD COLUMN token_env_key VARCHAR(100) NOT NULL DEFAULT 'WHATSAPP_ACCESS_TOKEN';
