"""
app.api.analytics
=================
Endpoints analíticos — spec SUPREME V4 seções 49-52.

GET /v1/metrics/{id_hash}     → WindowMetrics por janela (seção 49)
GET /v1/ieo/{id_hash}         → IEORecord por janela    (seção 50)
GET /v1/risk-flags            → CriticalLoadFlags       (seção 51)
GET /v1/health                → Status do sistema + DLQ (seção 52, C6)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Optional

import redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..security import require_api_token
from ..db import (
    count_dlq,
    fetch_flags,
    fetch_ieo,
    fetch_window_metrics,
    get_db,
)

log = logging.getLogger("supreme.analytics")
router = APIRouter(dependencies=[Depends(require_api_token)])
settings = get_settings()


# =============================================================================
# GET /metrics/{id_hash} — seção 49
# =============================================================================

@router.get(
    "/metrics/{id_hash}",
    summary="Métricas comportamentais por janela quinzenal",
)
async def get_metrics(
    id_hash: str,
    db:      Annotated[AsyncSession, Depends(get_db)],
    limit:   int = Query(default=50, ge=1, le=200),
) -> dict:
    rows = await fetch_window_metrics(db, id_hash, limit=limit)
    return {
        "id_hash": id_hash,
        "windows": [
            {
                "window_start": str(r["window_start"]),
                "T_minutes":    r["t_minutes"],
                "E_events":     r["e_events"],
                "V_volume":     r["v_volume"],
                "D_density":    r["d_density"],
                "dq_score":     r.get("dq_score"),
            }
            for r in rows
        ],
    }


# =============================================================================
# GET /ieo/{id_hash} — seção 50
# =============================================================================

@router.get(
    "/ieo/{id_hash}",
    summary="Índice IEO calculado por janela quinzenal",
)
async def get_ieo(
    id_hash: str,
    db:      Annotated[AsyncSession, Depends(get_db)],
    limit:   int = Query(default=50, ge=1, le=200),
) -> dict:
    rows = await fetch_ieo(db, id_hash, limit=limit)
    return {
        "id_hash": id_hash,
        "windows": [
            {
                "window_start": str(r["window_start"]),
                "IEO_score":    r["ieo_score"],
                "IEO_linear":   r["ieo_linear"],
                "IEO_sat":      r["ieo_sat"],
                "z_T":          r["z_t"],
                "z_E":          r["z_e"],
                "z_V":          r["z_v"],
                "z_D":          r["z_d"],
            }
            for r in rows
        ],
    }


# =============================================================================
# GET /risk-flags — seção 51
# =============================================================================

@router.get(
    "/risk-flags",
    summary="Flags de exposição crítica",
)
async def get_risk_flags(
    db:         Annotated[AsyncSession, Depends(get_db)],
    start_date: Optional[date] = Query(default=None),
    end_date:   Optional[date] = Query(default=None),
    id_hash:    Optional[str]  = Query(default=None),
) -> dict:
    rows = await fetch_flags(db, start_date, end_date, id_hash)
    return {
        "flags": [
            {
                "id_hash":             r["id_hash"],
                "timestamp":           str(r["timestamp"]),
                "IEO_value":           r["ieo_value"],
                "psychometric_change": r["psychometric_change"],
                "flag_confirmed":      r["flag_confirmed"],
            }
            for r in rows
        ],
    }


# =============================================================================
# GET /health — seção 52 (C6)
# =============================================================================

@router.get(
    "/health",
    summary="Status do sistema e filas (inclui Dead Letter Queue)",
)
async def get_health(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    # ── Verificar banco ───────────────────────────────────────────────────
    db_status = "connected"
    last_run  = None
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT MAX(timestamp) FROM system_health_logs WHERE status='ok'")
        )
        row = result.fetchone()
        if row and row[0]:
            last_run = row[0].isoformat()
    except Exception as exc:
        log.error(f"Health check DB error: {exc}")
        db_status = "error"

    # ── Verificar filas RQ via Redis ──────────────────────────────────────
    analytics_size  = 0
    dead_letter_size = 0
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True)
        analytics_size   = r.llen(f"rq:queue:{settings.rq_queue_analytics}")
        dead_letter_size = r.llen(f"rq:queue:{settings.rq_queue_dead_letter}")
    except Exception as exc:
        log.warning(f"Health check Redis error: {exc}")

    # Fallback: contar DLQ no banco se Redis indisponível
    if dead_letter_size == 0:
        try:
            dead_letter_size = await count_dlq(db)
        except Exception:
            pass

    overall = "ok" if db_status == "connected" else "degraded"

    return {
        "status":                  overall,
        "database":                db_status,
        "queue_analytics_size":    analytics_size,
        "queue_dead_letter_size":  dead_letter_size,  # alerta se > 0 (C6)
        "last_pipeline_run":       last_run,
    }
