"""
app.queue
=========
Interface com o Redis Queue (RQ).
Enfileira jobs de pipeline analítico.
"""

from __future__ import annotations

import logging

from rq import Queue
import redis

from .config import get_settings

log = logging.getLogger("supreme.queue")
settings = get_settings()


def _get_queue(name: str) -> Queue:
    """Cria conexão Redis e Queue sob demanda (evita falha no import-time)."""
    conn = redis.from_url(settings.redis_url)
    return Queue(name, connection=conn)


def enqueue_pipeline(id_hash: str) -> None:
    """Enfileira o pipeline completo para um id_hash."""
    try:
        q = _get_queue(settings.rq_queue_analytics)
        job = q.enqueue(
            "src.worker.pipeline.run_pipeline_for_user",
            id_hash,
            job_timeout=600,
        )
        log.info(f"Job enfileirado: {job.id} para {id_hash[:16]}...")
    except Exception as exc:
        log.error(f"FALHA ao enfileirar pipeline para {id_hash}: {exc}", exc_info=True)
        raise


def enqueue_dead_letter(id_hash: str, window_start: str, payload: dict, error: str) -> None:
    """Move job para a Dead Letter Queue após max_retries falhas (C6)."""
    try:
        q = _get_queue(settings.rq_queue_dead_letter)
        q.enqueue(
            "src.worker.pipeline.handle_dead_letter",
            {
                "id_hash":      id_hash,
                "window_start": window_start,
                "payload":      payload,
                "error":        error,
            },
            job_timeout=120,
        )
        log.error(
            f"DLQ: id_hash={id_hash[:16]} window={window_start} error={error[:120]}"
        )
    except Exception as exc:
        log.critical(f"FALHA ao enfileirar DLQ para {id_hash}: {exc}", exc_info=True)
