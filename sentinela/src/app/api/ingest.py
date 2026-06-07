"""
api.ingest
==========
Recebe dados do SUPREME V4 via push autenticado por API key.

Fixes aplicados:
  B2: COALESCE em todos os campos IEO — nunca sobrescreve dado existente com NULL.
  B3: Calcula red flags automaticamente após receber janela IEO completa.
  B10: Push PSI-only (ieo_score=None) não cria linha órfã nem sobrescreve IEO.
"""
from __future__ import annotations

import json
import hmac
from datetime import date
from typing import Optional
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from ..config import settings
from ..db import AsyncSession, get_db

log = logging.getLogger("sentinela.ingest")
router = APIRouter(prefix="/api/v1/ingest", tags=["Ingest"])


def _check_api_key(x_api_key: str = Header(...)):
    if not hmac.compare_digest(x_api_key.encode(), settings.supreme_api_key.encode()):
        raise HTTPException(status_code=403, detail="API key invalida")


class IEOPayload(BaseModel):
    id_hash:      str
    window_start: date
    t_minutes:    Optional[float] = None
    e_events:     Optional[int]   = None
    v_volume:     Optional[float] = None
    d_density:    Optional[float] = None
    dq_score:     Optional[float] = None
    ieo_score:    Optional[float] = None
    ieo_linear:   Optional[float] = None
    ieo_sat:      Optional[float] = None
    z_t:          Optional[float] = None
    z_e:          Optional[float] = None
    z_v:          Optional[float] = None
    z_d:          Optional[float] = None
    psi_score:         Optional[float] = None
    z_dass:            Optional[float] = None
    z_olbi:            Optional[float] = None
    z_srq:             Optional[float] = None
    z_panas_neg:       Optional[float] = None
    convergence_class: Optional[str]   = None


class PsicoPayload(BaseModel):
    id_hash:      str
    instrument:   str
    score:        float
    window_ref:   date
    submitted_at: date


# Fix B2: COALESCE em todos os campos IEO — jamais sobrescreve dado real com NULL.
# Antes os campos IEO eram sobrescritos sem COALESCE, apagando valores quando
# push_ieo() era chamado com ieo_score=None após submissão psicométrica.
IEO_FULL_UPSERT_SQL = (
    "INSERT INTO ieo_windows"
    " (id_hash, window_start, t_minutes, e_events, v_volume, d_density,"
    " dq_score, ieo_score, ieo_linear, ieo_sat, z_t, z_e, z_v, z_d,"
    " psi_score, z_dass, z_olbi, z_srq, z_panas_neg, convergence_class)"
    " VALUES"
    " (:id_hash, :window_start, :t_minutes, :e_events, :v_volume, :d_density,"
    " :dq_score, :ieo_score, :ieo_linear, :ieo_sat, :z_t, :z_e, :z_v, :z_d,"
    " :psi_score, :z_dass, :z_olbi, :z_srq, :z_panas_neg, :convergence_class)"
    " ON CONFLICT (id_hash, window_start) DO UPDATE SET"
    " ieo_score    = COALESCE(EXCLUDED.ieo_score,    ieo_windows.ieo_score),"
    " ieo_linear   = COALESCE(EXCLUDED.ieo_linear,   ieo_windows.ieo_linear),"
    " ieo_sat      = COALESCE(EXCLUDED.ieo_sat,      ieo_windows.ieo_sat),"
    " t_minutes    = COALESCE(EXCLUDED.t_minutes,    ieo_windows.t_minutes),"
    " e_events     = COALESCE(EXCLUDED.e_events,     ieo_windows.e_events),"
    " v_volume     = COALESCE(EXCLUDED.v_volume,     ieo_windows.v_volume),"
    " d_density    = COALESCE(EXCLUDED.d_density,    ieo_windows.d_density),"
    " dq_score     = COALESCE(EXCLUDED.dq_score,     ieo_windows.dq_score),"
    " z_t          = COALESCE(EXCLUDED.z_t,          ieo_windows.z_t),"
    " z_e          = COALESCE(EXCLUDED.z_e,          ieo_windows.z_e),"
    " z_v          = COALESCE(EXCLUDED.z_v,          ieo_windows.z_v),"
    " z_d          = COALESCE(EXCLUDED.z_d,          ieo_windows.z_d),"
    " psi_score    = COALESCE(EXCLUDED.psi_score,    ieo_windows.psi_score),"
    " z_dass       = COALESCE(EXCLUDED.z_dass,       ieo_windows.z_dass),"
    " z_olbi       = COALESCE(EXCLUDED.z_olbi,       ieo_windows.z_olbi),"
    " z_srq        = COALESCE(EXCLUDED.z_srq,        ieo_windows.z_srq),"
    " z_panas_neg  = COALESCE(EXCLUDED.z_panas_neg,  ieo_windows.z_panas_neg),"
    " convergence_class = COALESCE(EXCLUDED.convergence_class, ieo_windows.convergence_class)"
)

