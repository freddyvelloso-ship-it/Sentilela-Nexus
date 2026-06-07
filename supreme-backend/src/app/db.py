"""
app.db
======
Camada de acesso ao banco de dados â€” PostgreSQL via asyncpg + SQLAlchemy async.

Segue o princÃ­pio do Gridform: Ãºnica fronteira de I/O autorizada.
Nenhum outro mÃ³dulo chama o banco diretamente.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

settings = get_settings()

# â”€â”€ Engine SQLAlchemy async â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
    echo=settings.api_debug,
)

AsyncSessionLocal = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency: fornece uma sessÃ£o de banco por request."""
    async with AsyncSessionLocal() as session:
        yield session


# =============================================================================
# Primitivas de eventos_raw
# =============================================================================

async def insert_events(
    db:     AsyncSession,
    events: list[dict],
) -> int:
    """
    Insere eventos em lote com deduplicaÃ§Ã£o por event_hash.
    Usa SELECT-then-INSERT para compatibilidade com tabelas particionadas
    (ON CONFLICT em tabelas particionadas exige constraint na partiÃ§Ã£o destino
    resolvida em tempo de execuÃ§Ã£o, o que nem sempre estÃ¡ disponÃ­vel).
    Retorna o nÃºmero de eventos efetivamente armazenados.
    """
    if not events:
        return 0

    # Coletar hashes jÃ¡ existentes no banco para deduplicar em memÃ³ria.
    # Duplicatas enriquecidas posteriormente (watcher com duration real) atualizam
    # duration_seconds quando trazem valor maior do que o capturado pelo proxy.
    hashes = [e["event_hash"] for e in events]
    existing_result = await db.execute(
        text("SELECT event_hash, COALESCE(duration_seconds, 0) FROM events_raw WHERE event_hash = ANY(:hashes)"),
        {"hashes": hashes},
    )
    existing_durations = {row[0]: float(row[1] or 0) for row in existing_result.fetchall()}

    stored = 0
    for event in events:
        # Serializa operaÃ§Ãµes por event_hash para evitar corrida entre SELECT e INSERT
        # nas partiÃ§Ãµes de events_raw quando dois coletores enviam o mesmo evento.
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:event_hash))"),
            {"event_hash": event["event_hash"]},
        )
        old_duration = existing_durations.get(event["event_hash"])
        if old_duration is not None:
            new_duration = float(event.get("duration_seconds") or 0)
            if new_duration > old_duration:
                await db.execute(
                    text("""
                        UPDATE events_raw
                        SET duration_seconds = :duration_seconds
                        WHERE event_hash = :event_hash
                          AND COALESCE(duration_seconds, 0) < :duration_seconds
                    """),
                    {"event_hash": event["event_hash"], "duration_seconds": new_duration},
                )
            continue
        await db.execute(
            text("""
                INSERT INTO events_raw
                    (id_hash, timestamp, event_type, media_type,
                     severity, duration_seconds, source_tool, event_hash)
                VALUES
                    (:id_hash, :timestamp, :event_type, :media_type,
                     :severity, :duration_seconds, :source_tool, :event_hash)
            """),
            event,
        )
        existing_durations[event["event_hash"]] = float(event.get("duration_seconds") or 0)
        stored += 1

    await db.commit()
    return stored


async def fetch_events_in_window(
    db:           AsyncSession,
    id_hash:      str,
    window_start: date,
    window_end:   date,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT id_hash, timestamp, event_type, media_type,
                   severity, duration_seconds, source_tool
            FROM events_raw
            WHERE id_hash = :id_hash
              AND timestamp >= :window_start
              AND timestamp <  :window_end
            ORDER BY timestamp
        """),
        {"id_hash": id_hash, "window_start": window_start, "window_end": window_end},
    )
    return [dict(row._mapping) for row in result]


# =============================================================================
# Primitivas de sessions
# =============================================================================

async def upsert_sessions(db: AsyncSession, sessions: list[dict]) -> None:
    for sess in sessions:
        await db.execute(
            text("""
                INSERT INTO sessions
                    (session_id, id_hash, session_start, session_end,
                     duration_minutes, event_count)
                VALUES
                    (:session_id, :id_hash, :session_start, :session_end,
                     :duration_minutes, :event_count)
                ON CONFLICT (session_id) DO NOTHING
            """),
            sess,
        )
    await db.commit()


async def fetch_sessions_in_window(
    db:           AsyncSession,
    id_hash:      str,
    window_start: date,
    window_end:   date,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT session_id, id_hash, session_start, session_end,
                   duration_minutes, event_count
            FROM sessions
            WHERE id_hash = :id_hash
              AND session_start < :window_end
              AND session_end   >= :window_start
        """),
        {"id_hash": id_hash, "window_start": window_start, "window_end": window_end},
    )
    return [dict(row._mapping) for row in result]


