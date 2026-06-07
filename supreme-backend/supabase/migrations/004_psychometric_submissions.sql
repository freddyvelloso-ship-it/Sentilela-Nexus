-- Migration 004: tabela de submissoes psicometricas (nivel submissao, nao item)
-- Corrige incompatibilidade entre db.py e schema 003

CREATE TABLE IF NOT EXISTS psychometric_submissions (
    record_id   BIGSERIAL    PRIMARY KEY,
    id_hash     TEXT         NOT NULL,
    instrument  TEXT         NOT NULL,
    score       FLOAT        NOT NULL,
    timestamp   DATE         NOT NULL DEFAULT CURRENT_DATE,
    window_ref  DATE         NOT NULL,
    responses   JSONB        NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_ps_user       ON psychometric_submissions (id_hash);
CREATE INDEX IF NOT EXISTS idx_ps_instrument ON psychometric_submissions (id_hash, instrument);
CREATE INDEX IF NOT EXISTS idx_ps_timestamp  ON psychometric_submissions (timestamp);
