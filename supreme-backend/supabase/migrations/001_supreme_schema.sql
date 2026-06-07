-- =============================================================================
-- SUPREME V4 — Schema PostgreSQL 15+
-- Migração 001: Schema completo conforme especificação técnica v1.0
-- =============================================================================

-- ── Extensões ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- pg_cron não disponível no postgres:alpine — limpeza feita por job externo

-- =============================================================================
-- ENUM: instrumento psicométrico (seção 23)
-- =============================================================================
CREATE TYPE psychometric_instrument AS ENUM (
    'SRQ20',
    'DASS21',
    'OLBI',
    'PANAS_SHORT'
);

-- =============================================================================
-- TABELA: events_raw (seção 18)
-- Camada: Raw Telemetry
-- Particionamento RANGE mensal por timestamp (C2)
-- Deduplicação via event_hash (C4)
-- Retenção: 18 meses (C7)
-- =============================================================================
CREATE TABLE events_raw (
    event_id         BIGSERIAL,
    id_hash          TEXT         NOT NULL,          -- SHA-256(user_id + SALT)
    timestamp        TIMESTAMPTZ  NOT NULL,
    event_type       TEXT         NOT NULL
                         CHECK (event_type IN (
                             'file_open',
                             'image_view',
                             'video_play',
                             'classification_event'
                         )),
    media_type       TEXT         NOT NULL
                         CHECK (media_type IN ('image', 'video', 'preview')),
    severity         INTEGER      NOT NULL
                         CHECK (severity BETWEEN 1 AND 5),
    duration_seconds FLOAT,
    source_tool      TEXT         DEFAULT 'iped',
    event_hash       TEXT         NOT NULL,           -- SHA-256 dos campos de identidade do evento; exclui duration_seconds para permitir enriquecimento tardio
    created_at       TIMESTAMPTZ  DEFAULT NOW()
) PARTITION BY RANGE (timestamp);

-- Constraint de deduplicação (C4)
-- Nota: UNIQUE em tabela particionada exige incluir a chave de partição
-- A deduplicação via INSERT ... ON CONFLICT DO NOTHING usa o event_hash

-- Índices herdados por todas as partições (PG 15+)
CREATE INDEX idx_events_user       ON events_raw (id_hash);
CREATE INDEX idx_events_timestamp  ON events_raw (timestamp);
CREATE INDEX idx_events_user_time  ON events_raw (id_hash, timestamp);
CREATE INDEX idx_events_hash       ON events_raw (event_hash);

-- Partições para os primeiros 18 meses do estudo (2026-01 a 2027-06)
-- Script de manutenção mensal cria novas partições automaticamente (ver pg_cron abaixo)
CREATE TABLE events_raw_2026_01 PARTITION OF events_raw
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE events_raw_2026_02 PARTITION OF events_raw
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE events_raw_2026_03 PARTITION OF events_raw
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE events_raw_2026_04 PARTITION OF events_raw
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE events_raw_2026_05 PARTITION OF events_raw
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE events_raw_2026_06 PARTITION OF events_raw
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE events_raw_2026_07 PARTITION OF events_raw
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE events_raw_2026_08 PARTITION OF events_raw
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE events_raw_2026_09 PARTITION OF events_raw
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE events_raw_2026_10 PARTITION OF events_raw
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE events_raw_2026_11 PARTITION OF events_raw
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE events_raw_2026_12 PARTITION OF events_raw
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
CREATE TABLE events_raw_2027_01 PARTITION OF events_raw
    FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');
CREATE TABLE events_raw_2027_02 PARTITION OF events_raw
    FOR VALUES FROM ('2027-02-01') TO ('2027-03-01');
CREATE TABLE events_raw_2027_03 PARTITION OF events_raw
    FOR VALUES FROM ('2027-03-01') TO ('2027-04-01');
CREATE TABLE events_raw_2027_04 PARTITION OF events_raw
    FOR VALUES FROM ('2027-04-01') TO ('2027-05-01');
CREATE TABLE events_raw_2027_05 PARTITION OF events_raw
    FOR VALUES FROM ('2027-05-01') TO ('2027-06-01');
CREATE TABLE events_raw_2027_06 PARTITION OF events_raw
    FOR VALUES FROM ('2027-06-01') TO ('2027-07-01');

-- Criação de partições futuras: executar manualmente conforme necessário
-- CREATE TABLE events_raw_YYYY_MM PARTITION OF events_raw FOR VALUES FROM ('YYYY-MM-01') TO ('YYYY-MM+1-01');

-- =============================================================================
-- VIEW: latência entre eventos (seção 14.1)
-- =============================================================================
CREATE VIEW event_latency AS
SELECT
    id_hash,
    timestamp,
    timestamp - LAG(timestamp) OVER (
        PARTITION BY id_hash ORDER BY timestamp
    ) AS delta_t
FROM events_raw;

