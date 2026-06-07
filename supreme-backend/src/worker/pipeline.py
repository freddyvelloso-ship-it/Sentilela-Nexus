"""
worker.pipeline
===============
RQ worker â€” pipeline analÃ­tico assÃ­ncrono SUPREME V4.

Fluxo por id_hash:
    1. Identificar janelas pendentes (sem mÃ©tricas calculadas)
    2. Buscar eventos da janela no banco
    3. Construir sessÃµes (session.py)
    4. Calcular mÃ©tricas da janela (metrics.py)
    5. Atualizar baseline se elegÃ­vel (ieo.py)
    6. Calcular IEO (ieo.py)
    7. Detectar flags de risco crÃ­tico (risk.py)
    8. Persistir tudo no banco
    9. Em falha: logar â†’ retry 3x â†’ Dead Letter Queue (C6)

Chamado por: src.app.queue.enqueue_pipeline
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from ..app.config import get_settings
from ..app.db import (
    AsyncSessionLocal,
    fetch_baseline,
    fetch_events_in_window,
    has_active_consent,
    fetch_window_metrics,
    insert_dlq,
    insert_flag,
    insert_health_log,
    upsert_baseline,
    upsert_ieo,
    upsert_sessions,
    upsert_window_metrics,
)
from ..engine.supreme.ieo import (
    MAX_BASELINE_WINDOWS,
    MIN_BASELINE_WINDOWS,
    compute_baseline,
    compute_ieo,
)
from ..engine.supreme.metrics import (
    compute_window_metrics,
    generate_windows,
    is_valid_for_baseline,
)
from ..engine.supreme.models import (
    BaselineParameters,
    EventRecord,
    EventType,
    MediaType,
    SourceTool,
    WindowMetrics,
)
from ..engine.supreme.risk import check_critical_load
from ..engine.supreme.sentinela_push import push_ieo as _sentinela_push_ieo
from ..engine.supreme.session import build_sessions

log = logging.getLogger("supreme.worker.pipeline")
settings = get_settings()


# =============================================================================
# Entry point chamado pelo RQ
# =============================================================================

def run_pipeline_for_user(id_hash: str) -> dict:
    """
    Entry point sÃ­ncrono exigido pelo RQ.
    asyncio.run() cria sempre um loop novo â€” seguro no contexto do worker.
    """
    import asyncio

    try:
        return asyncio.run(_run_pipeline_async(id_hash))
    except Exception as exc:
        log.error(f"Pipeline falhou para {id_hash}: {exc}", exc_info=True)
        raise  # RQ captura e trata retry/DLQ via Retry config


async def _run_pipeline_async(id_hash: str) -> dict:
    """Executa o pipeline completo para um id_hash."""
    async with AsyncSessionLocal() as db:
        stats = {
            "id_hash":         id_hash,
            "windows_processed": 0,
            "ieo_computed":    0,
            "flags_raised":    0,
            "errors":          [],
        }

        try:
            if not await has_active_consent(db, id_hash):
                await _log(db, "consent", "error", "consent_revoked_or_missing", id_hash, None)
                stats["errors"].append("consent_revoked_or_missing")
                return stats

            # â”€â”€ 1. Determinar janelas a processar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            study_start = date.fromisoformat(settings.study_start_date)
            today       = date.today()
            windows     = generate_windows(study_start, today, step_days=settings.window_days)

            # Carregar mÃ©tricas jÃ¡ calculadas para evitar reprocessamento
            existing_metrics = await fetch_window_metrics(db, id_hash, limit=500)
            calculated_starts = {r["window_start"] for r in existing_metrics}

            # â”€â”€ 2. Processar cada janela pendente â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # all_valid_metrics: janelas com DQ >= 0.5 AND t_minutes > 0
            #   â†’ usadas para computar baseline (critÃ©rio estrito)
            # all_data_metrics: janelas com e_events > 0
            #   â†’ usadas para computar IEO (critÃ©rio relaxado; inclui janelas
            #     com t_minutes=0 de dados de teste ou eventos sem duraÃ§Ã£o)
            all_valid_metrics: list[WindowMetrics] = []
            all_data_metrics:  list[WindowMetrics] = []

            # Reconstruir mÃ©tricas existentes
            for r in existing_metrics:
                wm = WindowMetrics(
                    id_hash=r["id_hash"],
                    window_start=r["window_start"],
                    t_minutes=r["t_minutes"],
                    e_events=r["e_events"],
                    v_volume=r["v_volume"],
                    d_density=r["d_density"],
                    dq_score=r.get("dq_score", 0.0),
                )
                if wm.e_events > 0:
                    all_data_metrics.append(wm)
                if is_valid_for_baseline(wm):
                    all_valid_metrics.append(wm)

            for window_start in windows:
                window_end = window_start + timedelta(days=settings.window_days)

                # Pular janela futura (sem dados completos)
                if window_end > today:
                    continue

                # Processar apenas janelas novas
                if window_start in calculated_starts:
                    continue

                try:
                    wm = await _process_window(db, id_hash, window_start, window_end)
                    if wm:
                        stats["windows_processed"] += 1
                        if wm.e_events > 0:
                            all_data_metrics.append(wm)
                        if is_valid_for_baseline(wm):
                            all_valid_metrics.append(wm)
                except Exception as exc:
                    err_msg = f"Janela {window_start}: {exc}"
                    log.warning(err_msg)
                    stats["errors"].append(err_msg)
                    await _log(db, "metrics", "error", err_msg, id_hash, window_start)

            # â”€â”€ 3. Atualizar baseline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            baseline = await fetch_baseline(db, id_hash)
            baseline_obj: Optional[BaselineParameters] = (
                BaselineParameters(**baseline) if baseline else None
            )

            # Prefere janelas DQ-vÃ¡lidas para baseline; se nÃ£o houver,
            # usa qualquer janela com dados (e_events > 0) como fallback.
            # Isso garante que dados de teste e janelas sem sessÃµes ainda
            # gerem um baseline funcional.
            metrics_for_baseline = all_valid_metrics if all_valid_metrics else all_data_metrics

            if _should_compute_baseline(baseline_obj, metrics_for_baseline):
                try:
                    baseline_obj = compute_baseline(id_hash, metrics_for_baseline, baseline_obj)
                    await upsert_baseline(db, baseline_obj.model_dump())
                    log.info(f"Baseline atualizado para {id_hash} v{baseline_obj.baseline_version}")
                except Exception as exc:
                    err_msg = f"Baseline: {exc}"
                    log.error(err_msg)
                    stats["errors"].append(err_msg)
                    await _log(db, "baseline", "error", err_msg, id_hash, None)

            # â”€â”€ 4. Calcular IEO para janelas sem IEO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Itera all_data_metrics (e_events > 0), nÃ£o all_valid_metrics,
            # para que janelas com t_minutes=0 tambÃ©m recebam IEO calculado.
            if baseline_obj and baseline_obj.baseline_status == "active":
                existing_ieo_rows = await _fetch_ieo_starts(db, id_hash)

                for wm in all_data_metrics:
                    if wm.window_start in existing_ieo_rows:
                        continue
                    try:
                        ieo = compute_ieo(wm, baseline_obj)
                        ieo_payload = ieo.model_dump()
                        ieo_payload["algorithm_version"] = settings.algorithm_version
                        import json as _json
                        ieo_payload["algorithm_parameters"] = _json.dumps({"weights":{"z_t":0.5,"z_e":0.3,"z_v":0.2,"z_d_delta":0.1},"window_days":settings.window_days})
                        await upsert_ieo(db, ieo_payload)
                        stats["ieo_computed"] += 1

                        # â”€â”€ 5. Verificar risco crÃ­tico â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                        flag = check_critical_load(ieo, baseline_obj, None, None)
                        if flag:
                            await insert_flag(db, flag.model_dump())
                            stats["flags_raised"] += 1
                            log.warning(f"Flag crÃ­tica para {id_hash} janela {wm.window_start}")
                            await _log(db, "risk", "warning",
                                       f"IEO={ieo.ieo_score:.3f} flag_confirmed={flag.flag_confirmed}",
                                       id_hash, wm.window_start)

                    except Exception as exc:
                        err_msg = f"IEO janela {wm.window_start}: {exc}"
                        log.warning(err_msg)
                        stats["errors"].append(err_msg)
                        await _log(db, "ieo", "error", err_msg, id_hash, wm.window_start)
                        continue

                    # â”€â”€ Fix B11: push IEO ao SENTINELA (fora do try/except do IEO) â”€â”€
                    # Separado para que erros de push nÃ£o sejam confundidos com
                    # erros de cÃ¡lculo e para garantir que o push sempre ocorra
                    # apÃ³s persistÃªncia bem-sucedida no banco SUPREME.
                    try:
                        await _sentinela_push_ieo(
                            id_hash=ieo.id_hash,
                            window_start=ieo.window_start,
                            t_minutes=wm.t_minutes,
                            e_events=wm.e_events,
                            v_volume=wm.v_volume,
                            d_density=wm.d_density,
                            dq_score=wm.dq_score,
                            ieo_score=ieo.ieo_score,
                            ieo_linear=ieo.ieo_linear,
                            ieo_sat=ieo.ieo_sat,
                            z_t=ieo.z_t,
                            z_e=ieo.z_e,
                            z_v=ieo.z_v,
                            z_d=ieo.z_d,
                        )
                    except Exception as push_exc:
                        log.warning("SENTINELA IEO push falhou para %s janela %s: %s",
                                    id_hash, wm.window_start, push_exc)

            # â”€â”€ 6. Log de saÃºde â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            await _log(db, "pipeline", "ok",
                       f"windows={stats['windows_processed']} ieo={stats['ieo_computed']} flags={stats['flags_raised']}",
                       id_hash, None)

            return stats

        except Exception as exc:
            log.error(f"Pipeline crÃ­tico para {id_hash}: {exc}", exc_info=True)
            await _log(db, "pipeline", "error", str(exc), id_hash, None)
            raise


# =============================================================================
# Processar uma Ãºnica janela quinzenal
# =============================================================================

async def _process_window(
    db,
    id_hash:      str,
    window_start: date,
    window_end:   date,
) -> Optional[WindowMetrics]:
    """Busca eventos, constrÃ³i sessÃµes e calcula mÃ©tricas da janela."""
    raw_events = await fetch_events_in_window(db, id_hash, window_start, window_end)
    if not raw_events:
        return None

    # Converter dicts para EventRecord
    events = [_dict_to_event(r) for r in raw_events]

    # Construir sessÃµes
    sessions = build_sessions(events, id_hash)
    if sessions:
        session_dicts = [
            {
                "session_id":        s.session_id,
                "id_hash":           s.id_hash,
                "session_start":     s.session_start,
                "session_end":       s.session_end,
                "duration_minutes":  s.duration_minutes,
                "event_count":       s.event_count,
            }
            for s in sessions
        ]
        await upsert_sessions(db, session_dicts)

    # Calcular mÃ©tricas da janela
    wm = compute_window_metrics(id_hash, window_start, events, sessions)
    await upsert_window_metrics(db, {
        "id_hash":      wm.id_hash,
        "window_start": wm.window_start,
        "t_minutes":    wm.t_minutes,
        "e_events":     wm.e_events,
        "v_volume":     wm.v_volume,
        "d_density":    wm.d_density,
        "dq_score":     wm.dq_score,
    })

    return wm


# =============================================================================
# Dead Letter Queue handler â€” chamado pelo RQ apÃ³s max_retries
# =============================================================================

def handle_dead_letter(entry: dict) -> None:
    """
    Persiste entrada na DLQ do banco quando o RQ esgota os retries.
    Chamado pela _q_dead_letter apÃ³s enqueue_dead_letter().
    """
    import asyncio

    async def _persist():
        async with AsyncSessionLocal() as db:
            await insert_dlq(db, entry)
            log.error(
                f"DLQ: id_hash={entry.get('id_hash')} "
                f"window={entry.get('window_start')} "
                f"error={entry.get('error')}"
            )

    asyncio.run(_persist())


# =============================================================================
# Helpers internos
# =============================================================================

def _should_compute_baseline(
    existing: Optional[BaselineParameters],
    valid_metrics: list[WindowMetrics],
) -> bool:
    """Retorna True se o baseline deve ser (re)calculado."""
    n = len(valid_metrics)
    if n < MIN_BASELINE_WINDOWS:
        return False
    if existing is None:
        return True
    # Baseline jÃ¡ existe e estÃ¡ ativo â€” sÃ³ atualiza se ainda nÃ£o foi frozen
    # e ainda nÃ£o atingiu max janelas
    if existing.baseline_status == "active" and existing.baseline_frozen_at is None:
        if existing.baseline_window_count < MAX_BASELINE_WINDOWS:
            return True
    return False


def _dict_to_event(r: dict) -> EventRecord:
    """Converte linha do banco para EventRecord (reconstrÃ³i event_hash)."""
    return EventRecord(
        user_identifier=r["id_hash"],
        timestamp=r["timestamp"] if isinstance(r["timestamp"], datetime)
                  else datetime.fromisoformat(str(r["timestamp"])),
        event_type=EventType(r["event_type"]),
        media_type=MediaType(r["media_type"]),
        severity=r["severity"],
        duration_seconds=r["duration_seconds"],
        source_tool=SourceTool(r["source_tool"]),
    )


async def _fetch_ieo_starts(db, id_hash: str) -> set:
    """Retorna conjunto de window_start que jÃ¡ tÃªm IEO calculado."""
    from ..app.db import fetch_ieo
    rows = await fetch_ieo(db, id_hash, limit=500)
    return {r["window_start"] for r in rows}


async def _log(
    db,
    stage:        str,
    status:       str,
    message:      str,
    id_hash:      Optional[str],
    window_start: Optional[date],
) -> None:
    try:
        await insert_health_log(db, {
            "pipeline_stage": stage,
            "status":         status,
            "error_message":  message if status != "ok" else None,
            "id_hash":        id_hash,
            "window_start":   window_start,
        })
    except Exception:
        pass