# =============================================================================
# Primitivas de window_metrics
# =============================================================================

async def upsert_window_metrics(db: AsyncSession, metrics: dict) -> None:
    await db.execute(
        text("""
            INSERT INTO window_metrics
                (id_hash, window_start, t_minutes, e_events, v_volume, d_density, dq_score)
            VALUES
                (:id_hash, :window_start, :t_minutes, :e_events, :v_volume, :d_density, :dq_score)
            ON CONFLICT (id_hash, window_start)
            DO UPDATE SET
                t_minutes    = EXCLUDED.t_minutes,
                e_events     = EXCLUDED.e_events,
                v_volume     = EXCLUDED.v_volume,
                d_density    = EXCLUDED.d_density,
                dq_score     = EXCLUDED.dq_score,
                created_at   = NOW()
        """),
        metrics,
    )
    await db.commit()


async def fetch_window_metrics(
    db:      AsyncSession,
    id_hash: str,
    limit:   int = 50,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT id_hash, window_start, t_minutes, e_events,
                   v_volume, d_density, dq_score
            FROM window_metrics
            WHERE id_hash = :id_hash
            ORDER BY window_start
            LIMIT :limit
        """),
        {"id_hash": id_hash, "limit": limit},
    )
    return [dict(row._mapping) for row in result]


# =============================================================================
# Primitivas de baseline_parameters
# =============================================================================

async def fetch_baseline(db: AsyncSession, id_hash: str) -> Optional[dict]:
    result = await db.execute(
        text("""
            SELECT * FROM baseline_parameters
            WHERE id_hash = :id_hash AND baseline_status = 'active'
            LIMIT 1
        """),
        {"id_hash": id_hash},
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


async def upsert_baseline(db: AsyncSession, baseline: dict) -> None:
    # Normaliza enum instances para string pura antes de passar ao SQLAlchemy.
    # Pydantic v2 model_dump() retorna BaselineStatus.ACTIVE como instÃ¢ncia enum
    # (mesmo sendo str subclass), e o driver asyncpg pode falhar na serializaÃ§Ã£o.
    params = {
        k: (v.value if hasattr(v, "value") else v)
        for k, v in baseline.items()
    }

    # Arquiva o baseline anterior antes de inserir o novo
    await db.execute(
        text("""
            UPDATE baseline_parameters
            SET baseline_status = 'archived'
            WHERE id_hash = :id_hash AND baseline_status = 'active'
        """),
        {"id_hash": params["id_hash"]},
    )
    await db.execute(
        text("""
            INSERT INTO baseline_parameters
                (id_hash, mean_t, sd_t, mean_e, sd_e, mean_v, sd_v, mean_d, sd_d,
                 baseline_window_count, baseline_last_update, baseline_version,
                 baseline_frozen_at, baseline_status)
            VALUES
                (:id_hash, :mean_t, :sd_t, :mean_e, :sd_e, :mean_v, :sd_v, :mean_d, :sd_d,
                 :baseline_window_count, :baseline_last_update, :baseline_version,
                 :baseline_frozen_at, :baseline_status)
            ON CONFLICT (id_hash) DO UPDATE SET
                mean_t                 = EXCLUDED.mean_t,
                sd_t                   = EXCLUDED.sd_t,
                mean_e                 = EXCLUDED.mean_e,
                sd_e                   = EXCLUDED.sd_e,
                mean_v                 = EXCLUDED.mean_v,
                sd_v                   = EXCLUDED.sd_v,
                mean_d                 = EXCLUDED.mean_d,
                sd_d                   = EXCLUDED.sd_d,
                baseline_window_count  = EXCLUDED.baseline_window_count,
                baseline_last_update   = EXCLUDED.baseline_last_update,
                baseline_version       = EXCLUDED.baseline_version,
                baseline_frozen_at     = EXCLUDED.baseline_frozen_at,
                baseline_status        = EXCLUDED.baseline_status
        """),
        params,
    )
    await db.commit()


# =============================================================================
# Primitivas de ieo_logs
# =============================================================================

async def upsert_ieo(db: AsyncSession, ieo: dict) -> None:
    await db.execute(
        text("""
            INSERT INTO ieo_logs
                (id_hash, window_start, ieo_score, ieo_linear, ieo_sat,
                 z_t, z_e, z_v, z_d, algorithm_version, algorithm_parameters)
            VALUES
                (:id_hash, :window_start, :ieo_score, :ieo_linear, :ieo_sat,
                 :z_t, :z_e, :z_v, :z_d, :algorithm_version, cast(:algorithm_parameters as jsonb))
            ON CONFLICT (id_hash, window_start)
            DO UPDATE SET
                ieo_score  = EXCLUDED.ieo_score,
                ieo_linear = EXCLUDED.ieo_linear,
                ieo_sat    = EXCLUDED.ieo_sat,
                z_t        = EXCLUDED.z_t,
                z_e        = EXCLUDED.z_e,
                z_v        = EXCLUDED.z_v,
                z_d        = EXCLUDED.z_d,
                algorithm_version = EXCLUDED.algorithm_version,
                algorithm_parameters = EXCLUDED.algorithm_parameters,
                created_at = NOW()
        """),
        ieo,
    )
    await db.commit()


async def fetch_ieo(
    db:      AsyncSession,
    id_hash: str,
    limit:   int = 50,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT id_hash, window_start, ieo_score, ieo_linear, ieo_sat,
                   z_t, z_e, z_v, z_d, algorithm_version, algorithm_parameters
            FROM ieo_logs
            WHERE id_hash = :id_hash
            ORDER BY window_start
            LIMIT :limit
        """),
        {"id_hash": id_hash, "limit": limit},
    )
    return [dict(row._mapping) for row in result]