-- =============================================================================
-- TABELA: sessions (seção 19)
-- Camada: Processed Behavioral Data
-- Retenção: permanente
-- =============================================================================
CREATE TABLE sessions (
    session_id     UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    id_hash        TEXT         NOT NULL,
    session_start  TIMESTAMPTZ  NOT NULL,
    session_end    TIMESTAMPTZ  NOT NULL,
    duration_minutes FLOAT,
    event_count    INTEGER,
    created_at     TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX idx_sessions_user  ON sessions (id_hash);
CREATE INDEX idx_sessions_start ON sessions (session_start);

-- =============================================================================
-- TABELA: window_metrics (seção 20)
-- Camada: Processed Behavioral Data
-- Janela de 14 dias (quinzenal)
-- Retenção: permanente
-- =============================================================================
CREATE TABLE window_metrics (
    id_hash      TEXT   NOT NULL,
    window_start DATE   NOT NULL,
    t_minutes    FLOAT,              -- Exposure Time: soma de minutos de sessão
    e_events     INTEGER,            -- Event Count: total eventos válidos
    v_volume     FLOAT,              -- Exposure Volume: Σ W_k × duration
    d_density    FLOAT,              -- Density: E / T
    dq_score     FLOAT,              -- Data Quality: [0,1] proporção de eventos válidos
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (id_hash, window_start)
);

CREATE INDEX idx_window_user ON window_metrics (id_hash);

-- =============================================================================
-- TABELA: ieo_logs (seção 21)
-- Camada: Analytical Outputs
-- Retenção: permanente
-- =============================================================================
CREATE TABLE ieo_logs (
    id_hash      TEXT   NOT NULL,
    window_start DATE   NOT NULL,
    ieo_score    FLOAT,              -- IEO_final = IEO_sat + δ·z_D
    ieo_linear   FLOAT,             -- 0.5·z_T + 0.3·z_E + 0.2·z_V
    ieo_sat      FLOAT,             -- 1 / (1 + exp(-1·(ieo_linear - 1)))
    z_t          FLOAT,             -- z-score de T
    z_e          FLOAT,             -- z-score de E
    z_v          FLOAT,             -- z-score de V
    z_d          FLOAT,             -- z-score de D
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (id_hash, window_start)
);

-- =============================================================================
-- TABELA: baseline_parameters (seção 22)
-- Camada: Analytical Outputs
-- Política de congelamento e versionamento (C3)
-- Retenção: permanente
-- =============================================================================
CREATE TABLE baseline_parameters (
    id_hash                   TEXT    PRIMARY KEY,
    mean_t                    FLOAT,
    sd_t                      FLOAT,
    mean_e                    FLOAT,
    sd_e                      FLOAT,
    mean_v                    FLOAT,
    sd_v                      FLOAT,
    mean_d                    FLOAT,
    sd_d                      FLOAT,
    baseline_window_count     INTEGER,
    baseline_last_update      TIMESTAMPTZ,
    baseline_version          INTEGER     DEFAULT 1,         -- C3
    baseline_frozen_at        TIMESTAMPTZ,                   -- C3
    baseline_status           TEXT        DEFAULT 'active'
                                  CHECK (baseline_status IN ('active', 'archived')),
    recalibration_justification TEXT                         -- C3
);

-- =============================================================================
-- TABELA: psychometric_data (seção 23)
-- Camada: Analytical Outputs
-- Retenção: ≥ 5 anos pós-publicação (protocolo CEP)
-- =============================================================================
CREATE TABLE psychometric_data (
    record_id   BIGSERIAL                   PRIMARY KEY,
    id_hash     TEXT                        NOT NULL,
    instrument  psychometric_instrument     NOT NULL,        -- C5: ENUM
    score       FLOAT                       NOT NULL
                    CHECK (score >= 0 AND score <= 100),     -- C5: range
    timestamp   DATE                        NOT NULL,
    window_ref  DATE,                                        -- janela quinzenal de referência
    dq_flag     FLOAT                                        -- DQ da janela correspondente
);

CREATE INDEX idx_psychometric_user ON psychometric_data (id_hash);

-- =============================================================================
-- TABELA: critical_load_flags (seção 24)
-- Camada: Analytical Outputs
-- Retenção: ≥ 5 anos pós-publicação (protocolo CEP)
-- =============================================================================
CREATE TABLE critical_load_flags (
    flag_id             BIGSERIAL    PRIMARY KEY,
    id_hash             TEXT         NOT NULL,
    timestamp           DATE         NOT NULL,
    ieo_value           FLOAT,
    psychometric_change FLOAT,
    flag_confirmed      BOOLEAN      DEFAULT FALSE,
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX idx_flags_user ON critical_load_flags (id_hash);

-- =============================================================================
-- TABELA: system_health_logs (seção 25)
-- Camada: Operations
-- Retenção: 90 dias
-- =============================================================================
CREATE TABLE system_health_logs (
    log_id         BIGSERIAL    PRIMARY KEY,
    timestamp      TIMESTAMPTZ  DEFAULT NOW(),
    pipeline_stage TEXT,
    status         TEXT         CHECK (status IN ('ok', 'retry', 'dead_letter', 'error')),
    error_message  TEXT,
    id_hash        TEXT,                              -- usuário afetado (se aplicável)
    window_start   DATE                               -- janela afetada (se aplicável)
);

CREATE INDEX idx_health_timestamp ON system_health_logs (timestamp);

-- Limpeza de logs antigos: executar manualmente ou via job externo
-- DELETE FROM system_health_logs WHERE timestamp < NOW() - INTERVAL '90 days';

-- =============================================================================
-- TABELA: dead_letter_queue (C6 — jobs que falharam 3x)
-- =============================================================================
CREATE TABLE dead_letter_queue (
    dlq_id       BIGSERIAL    PRIMARY KEY,
    id_hash      TEXT,
    window_start DATE,
    payload      JSONB,
    error        TEXT,
    failed_at    TIMESTAMPTZ  DEFAULT NOW()
);

-- =============================================================================
-- ROW LEVEL SECURITY (RLS)
-- Separação lógica: dados operacionais isolados de psicométricos (seção 29)
-- =============================================================================
ALTER TABLE events_raw           ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions             ENABLE ROW LEVEL SECURITY;
ALTER TABLE window_metrics       ENABLE ROW LEVEL SECURITY;
ALTER TABLE ieo_logs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE baseline_parameters  ENABLE ROW LEVEL SECURITY;
ALTER TABLE psychometric_data    ENABLE ROW LEVEL SECURITY;
ALTER TABLE critical_load_flags  ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_health_logs   ENABLE ROW LEVEL SECURITY;
ALTER TABLE dead_letter_queue    ENABLE ROW LEVEL SECURITY;

-- Role: system_operator — acesso total (pipeline interno)
CREATE ROLE supreme_operator;

CREATE POLICY "operator_all_events"     ON events_raw          TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_sessions"   ON sessions            TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_metrics"    ON window_metrics      TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_ieo"        ON ieo_logs            TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_baseline"   ON baseline_parameters TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_psycho"     ON psychometric_data   TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_flags"      ON critical_load_flags TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_health"     ON system_health_logs  TO supreme_operator USING (true) WITH CHECK (true);
CREATE POLICY "operator_all_dlq"        ON dead_letter_queue   TO supreme_operator USING (true) WITH CHECK (true);

-- Role: analytics_user — leitura de outputs analíticos (sem dados operacionais brutos)
CREATE ROLE supreme_analytics;

CREATE POLICY "analytics_read_metrics"  ON window_metrics      FOR SELECT TO supreme_analytics USING (true);
CREATE POLICY "analytics_read_ieo"      ON ieo_logs            FOR SELECT TO supreme_analytics USING (true);
CREATE POLICY "analytics_read_flags"    ON critical_load_flags FOR SELECT TO supreme_analytics USING (true);
-- analytics NÃO acessa: events_raw, sessions, psychometric_data, baseline_parameters

-- =============================================================================
-- COMENTÁRIOS (documentação inline)
-- =============================================================================
COMMENT ON TABLE events_raw          IS 'Eventos operacionais brutos ingeridos do IPED. Append-only. Particionado por mês.';
COMMENT ON TABLE sessions            IS 'Sessões comportamentais derivadas do agrupamento de eventos (gap > 300s = nova sessão).';
COMMENT ON TABLE window_metrics      IS 'Métricas comportamentais agregadas por janela de 14 dias: T, E, V, D.';
COMMENT ON TABLE ieo_logs            IS 'Índice IEO calculado por janela quinzenal. Série temporal principal do estudo.';
COMMENT ON TABLE baseline_parameters IS 'Baseline individual congelado após fase inicial. Versionado. Nunca deletado.';
COMMENT ON TABLE psychometric_data   IS 'Resultados de instrumentos psicométricos (SRQ20, DASS21, OLBI, PANAS_SHORT).';
COMMENT ON TABLE critical_load_flags IS 'Flags de exposição crítica: IEO > 1.5σ E Δpsych ≥ 1σ simultaneamente.';
COMMENT ON TABLE system_health_logs  IS 'Logs operacionais do pipeline. Retenção 90 dias.';
COMMENT ON TABLE dead_letter_queue   IS 'Jobs que falharam 3x consecutivas no pipeline RQ.';

COMMENT ON COLUMN events_raw.event_hash IS 'SHA-256(id_hash, timestamp, event_type, media_type, severity, source_tool). Exclui duration_seconds para deduplicar evento imediato e evento enriquecido posterior.';
COMMENT ON COLUMN baseline_parameters.baseline_status IS 'active = em uso; archived = substituído por nova versão. Nunca deletar.';
COMMENT ON COLUMN window_metrics.dq_score IS 'Data Quality [0,1]. Janelas com DQ < 0.5 não alimentam o modelo inferencial.';
