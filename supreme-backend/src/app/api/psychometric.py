"""
app.api.psychometric
====================
Rotas do modulo psicomtrico.
"""

from __future__ import annotations

import csv
import io
import logging
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, field_validator

from ..security import require_api_token, require_ingest_token
from ..db import (
    AsyncSession,
    ensure_schedule_exists,
    fetch_due_instruments,
    fetch_latest_ieo_score,
    fetch_psychometric_history,
    fetch_schedule,
    fetch_scores_by_instrument,
    get_db,
    insert_psychometric_submission,
    upsert_psi,
    upsert_schedule,
)
from ...engine.supreme.psi import compute_psi
from ...engine.supreme.sentinela_push import push_ieo, push_psychometric

log = logging.getLogger("supreme.psychometric")

router       = APIRouter(dependencies=[Depends(require_api_token)], tags=["Psychometric"])
forms_router = APIRouter(tags=["Forms"])

FORMS_DIR = Path(__file__).parent.parent / "forms"

_SCHEDULE: dict[str, timedelta] = {
    "PANAS_SHORT": timedelta(days=2),
    "DASS21":      timedelta(days=14),
    "OLBI":        timedelta(days=30),
    "SRQ20":       timedelta(days=30),
}


def _rolling_stats(values: list[float]) -> tuple[Optional[float], Optional[float]]:
    n = len(values)
    if n < 4:
        return None, None
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return mean, math.sqrt(variance) if variance > 1e-9 else None


def _next_due(instrument: str, study_week: int = 0) -> datetime:
    delta = _SCHEDULE.get(instrument, timedelta(days=30))
    if instrument == "DASS21" and study_week >= 12:
        delta = timedelta(days=30)
    return datetime.now(tz=timezone.utc) + delta


async def _compute_and_save_psi(db: AsyncSession, id_hash: str, window_ref: date) -> None:
    dass_hist  = await fetch_scores_by_instrument(db, id_hash, "DASS21")
    olbi_hist  = await fetch_scores_by_instrument(db, id_hash, "OLBI")
    srq_hist   = await fetch_scores_by_instrument(db, id_hash, "SRQ20")
    panas_hist = await fetch_scores_by_instrument(db, id_hash, "PANAS_SHORT")

    dass_raw  = dass_hist[-1]  if dass_hist  else None
    olbi_raw  = olbi_hist[-1]  if olbi_hist  else None
    srq_raw   = srq_hist[-1]   if srq_hist   else None
    panas_raw = panas_hist[-1] if panas_hist  else None

    mean_dass,  sd_dass  = _rolling_stats(dass_hist[:-1]  if len(dass_hist)  > 1 else [])
    mean_olbi,  sd_olbi  = _rolling_stats(olbi_hist[:-1]  if len(olbi_hist)  > 1 else [])
    mean_srq,   sd_srq   = _rolling_stats(srq_hist[:-1]   if len(srq_hist)   > 1 else [])
    mean_panas, sd_panas = _rolling_stats(panas_hist[:-1] if len(panas_hist) > 1 else [])

    oei_score = await fetch_latest_ieo_score(db, id_hash)

    result = compute_psi(
        dass_raw=dass_raw, olbi_raw=olbi_raw, srq_raw=srq_raw, panas_neg_raw=panas_raw,
        mean_dass=mean_dass, sd_dass=sd_dass, mean_olbi=mean_olbi, sd_olbi=sd_olbi,
        mean_srq=mean_srq, sd_srq=sd_srq, mean_panas=mean_panas, sd_panas=sd_panas,
        oei_score=oei_score,
    )

    await upsert_psi(db, {
        "id_hash":           id_hash,
        "window_start":      window_ref,
        "psi_score":         result.psi_score,
        "z_dass":            result.z_dass,
        "z_olbi":            result.z_olbi,
        "z_srq":             result.z_srq,
        "z_panas_neg":       result.z_panas_neg,
        "dass_raw":          result.dass_raw,
        "olbi_raw":          result.olbi_raw,
        "srq_raw":           result.srq_raw,
        "panas_neg_raw":     result.panas_neg_raw,
        "convergence_class": result.convergence_class,
    })

    log.info("PSI | id_hash=%.8s window=%s psi=%.3f class=%s",
             id_hash, window_ref, result.psi_score, result.convergence_class)


class SubmitRequest(BaseModel):
    id_hash:    str
    instrument: str
    responses:  list[float]

    @field_validator("instrument")
    @classmethod
    def validate_instrument(cls, v: str) -> str:
        valid = {"PANAS_SHORT", "DASS21", "OLBI", "SRQ20"}
        if v not in valid:
            raise ValueError(f"instrument deve ser um de {valid}")
        return v