# =============================================================================
# Primitivas de critical_load_flags
# =============================================================================

async def insert_flag(db: AsyncSession, flag: dict) -> None:
    await db.execute(
        text("""
            INSERT INTO critical_load_flags
                (id_hash, timestamp, ieo_value, psychometric_change, flag_confirmed)
            VALUES
                (:id_hash, :timestamp, :ieo_value, :psychometric_change, :flag_confirmed)
        """),
        flag,
    )
    await db.commit()


async def fetch_flags(
    db:         AsyncSession,
    start_date: Optional[date] = None,
    end_date:   Optional[date] = None,
    id_hash:    Optional[str]  = None,
) -> list[dict]:
    conditions = ["1=1"]
    params: dict[str, Any] = {}
    if start_date:
        conditions.append("timestamp >= :start_date")
        params["start_date"] = start_date
    if end_date:
        conditions.append("timestamp <= :end_date")
        params["end_date"] = end_date
    if id_hash:
        conditions.append("id_hash = :id_hash")
        params["id_hash"] = id_hash

    result = await db.execute(
        text(f"""
            SELECT id_hash, timestamp, ieo_value, psychometric_change, flag_confirmed
            FROM critical_load_flags
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp DESC
        """),
        params,
    )
    return [dict(row._mapping) for row in result]


# =============================================================================
# Primitivas de system_health_logs
# =============================================================================

async def insert_health_log(db: AsyncSession, log: dict) -> None:
    await db.execute(
        text("""
            INSERT INTO system_health_logs
                (pipeline_stage, status, error_message, id_hash, window_start)
            VALUES
                (:pipeline_stage, :status, :error_message, :id_hash, :window_start)
        """),
        log,
    )
    await db.commit()


