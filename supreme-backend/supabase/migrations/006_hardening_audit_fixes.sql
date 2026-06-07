-- =============================================================================
-- SUPREME V5 — Migração 006: hardening pós-auditoria externa
-- Corrige lacunas de LGPD, índices, consentimento, RLS e tabela psicométrica órfã.
-- =============================================================================

-- BUG-07: garantir coluna usada por upsert_schedule mesmo em bancos parcialmente migrados.
ALTER TABLE instrument_schedule
    ADD COLUMN IF NOT EXISTS last_submitted TIMESTAMPTZ;

-- BUG-06: psychometric_data foi substituída por psychometric_submissions.
-- Mantida apenas até migração de dados legados; tabela nova é a fonte canônica.
DROP TABLE IF EXISTS psychometric_data CASCADE;

-- LGPD-03: consentimento formal do titular, verificado antes do processamento analítico.
CREATE TABLE IF NOT EXISTS subject_consents (
    id_hash TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('granted', 'revoked')),
    actor TEXT NOT NULL DEFAULT 'system',
    granted_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_subject_consents_status ON subject_consents(status);

-- DB-01 / DB-06: índices usados por fetch_baseline e diagnóstico operacional por usuário.
CREATE INDEX IF NOT EXISTS idx_baseline_active
    ON baseline_parameters(id_hash, baseline_status)
    WHERE baseline_status = 'active';
CREATE INDEX IF NOT EXISTS idx_health_id_hash
    ON system_health_logs(id_hash)
    WHERE id_hash IS NOT NULL;

-- LGPD-04: documentação operacional da retenção; enforcement via scripts/retention_cleanup.sh.
COMMENT ON TABLE events_raw IS 'Retenção operacional: 18 meses; aplicar scripts/retention_cleanup.sh via cron externo.';
COMMENT ON TABLE system_health_logs IS 'Retenção operacional: 90 dias; aplicar scripts/retention_cleanup.sh via cron externo.';

-- ARQ-04: força RLS em tabelas principais para impedir bypass acidental do owner.
ALTER TABLE events_raw FORCE ROW LEVEL SECURITY;
ALTER TABLE sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE window_metrics FORCE ROW LEVEL SECURITY;
ALTER TABLE ieo_logs FORCE ROW LEVEL SECURITY;
ALTER TABLE baseline_parameters FORCE ROW LEVEL SECURITY;
ALTER TABLE critical_load_flags FORCE ROW LEVEL SECURITY;
ALTER TABLE system_health_logs FORCE ROW LEVEL SECURITY;
ALTER TABLE dead_letter_queue FORCE ROW LEVEL SECURITY;
ALTER TABLE instrument_schedule FORCE ROW LEVEL SECURITY;
ALTER TABLE psychometric_submissions FORCE ROW LEVEL SECURITY;
ALTER TABLE psychometric_items FORCE ROW LEVEL SECURITY;
ALTER TABLE psi_scores FORCE ROW LEVEL SECURITY;
ALTER TABLE subject_consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE subject_consents FORCE ROW LEVEL SECURITY;

-- Compose atual usa o role 'supreme' como usuário de aplicação; enquanto não há
-- role app_operator dedicado, concedemos a membership necessária para as policies.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supreme')
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supreme_operator') THEN
        GRANT supreme_operator TO supreme;
    END IF;
END $$;


DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'subject_consents' AND policyname = 'operator_all_consents') THEN
        CREATE POLICY operator_all_consents ON subject_consents TO supreme_operator USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'subject_consents' AND policyname = 'analytics_read_consents') THEN
        CREATE POLICY analytics_read_consents ON subject_consents FOR SELECT TO supreme_analytics USING (true);
    END IF;
END $$;