@router.get("/schedule/{id_hash}")
async def get_schedule(id_hash: str, db: AsyncSession = Depends(get_db)):
    await ensure_schedule_exists(db, id_hash)
    due      = await fetch_due_instruments(db, id_hash)
    schedule = await fetch_schedule(db, id_hash)
    return {"id_hash": id_hash, "due_now": due, "schedule": schedule}


@forms_router.post("/v1/psychometric/submit")
async def submit_psychometric(body: SubmitRequest, db: AsyncSession = Depends(get_db),
                              _: None = Depends(require_ingest_token)):
    if not body.id_hash:
        raise HTTPException(status_code=400, detail="id_hash e obrigatorio")

    await ensure_schedule_exists(db, body.id_hash)

    from ...engine.supreme.psi import score_dass21, score_olbi, score_panas_short, score_srq20
    try:
        if body.instrument == "PANAS_SHORT":
            score = score_panas_short(body.responses)["na"]
        elif body.instrument == "DASS21":
            score = score_dass21(body.responses)["total"]
        elif body.instrument == "OLBI":
            score = score_olbi(body.responses)["total"]
        elif body.instrument == "SRQ20":
            score = float(score_srq20(body.responses)["total"])
        else:
            raise HTTPException(status_code=400, detail="Instrumento invalido")
    except AssertionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    today = date.today()
    # Alinha window_ref com as janelas reais do estudo (study_start + N*window_days).
    # O cálculo anterior (today - today.day % 14) produzia datas arbitrárias que
    # nunca coincidiam com as janelas do IEO, impedindo o link PSI→ieo_windows.
    from ..config import get_settings as _gs
    _s = _gs()
    _study_start = date.fromisoformat(_s.study_start_date)
    _days = (today - _study_start).days
    _window_num = max(0, _days // _s.window_days)
    window_ref = _study_start + timedelta(days=_window_num * _s.window_days)

    record_id = await insert_psychometric_submission(
        db=db, id_hash=body.id_hash, instrument=body.instrument,
        score=score, window_ref=window_ref, responses=body.responses,
    )

    history    = await fetch_psychometric_history(db, body.id_hash, limit=200)
    study_week = 0
    if history:
        first_ts = min(h["timestamp"] for h in history)
        if first_ts:
            first_date = first_ts.date() if hasattr(first_ts, "date") else first_ts
            study_week = max(0, (today - first_date).days // 7)

    await upsert_schedule(
        db=db, id_hash=body.id_hash, instrument=body.instrument,
        next_due=_next_due(body.instrument, study_week), study_week=study_week,
    )

    log.info("Submissao | id_hash=%.8s instrument=%s score=%.1f record_id=%s",
             body.id_hash, body.instrument, score, record_id)

    # Envia para SENTINELA (fire-and-forget)
    try:
        await push_psychometric(
            id_hash=body.id_hash, instrument=body.instrument,
            score=score, window_ref=window_ref, submitted_at=today,
        )
    except Exception as exc:
        log.warning("SENTINELA push psico falhou: %s", exc)

    psi_result = None
    try:
        await _compute_and_save_psi(db, body.id_hash, window_ref)
        # Busca resultado PSI para incluir no push IEO
        from ..db import fetch_scores_by_instrument
        dass_hist  = await fetch_scores_by_instrument(db, body.id_hash, "DASS21")
        olbi_hist  = await fetch_scores_by_instrument(db, body.id_hash, "OLBI")
        srq_hist   = await fetch_scores_by_instrument(db, body.id_hash, "SRQ20")
        panas_hist = await fetch_scores_by_instrument(db, body.id_hash, "PANAS_SHORT")
        from ...engine.supreme.psi import score_dass21, score_olbi, score_panas_short, score_srq20
        from ..db import fetch_latest_ieo_score
        oei = await fetch_latest_ieo_score(db, body.id_hash)
        mean_dass, sd_dass   = _rolling_stats(dass_hist[:-1]  if len(dass_hist)  > 1 else [])
        mean_olbi, sd_olbi   = _rolling_stats(olbi_hist[:-1]  if len(olbi_hist)  > 1 else [])
        mean_srq,  sd_srq    = _rolling_stats(srq_hist[:-1]   if len(srq_hist)   > 1 else [])
        mean_panas, sd_panas = _rolling_stats(panas_hist[:-1] if len(panas_hist) > 1 else [])
        psi_result = compute_psi(
            dass_raw=dass_hist[-1]  if dass_hist  else None,
            olbi_raw=olbi_hist[-1]  if olbi_hist  else None,
            srq_raw=srq_hist[-1]    if srq_hist   else None,
            panas_neg_raw=panas_hist[-1] if panas_hist else None,
            mean_dass=mean_dass, sd_dass=sd_dass,
            mean_olbi=mean_olbi, sd_olbi=sd_olbi,
            mean_srq=mean_srq,   sd_srq=sd_srq,
            mean_panas=mean_panas, sd_panas=sd_panas,
            oei_score=oei,
        )
    except Exception as exc:
        log.warning("PSI nao calculado: %s", exc)

    # Fix B10: push PSI-only ao SENTINELA apenas se janela IEO já existir.
    # Antes, push_ieo() era chamado com ieo_score=None para todos os casos,
    # criando linhas órfãs no banco do SENTINELA e sobrescrevendo IEO com NULL.
    # Agora: enviamos apenas os campos PSI via push_ieo(); o endpoint do
    # SENTINELA (PSI_ONLY_UPDATE_SQL) só atualiza se a linha já existir.
    if psi_result is not None:
        try:
            await push_ieo(
                id_hash=body.id_hash,
                window_start=window_ref,
                # IEO fields: None — o endpoint do SENTINELA só fará UPDATE
                # se a linha existir, sem criar órfã nem sobrescrever IEO (Fix B2+B10)
                t_minutes=None, e_events=None, v_volume=None,
                d_density=None, dq_score=None, ieo_score=None,
                ieo_linear=None, ieo_sat=None,
                z_t=None, z_e=None, z_v=None, z_d=None,
                # PSI fields preenchidos
                psi_score=psi_result.psi_score,
                z_dass=psi_result.z_dass,
                z_olbi=psi_result.z_olbi,
                z_srq=psi_result.z_srq,
                z_panas_neg=psi_result.z_panas_neg,
                convergence_class=psi_result.convergence_class,
            )
        except Exception as exc:
            log.warning("SENTINELA push PSI falhou: %s", exc)

    return {
        "status":     "ok",
        "record_id":  record_id,
        "instrument": body.instrument,
        "score":      score,
        "window_ref": str(window_ref),
    }


@forms_router.get("/forms/{instrument}", include_in_schema=False)
async def serve_form(instrument: str):
    mapping = {
        "panas":  "panas.html",
        "dass21": "dass21.html",
        "olbi":   "olbi.html",
        "srq20":  "srq20.html",
    }
    filename = mapping.get(instrument.lower())
    if not filename:
        raise HTTPException(status_code=404, detail=f"Formulario '{instrument}' nao encontrado")
    html_path = FORMS_DIR / filename
    if not html_path.exists():
        raise HTTPException(status_code=500, detail=f"Arquivo {filename} nao encontrado")
    return FileResponse(str(html_path), media_type="text/html")


@router.get("/export", summary="Exportacao CSV para R")
async def export_csv(
    start_date: Optional[date] = Query(None),
    end_date:   Optional[date] = Query(None),
    db:         AsyncSession   = Depends(get_db),
):
    from sqlalchemy import text as sql_text

    date_filter = ""
    params: dict = {}
    if start_date:
        date_filter += " AND wm.window_start >= :start_date"
        params["start_date"] = start_date
    if end_date:
        date_filter += " AND wm.window_start <= :end_date"
        params["end_date"] = end_date

    query = sql_text(f"""
        SELECT
            wm.id_hash, wm.window_start,
            wm.t_minutes, wm.e_events, wm.v_volume, wm.d_density, wm.dq_score,
            il.ieo_score, il.ieo_linear, il.ieo_sat, il.z_t, il.z_e, il.z_v, il.z_d,
            ps.psi_score, ps.z_dass, ps.z_olbi, ps.z_srq, ps.z_panas_neg,
            ps.dass_raw, ps.olbi_raw, ps.srq_raw, ps.panas_neg_raw,
            ps.convergence_class
        FROM window_metrics wm
        LEFT JOIN ieo_logs il ON il.id_hash = wm.id_hash AND il.window_start = wm.window_start
        LEFT JOIN psi_scores ps ON ps.id_hash = wm.id_hash AND ps.window_start = wm.window_start
        WHERE 1=1 {date_filter}
        ORDER BY wm.id_hash, wm.window_start
    """)

    result = await db.execute(query, params)
    rows   = result.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id_hash", "window_start",
        "t_minutes", "e_events", "v_volume", "d_density", "dq_score",
        "ieo_score", "ieo_linear", "ieo_sat", "z_t", "z_e", "z_v", "z_d",
        "psi_score", "z_dass", "z_olbi", "z_srq", "z_panas_neg",
        "dass_raw", "olbi_raw", "srq_raw", "panas_neg_raw",
        "convergence_class",
    ])
    for row in rows:
        writer.writerow(list(row))

    filename = f"supreme_export_{date.today().isoformat()}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