# =============================================================================
# Primitivas de dead_letter_queue
# =============================================================================

async def insert_dlq(db: AsyncSession, entry: dict) -> None:
    await db.execute(
        text("""
            INSERT INTO dead_letter_queue (id_hash, window_start, payload, error)
            VALUES (:id_hash, :window_start, cast(:payload as jsonb), :error)
        """),
        {**entry, "payload": json.dumps(entry.get("payload", {}))},
    )
    await db.commit()


async def count_dlq(db: AsyncSession) -> int:
    result = await db.execute(text("SELECT COUNT(*) FROM dead_letter_queue"))
    return result.scalar() or 0


# =============================================================================
# Primitivas psicomÃ©tricas (mÃ³dulo PSI â€” migration 003)
# =============================================================================

_INSTRUMENTS = ("PANAS_SHORT", "DASS21", "OLBI", "SRQ20")


async def ensure_schedule_exists(db: AsyncSession, id_hash: str) -> None:
    """Cria entradas de schedule para todos os instrumentos se ainda nÃ£o existirem.
    Usa NOW() do servidor PostgreSQL para evitar skew de clock Pythonâ†”DB."""
    for instrument in _INSTRUMENTS:
        await db.execute(
            text("""
                INSERT INTO instrument_schedule (id_hash, instrument, next_due, study_week)
                VALUES (:id_hash, :instrument, NOW() - INTERVAL '1 second', 0)
                ON CONFLICT (id_hash, instrument) DO NOTHING
            """),
            {"id_hash": id_hash, "instrument": instrument},
        )
    await db.commit()


async def fetch_schedule(db: AsyncSession, id_hash: str) -> list[dict]:
    """Retorna o schedule completo de instrumentos para um id_hash."""
    result = await db.execute(
        text("""
            SELECT instrument, next_due, study_week
            FROM instrument_schedule
            WHERE id_hash = :id_hash
            ORDER BY instrument
        """),
        {"id_hash": id_hash},
    )
    return [dict(row._mapping) for row in result]


async def fetch_due_instruments(db: AsyncSession, id_hash: str) -> list[str]:
    """Retorna lista de instrumentos cujo next_due <= agora.
    Usa NOW() do servidor PostgreSQL para consistÃªncia com ensure_schedule_exists."""
    result = await db.execute(
        text("""
            SELECT instrument FROM instrument_schedule
            WHERE id_hash = :id_hash AND next_due <= NOW()
            ORDER BY instrument
        """),
        {"id_hash": id_hash},
    )
    return [row[0] for row in result]


async def upsert_schedule(
    db:         AsyncSession,
    id_hash:    str,
    instrument: str,
    next_due:   object,
    study_week: int,
) -> None:
    """Atualiza next_due, last_submitted e study_week de um instrumento."""
    await db.execute(
        text("""
            INSERT INTO instrument_schedule (id_hash, instrument, next_due, study_week, last_submitted)
            VALUES (:id_hash, :instrument, :next_due, :study_week, NOW())
            ON CONFLICT (id_hash, instrument) DO UPDATE SET
                next_due       = EXCLUDED.next_due,
                study_week     = EXCLUDED.study_week,
                last_submitted = NOW()
        """),
        {"id_hash": id_hash, "instrument": instrument,
         "next_due": next_due, "study_week": study_week},
    )
    await db.commit()


async def insert_psychometric_submission(
    db:         AsyncSession,
    id_hash:    str,
    instrument: str,
    score:      float,
    window_ref: object,
    responses:  list,
) -> int:
    """Insere submissÃ£o psicomÃ©trica e retorna o record_id gerado."""
    import json as _json
    from datetime import date
    result = await db.execute(
        text("""
            INSERT INTO psychometric_submissions
                (id_hash, instrument, score, timestamp, window_ref, responses)
            VALUES
                (:id_hash, :instrument, :score, :timestamp, :window_ref, cast(:responses as jsonb))
            RETURNING record_id
        """),
        {
            "id_hash":    id_hash,
            "instrument": instrument,
            "score":      score,
            "timestamp":  date.today(),
            "window_ref": window_ref,
            "responses":  _json.dumps(responses),
        },
    )
    row = result.fetchone()
    await db.commit()
    return row[0] if row else 0


