-- =============================================================================
-- SUPREME V4 — Migração 002
-- Adiciona constraint UNIQUE (event_hash, timestamp) em events_raw
-- para suportar ON CONFLICT DO NOTHING em tabela particionada (PG 15+).
--
-- Em tabelas particionadas, UNIQUE deve incluir a chave de partição.
-- A chave de partição de events_raw é: timestamp
-- =============================================================================

-- Adiciona constraint em cada partição existente
-- (PG não permite ALTER TABLE ... ADD CONSTRAINT UNIQUE em partitioned table diretamente;
--  é necessário adicionar em cada partição individualmente OU usar índice único)

-- Abordagem: índice único por partição (mais flexível que constraint)
-- O ON CONFLICT (event_hash, timestamp) funciona com índice UNIQUE.

CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_01 ON events_raw_2026_01 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_02 ON events_raw_2026_02 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_03 ON events_raw_2026_03 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_04 ON events_raw_2026_04 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_05 ON events_raw_2026_05 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_06 ON events_raw_2026_06 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_07 ON events_raw_2026_07 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_08 ON events_raw_2026_08 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_09 ON events_raw_2026_09 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_10 ON events_raw_2026_10 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_11 ON events_raw_2026_11 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2026_12 ON events_raw_2026_12 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2027_01 ON events_raw_2027_01 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2027_02 ON events_raw_2027_02 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2027_03 ON events_raw_2027_03 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2027_04 ON events_raw_2027_04 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2027_05 ON events_raw_2027_05 (event_hash, timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_hash_ts_2027_06 ON events_raw_2027_06 (event_hash, timestamp);
