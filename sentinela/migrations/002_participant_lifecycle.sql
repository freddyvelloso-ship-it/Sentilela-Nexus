-- SENTINELA — Ciclo de vida de participantes
-- Permite descontinuar, reativar e excluir (lógico) participantes do estudo

CREATE TABLE IF NOT EXISTS participant_lifecycle (
    id_hash    TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'inactive', 'deleted')),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_status ON participant_lifecycle (status);
