-- Adiciona coluna api_phone_number_id à tabela telefones_produto
-- Separa o display phone (usado para lookup de produto e link wa.me) do
-- phone_number_id da API Meta (usado para enviar mensagens pelo WhatsApp Business API)
ALTER TABLE telefones_produto
    ADD COLUMN api_phone_number_id VARCHAR(50) NULL
        COMMENT 'ID da API WhatsApp Business (phone_number_id do Meta), usado para enviar mensagens';

-- Preenche api_phone_number_id para os telefones já cadastrados
UPDATE telefones_produto SET api_phone_number_id = '974838442380155'  WHERE produto_id = 1;
UPDATE telefones_produto SET api_phone_number_id = '1012710858592627' WHERE produto_id = 6;