async def fetch_psychometric_history(
    db:      AsyncSession,
    id_hash: str,
    limit:   int = 200,
) -> list[dict]:
    """Retorna histÃ³rico de submissÃµes psicomÃ©tricas, mais recente primeiro."""
    result = await db.execute(
        text("""
            SELECT instrument, score, timestamp, window_ref
            FROM psychometric_submissions
            WHERE id_hash = :id_hash
            ORDER BY timestamp DESC
            LIMIT :limit
        """),
        {"id_hash": id_hash, "limit": limit},
    )
    return [dict(row._mapping) for row in result]


async def fetch_scores_by_instrument(
    db:         AsyncSession,
    id_hash:    str,
    instrument: str,
) -> list[float]:
    """Retorna scores histÃ³ricos de um instrumento, ordem cronolÃ³gica."""
    result = await db.execute(
        text("""
            SELECT score FROM psychometric_submissions
            WHERE id_hash = :id_hash AND instrument = :instrument
            ORDER BY timestamp ASC
        """),
        {"id_hash": id_hash, "instrument": instrument},
    )
    return [row[0] for row in result]


async def fetch_latest_ieo_score(db: AsyncSession, id_hash: str) -> Optional[float]:
    """Retorna o ieo_score mais recente do analista."""
    result = await db.execute(
        text("""
            SELECT ieo_score FROM ieo_logs
            WHERE id_hash = :id_hash
            ORDER BY window_start DESC
            LIMIT 1
        """),
        {"id_hash": id_hash},
    )
    row = result.fetchone()
    return row[0] if row else None


async def upsert_psi(db: AsyncSession, psi: dict) -> None:
    """Insere ou atualiza registro PSI para uma janela."""
    await db.execute(
        text("""
            INSERT INTO psi_scores
                (id_hash, window_start, psi_score, z_dass, z_olbi, z_srq, z_panas_neg,
                 dass_raw, olbi_raw, srq_raw, panas_neg_raw, convergence_class)
            VALUES
                (:id_hash, :window_start, :psi_score, :z_dass, :z_olbi, :z_srq, :z_panas_neg,
                 :dass_raw, :olbi_raw, :srq_raw, :panas_neg_raw, :convergence_class)
            ON CONFLICT (id_hash, window_start) DO UPDATE SET
                psi_score        = EXCLUDED.psi_score,
                z_dass           = EXCLUDED.z_dass,
                z_olbi           = EXCLUDED.z_olbi,
                z_srq            = EXCLUDED.z_srq,
                z_panas_neg      = EXCLUDED.z_panas_neg,
                dass_raw         = EXCLUDED.dass_raw,
                olbi_raw         = EXCLUDED.olbi_raw,
                srq_raw          = EXCLUDED.srq_raw,
                panas_neg_raw    = EXCLUDED.panas_neg_raw,
                convergence_class = EXCLUDED.convergence_class
        """),
        psi,
    )
    await db.commit()

# =============================================================================
# Auditoria LGPD / governanÃ§a de dados
# =============================================================================

async def insert_audit_log(db: AsyncSession, entry: dict) -> None:
    await db.execute(
        text("""
            INSERT INTO audit_log(actor, action, subject_id_hash, resource, metadata)
            VALUES (:actor, :action, :subject_id_hash, :resource, cast(:metadata as jsonb))
        """),
        {**entry, "metadata": json.dumps(entry.get("metadata", {}))},
    )
    await db.commit()


