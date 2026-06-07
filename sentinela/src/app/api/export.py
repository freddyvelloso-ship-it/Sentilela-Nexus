"""
sentinela.app.api.export
========================
Exportacao CSV para analise em R.
Inclui IEO, PSI, scores brutos e red flags por janela.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import text

from ..auth import get_current_user
from ..db import AsyncSession, get_db

router = APIRouter(prefix="/api/export", tags=["Export"])


@router.get("/csv", summary="Exportar dados completos para R")
async def export_csv(
    start_date: Optional[date] = Query(None),
    end_date:   Optional[date] = Query(None),
    db:         AsyncSession   = Depends(get_db),
    _:          dict           = Depends(get_current_user),
):
    """
    Exporta todos os dados disponíveis em formato CSV para análise em R.
    Inclui IEO por janela, PSI estimado (quando disponivel), red flags e
    scores psicométricos agregados por janela.

    Disponível para master e pibic (dados ja sao anonimizados via id_hash).
    """
    date_filter = ""
    params: dict = {}
    if start_date:
        date_filter += " AND iw.window_start >= :start_date"
        params["start_date"] = start_date
    if end_date:
        date_filter += " AND iw.window_start <= :end_date"
        params["end_date"] = end_date

    query = text(f"""
        SELECT
            iw.id_hash,
            iw.window_start,
            iw.t_minutes,
            iw.e_events,
            iw.v_volume,
            iw.d_density,
            iw.dq_score,
            iw.ieo_score,
            iw.ieo_linear,
            iw.ieo_sat,
            iw.z_t,
            iw.z_e,
            iw.z_v,
            iw.z_d,
            -- PSI e componentes (do SUPREME V4 se disponivel)
            iw.psi_score,
            iw.z_dass,
            iw.z_olbi,
            iw.z_srq,
            iw.z_panas_neg,
            -- Scores brutos psicometricos mais recentes da janela
            (SELECT score FROM psico_submissions
             WHERE id_hash = iw.id_hash
               AND instrument = 'DASS21'
               AND window_ref = iw.window_start
             ORDER BY submitted_at DESC LIMIT 1) AS dass_raw,
            (SELECT score FROM psico_submissions
             WHERE id_hash = iw.id_hash
               AND instrument = 'OLBI'
               AND window_ref = iw.window_start
             ORDER BY submitted_at DESC LIMIT 1) AS olbi_raw,
            (SELECT score FROM psico_submissions
             WHERE id_hash = iw.id_hash
               AND instrument = 'SRQ20'
               AND window_ref = iw.window_start
             ORDER BY submitted_at DESC LIMIT 1) AS srq_raw,
            (SELECT score FROM psico_submissions
             WHERE id_hash = iw.id_hash
               AND instrument = 'PANAS_SHORT'
               AND window_ref = iw.window_start
             ORDER BY submitted_at DESC LIMIT 1) AS panas_na_raw,
            -- Red flags na janela
            (SELECT string_agg(flag_type, ';')
             FROM red_flags rf
             WHERE rf.id_hash = iw.id_hash
               AND rf.window_start = iw.window_start) AS flags,
            (SELECT string_agg(severity, ';')
             FROM red_flags rf
             WHERE rf.id_hash = iw.id_hash
               AND rf.window_start = iw.window_start) AS flag_severities
        FROM ieo_windows iw
        WHERE 1=1 {date_filter}
        ORDER BY iw.id_hash, iw.window_start
    """)

    result = await db.execute(query, params)
    rows = result.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id_hash", "window_start",
        "t_minutes", "e_events", "v_volume", "d_density", "dq_score",
        "ieo_score", "ieo_linear", "ieo_sat",
        "z_t", "z_e", "z_v", "z_d",
        "psi_score", "z_dass", "z_olbi", "z_srq", "z_panas_neg",
        "dass_raw", "olbi_raw", "srq_raw", "panas_na_raw",
        "flags", "flag_severities",
    ])
    for row in rows:
        writer.writerow(list(row))

    filename = f"sentinela_export_{date.today().isoformat()}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/psychometric-raw", summary="Exportar submissoes psicometricas brutas")
async def export_psychometric_raw(
    instrument: Optional[str] = Query(None, description="DASS21 | OLBI | SRQ20 | PANAS_SHORT"),
    start_date: Optional[date] = Query(None),
    end_date:   Optional[date] = Query(None),
    db:         AsyncSession   = Depends(get_db),
    _:          dict           = Depends(get_current_user),
):
    filters = ""
    params: dict = {}
    if instrument:
        filters += " AND instrument = :instrument"
        params["instrument"] = instrument
    if start_date:
        filters += " AND submitted_at >= :start_date"
        params["start_date"] = start_date
    if end_date:
        filters += " AND submitted_at <= :end_date"
        params["end_date"] = end_date

    query = text(f"""
        SELECT id_hash, instrument, score, window_ref, submitted_at
        FROM psico_submissions
        WHERE 1=1 {filters}
        ORDER BY id_hash, submitted_at
    """)
    result = await db.execute(query, params)
    rows = result.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id_hash", "instrument", "score", "window_ref", "submitted_at"])
    for row in rows:
        writer.writerow(list(row))

    filename = f"sentinela_psico_{date.today().isoformat()}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
