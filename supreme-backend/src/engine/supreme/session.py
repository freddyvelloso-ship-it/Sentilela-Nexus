"""
engine.supreme.session
======================
Session Builder — spec SUPREME V4 seção 14.

Algoritmo:
    Eventos ordenados por timestamp.
    delta = timestamp[i] - timestamp[i-1]
    delta ≤ 300s  → mesma sessão
    delta > 300s  → nova sessão

Restrições:
    min_session_duration = 5s   (filtra cliques acidentais)
    max_session_duration = 12h  (filtra sessões esquecidas abertas)
    gap_threshold        = 300s
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .models import EventRecord, SessionRecord

# ── Parâmetros do algoritmo (spec seção 14) ───────────────────────────────
GAP_THRESHOLD_S      = 300       # segundos
MIN_SESSION_DURATION = 5         # segundos
MAX_SESSION_DURATION = 12 * 3600 # segundos (12 horas)


def build_sessions(
    events: Sequence[EventRecord],
    id_hash: str,
) -> list[SessionRecord]:
    """
    Agrupa eventos de um único id_hash em sessões comportamentais.

    Args:
        events:  Sequência de EventRecord já filtrada para um único id_hash,
                 ordenada por timestamp.
        id_hash: Identificador pseudonimizado do analista.

    Returns:
        Lista de SessionRecord válidos (duração dentro dos limites).
    """
    if not events:
        return []

    sorted_events = sorted(events, key=lambda e: e.timestamp)
    sessions: list[SessionRecord] = []

    # Inicializa primeira sessão
    session_start  = sorted_events[0].timestamp
    session_events = [sorted_events[0]]
    prev_ts        = sorted_events[0].timestamp

    def _finalize_session(
        start: datetime,
        end: datetime,
        count: int,
    ) -> SessionRecord | None:
        duration_s = (end - start).total_seconds()
        if duration_s < MIN_SESSION_DURATION:
            return None
        if duration_s > MAX_SESSION_DURATION:
            return None
        return SessionRecord(
            session_id=str(uuid.uuid4()),
            id_hash=id_hash,
            session_start=start,
            session_end=end,
            duration_minutes=round(duration_s / 60.0, 4),
            event_count=count,
        )

    for event in sorted_events[1:]:
        delta_s = (event.timestamp - prev_ts).total_seconds()

        if delta_s > GAP_THRESHOLD_S:
            # Fecha sessão atual
            sess = _finalize_session(
                start=session_start,
                end=prev_ts,
                count=len(session_events),
            )
            if sess:
                sessions.append(sess)
            # Abre nova sessão
            session_start  = event.timestamp
            session_events = [event]
        else:
            session_events.append(event)

        prev_ts = event.timestamp

    # Fecha última sessão
    if session_events:
        sess = _finalize_session(
            start=session_start,
            end=prev_ts,
            count=len(session_events),
        )
        if sess:
            sessions.append(sess)

    return sessions


def group_events_by_user(
    events: Sequence[EventRecord],
) -> dict[str, list[EventRecord]]:
    """Agrupa eventos por id_hash para processamento por analista."""
    grouped: dict[str, list[EventRecord]] = {}
    for event in events:
        grouped.setdefault(event.user_identifier, []).append(event)
    return grouped
