-- Migration 005: SUPREME produção institucional / enterprise

ALTER TABLE ieo_logs
    ADD COLUMN IF NOT EXISTS algorithm_version TEXT NOT NULL DEFAULT 'IEO-1.0.0',
    ADD COLUMN IF NOT EXISTS algorithm_parameters JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    actor TEXT NOT NULL DEFAULT 'system',
    action TEXT NOT NULL,
    subject_id_hash TEXT,
    resource TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_subject ON audit_log(subject_id_hash);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

CREATE TABLE IF NOT EXISTS algorithm_registry (
    algorithm_version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    git_commit TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO algorithm_registry(algorithm_version, name, parameters, is_active)
VALUES ('IEO-1.0.0', 'SUPREME IEO baseline-saturated score', '{"weights":{"z_t":0.5,"z_e":0.3,"z_v":0.2,"z_d_delta":0.1},"saturation":"logistic"}'::jsonb, TRUE)
ON CONFLICT (algorithm_version) DO NOTHING;

CREATE OR REPLACE FUNCTION log_subject_erasure(p_subject TEXT, p_actor TEXT DEFAULT 'system') RETURNS VOID AS $$
BEGIN
    INSERT INTO audit_log(actor, action, subject_id_hash, resource, metadata)
    VALUES (p_actor, 'subject_erasure_requested', p_subject, 'all_subject_tables', '{}'::jsonb);
END;
$$ LANGUAGE plpgsql;