ERASE_DELETE_QUERIES = {
    "events_raw": text("DELETE FROM events_raw WHERE id_hash = :id_hash"),
    "sessions": text("DELETE FROM sessions WHERE id_hash = :id_hash"),
    "window_metrics": text("DELETE FROM window_metrics WHERE id_hash = :id_hash"),
    "ieo_logs": text("DELETE FROM ieo_logs WHERE id_hash = :id_hash"),
    "baseline_parameters": text("DELETE FROM baseline_parameters WHERE id_hash = :id_hash"),
    "psychometric_data": text("DELETE FROM psychometric_data WHERE id_hash = :id_hash"),
    "psychometric_submissions": text("DELETE FROM psychometric_submissions WHERE id_hash = :id_hash"),
    "psychometric_items": text("DELETE FROM psychometric_items WHERE id_hash = :id_hash"),
    "psi_scores": text("DELETE FROM psi_scores WHERE id_hash = :id_hash"),
    "critical_load_flags": text("DELETE FROM critical_load_flags WHERE id_hash = :id_hash"),
    "instrument_schedule": text("DELETE FROM instrument_schedule WHERE id_hash = :id_hash"),
    "dead_letter_queue": text("DELETE FROM dead_letter_queue WHERE id_hash = :id_hash"),
    "subject_consents": text("DELETE FROM subject_consents WHERE id_hash = :id_hash"),
}

async def has_active_consent(db: AsyncSession, id_hash: str) -> bool:
    result = await db.execute(
        text("""
            SELECT status = 'granted'
            FROM subject_consents
            WHERE id_hash = :id_hash
            ORDER BY updated_at DESC
            LIMIT 1
        """),
        {"id_hash": id_hash},
    )
    row = result.fetchone()
    return bool(row and row[0])


async def upsert_consent(db: AsyncSession, id_hash: str, status: str, actor: str = "api") -> None:
    if status not in {"granted", "revoked"}:
        raise ValueError("status deve ser 'granted' ou 'revoked'")
    await db.execute(
        text("""
            INSERT INTO subject_consents (id_hash, status, actor, granted_at, revoked_at, updated_at)
            VALUES (:id_hash, :status, :actor,
                    CASE WHEN :status = 'granted' THEN NOW() ELSE NULL END,
                    CASE WHEN :status = 'revoked' THEN NOW() ELSE NULL END,
                    NOW())
            ON CONFLICT (id_hash) DO UPDATE SET
                status = EXCLUDED.status,
                actor = EXCLUDED.actor,
                granted_at = CASE WHEN EXCLUDED.status = 'granted' THEN NOW() ELSE subject_consents.granted_at END,
                revoked_at = CASE WHEN EXCLUDED.status = 'revoked' THEN NOW() ELSE NULL END,
                updated_at = NOW()
        """),
        {"id_hash": id_hash, "status": status, "actor": actor},
    )
    await insert_audit_log(db, {
        "actor": actor,
        "action": f"consent_{status}",
        "subject_id_hash": id_hash,
        "resource": "subject_consents",
        "metadata": {"status": status},
    })
    await db.commit()


async def erase_subject(db: AsyncSession, id_hash: str, actor: str = "system") -> dict:
    deleted = {}
    await insert_audit_log(db, {
        "actor": actor, "action": "subject_erasure_started",
        "subject_id_hash": id_hash, "resource": "all_subject_tables", "metadata": {}
    })
    for table, query in ERASE_DELETE_QUERIES.items():
        try:
            result = await db.execute(query, {"id_hash": id_hash})
            deleted[table] = result.rowcount
        except Exception as exc:
            deleted[table] = f"error: {exc}"

    # Logs operacionais e auditoria sÃ£o preservados por necessidade de integridade,
    # mas deixam de carregar identificador pseudonimizado reversÃ­vel do titular.
    health = await db.execute(
        text("UPDATE system_health_logs SET id_hash = 'ERASED_' || id_hash WHERE id_hash = :id_hash"),
        {"id_hash": id_hash},
    )
    audit = await db.execute(
        text("UPDATE audit_log SET subject_id_hash = 'ERASED_' || subject_id_hash WHERE subject_id_hash = :id_hash"),
        {"id_hash": id_hash},
    )
    deleted["system_health_logs_anon"] = health.rowcount
    deleted["audit_log_anon"] = audit.rowcount
    await db.commit()
    await insert_audit_log(db, {
        "actor": actor, "action": "subject_erasure_completed",
        "subject_id_hash": "ERASED_" + id_hash, "resource": "all_subject_tables", "metadata": deleted
    })
    return deleted