# Fix B10 (revisado): quando só PSI chegou (ieo_score=None), faz UPSERT apenas
# dos campos PSI. Se linha IEO já existe → atualiza PSI via COALESCE sem tocar
# ieo_score. Se linha ainda não existe → cria com ieo_score=NULL; quando o IEO
# chegar pelo IEO_FULL_UPSERT_SQL os campos IEO são preenchidos sem sobrescrever
# o PSI já salvo. Resolve o caso de PSI submetido antes do pipeline IEO rodar.
PSI_ONLY_UPDATE_SQL = (
    "INSERT INTO ieo_windows"
    " (id_hash, window_start, psi_score, z_dass, z_olbi, z_srq, z_panas_neg, convergence_class)"
    " VALUES"
    " (:id_hash, :window_start, :psi_score, :z_dass, :z_olbi, :z_srq, :z_panas_neg, :convergence_class)"
    " ON CONFLICT (id_hash, window_start) DO UPDATE SET"
    " psi_score        = COALESCE(EXCLUDED.psi_score,        ieo_windows.psi_score),"
    " z_dass           = COALESCE(EXCLUDED.z_dass,           ieo_windows.z_dass),"
    " z_olbi           = COALESCE(EXCLUDED.z_olbi,           ieo_windows.z_olbi),"
    " z_srq            = COALESCE(EXCLUDED.z_srq,            ieo_windows.z_srq),"
    " z_panas_neg      = COALESCE(EXCLUDED.z_panas_neg,      ieo_windows.z_panas_neg),"
    " convergence_class = COALESCE(EXCLUDED.convergence_class, ieo_windows.convergence_class)"
)

PSICO_INSERT_SQL = (
    "INSERT INTO psico_submissions (id_hash, instrument, score, window_ref, submitted_at)"
    " VALUES (:id_hash, :instrument, :score, :window_ref, :submitted_at)"
    " ON CONFLICT (id_hash, instrument, window_ref) DO UPDATE SET"
    " score        = EXCLUDED.score,"
    " submitted_at = EXCLUDED.submitted_at"
)


