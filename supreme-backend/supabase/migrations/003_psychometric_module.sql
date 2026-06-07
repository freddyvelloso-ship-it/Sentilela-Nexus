-- =============================================================================
-- SUPREME V4 — Migração 003: Módulo Psicométrico
-- Tabelas: instrument_schedule, psychometric_items, psi_scores
-- =============================================================================

-- ── 1. instrument_schedule ───────────────────────────────────────────────────
-- Controla quando cada instrumento é devido por usuário.
-- Atualizado automaticamente após cada submissão.
CREATE TABLE instrument_schedule (
    id_hash         TEXT                    NOT NULL,
    instrument      psychometric_instrument NOT NULL,
    last_submitted  TIMESTAMPTZ,
    next_due        TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    study_week      INTEGER                 DEFAULT 0,  -- semana no protocolo (afeta freq. DASS-21)
    created_at      TIMESTAMPTZ             DEFAULT NOW(),
    updated_at      TIMESTAMPTZ             DEFAULT NOW(),
    PRIMARY KEY (id_hash, instrument)
);

CREATE INDEX idx_schedule_user ON instrument_schedule (id_hash);
CREATE INDEX idx_schedule_due  ON instrument_schedule (next_due);

-- ── 2. psychometric_items ────────────────────────────────────────────────────
-- Armazena respostas individuais por item para auditabilidade e recálculo.
CREATE TABLE psychometric_items (
    item_id         BIGSERIAL    PRIMARY KEY,
    submission_id   BIGINT       NOT NULL,   -- FK → psychometric_data.record_id
    id_hash         TEXT         NOT NULL,
    instrument      psychometric_instrument NOT NULL,
    item_number     INTEGER      NOT NULL,   -- 1-based
    response        FLOAT        NOT NULL,   -- valor bruto do item
    submitted_at    TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX idx_items_submission ON psychometric_items (submission_id);
CREATE INDEX idx_items_user       ON psychometric_items (id_hash);

-- ── 3. psi_scores ────────────────────────────────────────────────────────────
-- PSI composto por janela de 14 dias + classificação OEI-PSI.
CREATE TABLE psi_scores (
    id_hash          TEXT   NOT NULL,
    window_start     DATE   NOT NULL,
    psi_score        FLOAT,              -- PSI = 0.35·z_DASS + 0.30·z_OLBI + 0.20·z_SRQ + 0.15·z_PANAS_neg
    z_dass           FLOAT,
    z_olbi           FLOAT,
    z_srq            FLOAT,
    z_panas_neg      FLOAT,
    dass_raw         FLOAT,
    olbi_raw         FLOAT,
    srq_raw          FLOAT,
    panas_neg_raw    FLOAT,
    convergence_class TEXT  CHECK (convergence_class IN (
                                 'convergence',      -- OEI alto + PSI alto
                                 'baseline',         -- OEI baixo + PSI baixo
                                 'residual_burden',  -- OEI baixo + PSI alto
                                 'divergence'        -- OEI alto + PSI baixo (risco mascarado)
                             )),
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id_hash, window_start)
);

CREATE INDEX idx_psi_user ON psi_scores (id_hash);

-- ── 4. Policies RLS para novas tabelas ───────────────────────────────────────
ALTER TABLE instrument_schedule  ENABLE ROW LEVEL SECURITY;
ALTER TABLE psychometric_items   ENABLE ROW LEVEL SECURITY;
ALTER TABLE psi_scores           ENABLE ROW LEVEL SECURITY;

CREATE POLICY "operator_all_schedule" ON instrument_schedule TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_items"    ON psychometric_items  TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_psi"      ON psi_scores          TO supreme_operator USING (true) WITH CHECK (true);

CREATE POLICY "analytics_read_psi"    ON psi_scores FOR SELECT TO supreme_analytics USING (true);

COMMENT ON TABLE instrument_schedule IS 'Agendamento de instrumentos psicométricos por usuário. Atualizado após cada submissão.';
COMMENT ON TABLE psychometric_items  IS 'Respostas brutas por item. Permite recálculo de scores e auditoria.';
COMMENT ON TABLE psi_scores          IS 'PSI composto por janela de 14 dias. Inclui classificação OEI-PSI (convergência/divergência).';
