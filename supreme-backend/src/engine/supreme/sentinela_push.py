"""
engine.supreme.sentinela_push
=============================
Envia dados do SUPREME V4 para o SENTINELA em tempo real.
Fire-and-forget: erros sao logados mas nunca interrompem o pipeline principal.

Configuracao (.env):
    SENTINELA_URL     = https://sentinela.meudominio.com
    SENTINELA_API_KEY = <chave compartilhada>
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional

log = logging.getLogger("supreme.sentinela_push")

_URL = os.getenv("SENTINELA_URL", "").rstrip("/")
_KEY = os.getenv("SENTINELA_API_KEY", "")

if not _URL or not _KEY:
    log.warning(
        "SENTINELA push INATIVO — defina SENTINELA_URL e SENTINELA_API_KEY no .env "
        "(IEO e psicométricos NÃO serão enviados ao SENTINELA)"
    )


async def _post_with_backoff(url: str, payload: dict, label: str) -> None:
    import asyncio
    import httpx

    delays = (1, 2, 4)
    last_error = None
    for attempt, delay in enumerate((0, *delays), start=1):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(url, json=payload, headers={"X-API-Key": _KEY})
            if r.status_code in (200, 201):
                log.debug("SENTINELA %s push OK", label)
                return
            last_error = f"{r.status_code} {r.text[:120]}"
        except Exception as exc:
            last_error = str(exc)
        log.warning("SENTINELA %s push tentativa %s falhou: %s", label, attempt, last_error)
    log.error("SENTINELA %s push descartado apos retries: %s", label, last_error)


def _enabled() -> bool:
    ok = bool(_URL and _KEY)
    if not ok:
        log.debug(
            "SENTINELA push desabilitado: SENTINELA_URL=%r SENTINELA_API_KEY=%s",
            _URL or "(vazio)",
            "***" if _KEY else "(vazio)",
        )
    return ok


async def push_ieo(
    id_hash:      str,
    window_start: date,
    t_minutes:    Optional[float],
    e_events:     Optional[int],
    v_volume:     Optional[float],
    d_density:    Optional[float],
    dq_score:     Optional[float],
    ieo_score:    Optional[float],
    ieo_linear:   Optional[float],
    ieo_sat:      Optional[float],
    z_t:          Optional[float],
    z_e:          Optional[float],
    z_v:          Optional[float],
    z_d:          Optional[float],
    # PSI da mesma janela (opcional — enviado junto quando disponivel)
    psi_score:         Optional[float] = None,
    z_dass:            Optional[float] = None,
    z_olbi:            Optional[float] = None,
    z_srq:             Optional[float] = None,
    z_panas_neg:       Optional[float] = None,
    convergence_class: Optional[str]   = None,
) -> None:
    """Envia janela IEO (+ PSI se disponivel) para o SENTINELA."""
    if not _enabled():
        return

    payload = {
        "id_hash":           id_hash,
        "window_start":      window_start.isoformat(),
        "t_minutes":         t_minutes,
        "e_events":          e_events,
        "v_volume":          v_volume,
        "d_density":         d_density,
        "dq_score":          dq_score,
        "ieo_score":         ieo_score,
        "ieo_linear":        ieo_linear,
        "ieo_sat":           ieo_sat,
        "z_t":               z_t,
        "z_e":               z_e,
        "z_v":               z_v,
        "z_d":               z_d,
        "psi_score":         psi_score,
        "z_dass":            z_dass,
        "z_olbi":            z_olbi,
        "z_srq":             z_srq,
        "z_panas_neg":       z_panas_neg,
        "convergence_class": convergence_class,
    }

    await _post_with_backoff(f"{_URL}/api/v1/ingest/ieo", payload, "IEO")


async def push_psychometric(
    id_hash:      str,
    instrument:   str,
    score:        float,
    window_ref:   date,
    submitted_at: date,
) -> None:
    """Envia submissao psicometrica para o SENTINELA."""
    if not _enabled():
        return

    payload = {
        "id_hash":      id_hash,
        "instrument":   instrument,
        "score":        score,
        "window_ref":   window_ref.isoformat(),
        "submitted_at": submitted_at.isoformat(),
    }

    await _post_with_backoff(f"{_URL}/api/v1/ingest/psychometric", payload, "psicometrico")
