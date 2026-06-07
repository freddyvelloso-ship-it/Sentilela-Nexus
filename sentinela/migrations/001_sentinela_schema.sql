-- SENTINELA — Schema principal
-- Recebe dados pseudonimizados do SUPREME V4

-- Usuarios do sistema de pesquisa
CREATE TABLE IF NOT EXISTS sentinela_users (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('master','pibic')),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Janelas IEO recebidas do SUPREME V4
CREATE TABLE IF NOT EXISTS ieo_windows (
    id           BIGSERIAL PRIMARY KEY,
    id_hash      TEXT NOT NULL,
    window_start DATE NOT NULL,
    t_minutes    FLOAT,
    e_events     INT,
    v_volume     FLOAT,
    d_density    FLOAT,
    dq_score     FLOAT,
    ieo_score    FLOAT,
    ieo_linear   FLOAT,
    ieo_sat      FLOAT,
    z_t          FLOAT,
    z_e          FLOAT,
    z_v          FLOAT,
    z_d          FLOAT,
    -- PSI recebido junto com IEO (calculado pelo SUPREME V4)
    psi_score    FLOAT,
    z_dass       FLOAT,
    z_olbi       FLOAT,
    z_srq        FLOAT,
    z_panas_neg  FLOAT,
    convergence_class TEXT,
    received_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (id_hash, window_start)
);

-- Submissoes psicometricas recebidas do SUPREME V4
CREATE TABLE IF NOT EXISTS psico_submissions (
    id          BIGSERIAL PRIMARY KEY,
    id_hash     TEXT NOT NULL,
    instrument  TEXT NOT NULL,
    score       FLOAT NOT NULL,
    window_ref  DATE NOT NULL,
    submitted_at DATE NOT NULL,
    received_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_psico_user ON psico_submissions (id_hash);
CREATE INDEX IF NOT EXISTS idx_psico_inst ON psico_submissions (id_hash, instrument);
-- Evita duplicatas de submissão do mesmo instrumento na mesma janela para o mesmo participante
CREATE UNIQUE INDEX IF NOT EXISTS idx_psico_unique
    ON psico_submissions (id_hash, instrument, window_ref);

-- Red flags calculadas pelo SENTINELA
CREATE TABLE IF NOT EXISTS red_flags (
    id           BIGSERIAL PRIMARY KEY,
    id_hash      TEXT NOT NULL,
    window_start DATE NOT NULL,
    flag_type    TEXT NOT NULL CHECK (flag_type IN ('reatividade','dissonancia','cronicidade')),
    severity     TEXT NOT NULL CHECK (severity IN ('moderado','maior')),
    detail       JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (id_hash, window_start, flag_type)
);

CREATE INDEX IF NOT EXISTS idx_ieo_user    ON ieo_windows (id_hash);
CREATE INDEX IF NOT EXISTS idx_ieo_window  ON ieo_windows (window_start);
CREATE INDEX IF NOT EXISTS idx_rf_user     ON red_flags (id_hash);
CREATE INDEX IF NOT EXISTS idx_rf_type     ON red_flags (flag_type);


-- Configuracoes operacionais imutaveis / bootstrap one-shot
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
