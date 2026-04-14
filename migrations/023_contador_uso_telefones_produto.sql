-- Adiciona contador de uso para distribuição round-robin entre números de WhatsApp por produto
ALTER TABLE telefones_produto
    ADD COLUMN contador_uso INT NOT NULL DEFAULT 0;
