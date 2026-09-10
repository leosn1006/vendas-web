ALTER TABLE pedidos
    ADD COLUMN fluxo_inicial ENUM('web', 'wpp') NULL AFTER estado_id;

UPDATE pedidos
SET fluxo_inicial = CASE
    WHEN estado_id >= 1000 THEN 'web'
    ELSE 'wpp'
END;

ALTER TABLE pedidos
    MODIFY COLUMN fluxo_inicial ENUM('web', 'wpp') NOT NULL DEFAULT 'wpp';