# Fix B3: motor de red flags chamado após cada ingestão de IEO completo.
# Antes, red_flags.py existia mas nunca era invocado — tabela red_flags vazia.
async def _compute_red_flags(db: AsyncSession, id_hash: str, window_start: date) -> None:
    """
    Calcula reatividade, dissonância e cronicidade para a janela recebida
    e persiste os resultados em red_flags (upsert por tipo).
    """
    from ...engine.red_flags import check_reatividade, check_dissonancia, check_cronicidade

    try:
        # Dados da janela atual
        r = await db.execute(text("""
            SELECT ieo_score, z_panas_neg, z_dass, z_olbi, z_srq
            FROM ieo_windows
            WHERE id_hash = :h AND window_start = :w
        """), {"h": id_hash, "w": window_start})
        row = r.mappings().one_or_none()
        if not row or row["ieo_score"] is None:
            return

        # z-score do IEO relativo ao grupo (normalização cross-sectional)
        # — necessário pois o IEO individual é score absoluto, não z-score
        r2 = await db.execute(text("""
            SELECT AVG(ieo_score) AS mean_ieo, STDDEV(ieo_score) AS sd_ieo
            FROM ieo_windows WHERE ieo_score IS NOT NULL
        """))
        stats = r2.mappings().one_or_none()
        ieo_z: Optional[float] = None
        if stats and stats["sd_ieo"] and float(stats["sd_ieo"]) > 0:
            ieo_z = (row["ieo_score"] - float(stats["mean_ieo"])) / float(stats["sd_ieo"])

        # PANAS NA da janela anterior (para detectar variação)
        r3 = await db.execute(text("""
            SELECT z_panas_neg FROM ieo_windows
            WHERE id_hash = :h AND window_start < :w AND z_panas_neg IS NOT NULL
            ORDER BY window_start DESC LIMIT 1
        """), {"h": id_hash, "w": window_start})
        prev = r3.mappings().one_or_none()
        panas_prev: Optional[float] = prev["z_panas_neg"] if prev else None

        # Streak de OLBI/SRQ elevados consecutivos (para cronicidade)
        r4 = await db.execute(text("""
            SELECT z_olbi, z_srq FROM ieo_windows
            WHERE id_hash = :h AND window_start <= :w
            ORDER BY window_start DESC LIMIT 5
        """), {"h": id_hash, "w": window_start})
        history = list(r4.mappings())

        olbi_streak = 0
        for h in history:
            if h["z_olbi"] is not None and h["z_olbi"] > 1.0:
                olbi_streak += 1
            else:
                break
        srq_streak = 0
        for h in history:
            if h["z_srq"] is not None and h["z_srq"] > 1.0:
                srq_streak += 1
            else:
                break

        z_panas = row["z_panas_neg"]
        z_dass  = row["z_dass"]
        z_olbi  = row["z_olbi"]
        z_srq   = row["z_srq"]
        dass_stable = z_dass is None or z_dass < 1.0
        olbi_stable = z_olbi is None or z_olbi < 1.0
        srq_stable  = z_srq  is None or z_srq  < 1.0

        flags_to_insert = []

        sev = check_reatividade(ieo_z, z_panas, panas_prev, None, None)
        if sev:
            flags_to_insert.append(("reatividade", sev, {
                "ieo_z":       round(ieo_z, 3) if ieo_z is not None else None,
                "z_panas_neg": round(z_panas, 3) if z_panas is not None else None,
            }))

        sev = check_dissonancia(ieo_z, dass_stable, olbi_stable, srq_stable)
        if sev:
            flags_to_insert.append(("dissonancia", sev, {
                "ieo_z": round(ieo_z, 3) if ieo_z is not None else None,
            }))

        sev = check_cronicidade(ieo_z, olbi_streak, srq_streak)
        if sev:
            flags_to_insert.append(("cronicidade", sev, {
                "olbi_streak": olbi_streak,
                "srq_streak":  srq_streak,
            }))

        for flag_type, severity, detail in flags_to_insert:
            await db.execute(text("""
                INSERT INTO red_flags (id_hash, window_start, flag_type, severity, detail)
                VALUES (:id_hash, :window_start, :flag_type, :severity, cast(:detail as jsonb))
                ON CONFLICT (id_hash, window_start, flag_type) DO UPDATE SET
                    severity = EXCLUDED.severity,
                    detail   = EXCLUDED.detail
            """), {
                "id_hash":      id_hash,
                "window_start": window_start,
                "flag_type":    flag_type,
                "severity":     severity,
                "detail":       json.dumps(detail),
            })

        if flags_to_insert:
            log.info("Red flags | id=%.8s window=%s flags=%s",
                     id_hash, window_start, [f[0] for f in flags_to_insert])

    except Exception as exc:
        log.warning("Erro ao calcular red flags | id=%.8s window=%s: %s",
                    id_hash, window_start, exc)


@router.post("/ieo")
async def receive_ieo(
    payload: IEOPayload,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(_check_api_key),
):
    p = payload.model_dump()

    if payload.ieo_score is None:
        # Fix B10: PSI-only — só atualiza linha existente, não cria órfã
        await db.execute(text(PSI_ONLY_UPDATE_SQL), p)
        log.info("PSI-only update | id=%.8s window=%s psi=%s",
                 payload.id_hash, payload.window_start,
                 f"{payload.psi_score:.3f}" if payload.psi_score else "None")
    else:
        # Fix B2: upsert completo com COALESCE em todos os campos
        await db.execute(text(IEO_FULL_UPSERT_SQL), p)
        log.info("IEO recebido | id=%.8s window=%s ieo=%.3f",
                 payload.id_hash, payload.window_start, payload.ieo_score)

    await db.commit()

    # Fix B3: calcular red flags após janela IEO completa.
    # Executa somente quando há IEO real; submissões PSI-only não têm base suficiente.
    if payload.ieo_score is not None:
        await _compute_red_flags(db, payload.id_hash, payload.window_start)
        await db.commit()

    return {"status": "ok", "kind": "ieo", "id_hash": payload.id_hash, "window_start": payload.window_start.isoformat()}


@router.post("/psychometric")
async def receive_psychometric(
    payload: PsicoPayload,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(_check_api_key),
):
    """Recebe uma submissão psicométrica bruta/agregada enviada pelo SUPREME.

    Este endpoint estava previsto pelo push_psychometric() no backend, mas a versão
    auditada terminava o arquivo antes de registrar a rota. Sem esta rota, o
    SENTINELA aceitava IEO mas perdia os envios psicométricos individuais.
    """
    await db.execute(text(PSICO_INSERT_SQL), payload.model_dump())
    await db.commit()
    log.info(
        "Psicometrico recebido | id=%.8s instrument=%s score=%.3f window=%s",
        payload.id_hash,
        payload.instrument,
        payload.score,
        payload.window_ref,
    )
    return {
        "status": "ok",
        "kind": "psychometric",
        "id_hash": payload.id_hash,
        "instrument": payload.instrument,
        "window_ref": payload.window_ref.isoformat(),
    }
