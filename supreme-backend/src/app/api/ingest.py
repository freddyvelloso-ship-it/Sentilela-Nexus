"""
app.api.ingest
==============
POST /v1/events/ingest — spec SUPREME V4 seção 48.

Fluxo:
    1. Validar schema do payload (Pydantic — rejeita eventos inválidos)
    2. Deduplicar via event_hash (ON CONFLICT DO NOTHING no banco)
    3. Persistir eventos válidos em events_raw
    4. Enfileirar job de pipeline (RQ) para o id_hash do lote
    5. Retornar contagem de eventos armazenados
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...engine.supreme.models import IngestRequest, IngestResponse
from ..db import get_db, insert_events, insert_health_log
from ..queue import enqueue_pipeline
from ..observability import INGEST_EVENTS
from ..security import require_ingest_token

log = logging.getLogger("supreme.ingest")
router = APIRouter()


@router.post(
    "/events/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingestão de eventos operacionais em lote",
    description=(
        "Recebe eventos do agente supreme-watcher ou supreme-proxy. "
        "Eventos com event_hash duplicado são silenciosamente descartados. "
        "Eventos inválidos retornam 422. "
        "Após persistência, enfileira pipeline analítico no RQ."
    ),
)
async def ingest_events(
    payload: IngestRequest,
    db:      Annotated[AsyncSession, Depends(get_db)],
    _:       Annotated[None, Depends(require_ingest_token)],
) -> IngestResponse:
    received = len(payload.events)

    # ── Converter eventos para dicts prontos para o banco ─────────────────
    rows = []
    for event in payload.events:
        rows.append({
            "id_hash":          event.user_identifier,
            "timestamp":        event.timestamp,
            "event_type":       event.event_type.value,
            "media_type":       event.media_type.value,
            "severity":         event.severity,
            "duration_seconds": event.duration_seconds,
            "source_tool":      event.source_tool.value,
            "event_hash":       event.event_hash,
        })

    # ── Persistir com deduplicação ────────────────────────────────────────
    try:
        stored = await insert_events(db, rows)
    except Exception as exc:
        log.error(f"Falha ao persistir eventos: {exc}")
        await _log_health(db, "ingest", "error", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error_code": "DATABASE_ERROR", "message": str(exc)},
        )

    # ── Enfileirar pipeline para cada id_hash único do lote ──────────────
    if stored > 0:
        unique_users = {e.user_identifier for e in payload.events}
        for id_hash in unique_users:
            try:
                enqueue_pipeline(id_hash)
            except Exception as exc:
                log.error(f"Falha ao enfileirar pipeline para {id_hash}: {exc}", exc_info=True)

    INGEST_EVENTS.labels("received").inc(received)
    INGEST_EVENTS.labels("stored").inc(stored)
    log.info(f"Ingestão: recebidos={received} armazenados={stored}")

    return IngestResponse(
        status="success",
        events_received=received,
        events_stored=stored,
    )


async def _log_health(
    db:     AsyncSession,
    stage:  str,
    status: str,
    error:  str,
) -> None:
    try:
        await insert_health_log(db, {
            "pipeline_stage": stage,
            "status":         status,
            "error_message":  error,
            "id_hash":        None,
            "window_start":   None,
        })
    except Exception:
        pass
