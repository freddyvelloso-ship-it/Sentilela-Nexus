"""
engine.supreme.session
======================
Session Builder â€” spec SUPREME V4 seÃ§Ã£o 14.

Algoritmo:
    Eventos ordenados por timestamp.
    delta = timestamp[i] - timestamp[i-1]
    delta â‰¤ 300s  â†’ mesma sessÃ£o
    delta > 300s  â†’ nova sessÃ£o

RestriÃ§Ãµes:
    min_session_duration = 5s   (filtra cliques acidentais)
    max_session_duration = 12h  (filtra sessÃµes esquecidas abertas)
    gap_threshold        = 300s
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from .models import EventRecord, SessionRecord

# â”€â”€ ParÃ¢metros do algoritmo (spec seÃ§Ã£o 14) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
GAP_THRESHOLD_S      = 300       # segundos
MIN_SESSION_DURATION = 5         # segundos
MAX_SESSION_DURATION = 12 * 3600 # segundos (12 horas)


def build_sessions(
    events: Sequence[EventRecord],
    id_hash: str,
) -> list[SessionRecord]:
    """
    Agrupa eventos de um Ãºnico id_hash em sessÃµes comportamentais.

    Args:
        events:  SequÃªncia de EventRecord jÃ¡ filtrada para um Ãºnico id_hash,
                 ordenada por timestamp.
        id_hash: Identificador pseudonimizado do analista.

    Returns:
        Lista de SessionRecord vÃ¡lidos (duraÃ§Ã£o dentro dos limites).
    """
    if not events:
        return []

    sorted_events = sorted(events, key=lambda e: e.timestamp)
    sessions: list[SessionRecord] = []

    # Inicializa primeira sessÃ£o
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
            # Fecha sessÃ£o atual
            sess = _finalize_session(
                start=session_start,
                end=prev_ts,
                count=len(session_events),
            )
            if sess:
                sessions.append(sess)
            # Abre nova sessÃ£o
            session_start  = event.timestamp
            session_events = [event]
        else:
            session_events.append(event)

        prev_ts = event.timestamp

    # Fecha Ãºltima sessÃ£o
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
