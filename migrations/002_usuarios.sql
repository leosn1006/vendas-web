-- ============================================================
-- Migration 002: Criação da tabela de usuários administrativos
-- ============================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    email      VARCHAR(255) NOT NULL UNIQUE,
    senha      VARCHAR(255) NOT NULL,  -- bcrypt hash
    nome       VARCHAR(255) NOT NULL,
    perfil     ENUM('admin', 'consulta') NOT NULL DEFAULT 'consulta',
    ativo      BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Índices
CREATE INDEX idx_usuarios_email  ON usuarios(email);
CREATE INDEX idx_usuarios_perfil ON usuarios(perfil);
CREATE INDEX idx_usuarios_ativo  ON usuarios(ativo);
