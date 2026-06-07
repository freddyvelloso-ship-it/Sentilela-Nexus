"""
engine.supreme.ieo
==================
IEO Engine — Pipeline Matemático Unificado.
Spec SUPREME V4 seções 39 & 61 (incorporadas).

Pipeline de 5 etapas sequenciais:

    Etapa 1 — Peso por evento (nível de evento)
        W_evento = COPINE_weight × media_multiplier

    Etapa 2 — Agregação por sessão
        IEO_session    = Σ W_evento
        IEO_window_raw = IEO_session / session_duration_minutes

    Etapa 3 — Agregação por janela quinzenal (14 dias)
        T = Σ session_duration_minutes
        E = contagem total de eventos válidos
        V = Σ (IEO_window_raw × session_duration_minutes)
        D = E / T

    Etapa 4 — Padronização por baseline individual
        z_T = (T - mean_T) / sd_T
        z_E = (E - mean_E) / sd_E
        z_V = (V - mean_V) / sd_V
        z_D = (D - mean_D) / sd_D

    Etapa 5 — Combinação linear, saturação e ajuste de densidade
        IEO_linear = 0.5·z_T + 0.3·z_E + 0.2·z_V   [α+β+γ = 1]
        IEO_sat    = 1 / (1 + exp(-1·(IEO_linear - 1)))
        IEO_final  = IEO_sat + 0.1·z_D               [δ ≤ 0.20]

Constantes:
    α = 0.5, β = 0.3, γ = 0.2  (combinação linear)
    k = 1, x0 = 1              (logística)
    δ = 0.1                    (ajuste de densidade)
"""

from __future__ import annotations

import math
from datetime import date

from .models import (
    BaselineParameters,
    IEORecord,
    WindowMetrics,
    ZScores,
    compute_z_scores,
)

# ── Constantes do pipeline IEO (spec seção 39) ────────────────────────────
ALPHA   = 0.5    # peso de z_T na combinação linear
BETA    = 0.3    # peso de z_E
GAMMA   = 0.2    # peso de z_V
DELTA   = 0.1    # coeficiente de ajuste de densidade (≤ 0.20)
K_LOGISTIC = 1.0 # steepness da sigmoide
X0_LOGISTIC = 1.0 # ponto de inflexão da sigmoide

assert abs(ALPHA + BETA + GAMMA - 1.0) < 1e-9, "α + β + γ deve ser = 1"
assert DELTA <= 0.20, "δ deve ser ≤ 0.20"


def ieo_linear(z: ZScores) -> float:
    """
    Etapa 5a — Combinação linear dos z-scores.
    IEO_linear = α·z_T + β·z_E + γ·z_V
    """
    return ALPHA * z.z_t + BETA * z.z_e + GAMMA * z.z_v


def ieo_saturation(linear: float) -> float:
    """
    Etapa 5b — Saturação logística.
    IEO_sat = 1 / (1 + exp(-k·(IEO_linear - x0)))
    Evita crescimento ilimitado em exposição extrema (spec seção 40).
    """
    return 1.0 / (1.0 + math.exp(-K_LOGISTIC * (linear - X0_LOGISTIC)))


def ieo_final(sat: float, z_d: float) -> float:
    """
    Etapa 5c — Ajuste de densidade.
    IEO_final = IEO_sat + δ·z_D
    """
    return sat + DELTA * z_d


def compute_ieo(
    metrics:  WindowMetrics,
    baseline: BaselineParameters,
) -> IEORecord:
    """
    Executa o pipeline IEO completo para uma janela.

    Args:
        metrics:  WindowMetrics já calculadas para a janela.
        baseline: Parâmetros de baseline congelado do analista.

    Returns:
        IEORecord com todos os campos do pipeline (spec seção 42).

    Raises:
        ValueError: Se o baseline não está congelado (status != active).
    """
    if baseline.baseline_status.value != "active":
        raise ValueError(
            f"Baseline do analista {baseline.id_hash} não está ativo "
            f"(status={baseline.baseline_status}). "
            "Não é possível calcular IEO sem baseline congelado."
        )

    # Etapa 4 — Padronização
    z = compute_z_scores(metrics, baseline)

    # Etapa 5 — Combinação, saturação e ajuste
    linear = ieo_linear(z)
    sat    = ieo_saturation(linear)
    final  = ieo_final(sat, z.z_d)

    return IEORecord(
        id_hash=metrics.id_hash,
        window_start=metrics.window_start,
        ieo_score=round(final,  6),
        ieo_linear=round(linear, 6),
        ieo_sat=round(sat,    6),
        z_t=round(z.z_t, 6),
        z_e=round(z.z_e, 6),
        z_v=round(z.z_v, 6),
        z_d=round(z.z_d, 6),
    )


# =============================================================================
# Baseline Engine (spec seção 37)
# =============================================================================

MIN_BASELINE_WINDOWS = 4    # mínimo de janelas válidas (DQ ≥ 0.5)
MAX_BASELINE_WINDOWS = 8    # fase inicial: primeiras 4 a 8 janelas


def compute_baseline(
    id_hash:         str,
    valid_metrics:   list[WindowMetrics],
    previous:        BaselineParameters | None = None,
) -> BaselineParameters:
    """
    Calcula os parâmetros de baseline a partir de janelas válidas.

    Regras (spec seção 37.1):
    - Mínimo 4 janelas com DQ ≥ 0.5
    - Nenhuma janela com critical_load_flag (verificado pelo caller)
    - Calculado exclusivamente na fase inicial

    Args:
        id_hash:       Identificador pseudonimizado.
        valid_metrics: Janelas válidas para o baseline (sem flags, DQ ≥ 0.5).
        previous:      Baseline anterior (para arquivamento, se necessário).

    Returns:
        Novo BaselineParameters com status='active'.

    Raises:
        ValueError: Se não há janelas válidas suficientes.
    """
    if len(valid_metrics) < MIN_BASELINE_WINDOWS:
        raise ValueError(
            f"Baseline requer mínimo {MIN_BASELINE_WINDOWS} janelas válidas. "
            f"Disponíveis: {len(valid_metrics)}."
        )

    # Limita ao máximo da fase inicial
    use = valid_metrics[:MAX_BASELINE_WINDOWS]

    def _mean(values: list[float]) -> float:
        return sum(values) / len(values)

    def _std(values: list[float], mean: float) -> float:
        if len(values) < 2:
            return 0.001  # floor para evitar divisão por zero
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return max(math.sqrt(variance), 0.001)

    ts = [m.t_minutes for m in use]
    es = [float(m.e_events) for m in use]
    vs = [m.v_volume for m in use]
    ds = [m.d_density for m in use]

    mean_t = _mean(ts); sd_t = _std(ts, mean_t)
    mean_e = _mean(es); sd_e = _std(es, mean_e)
    mean_v = _mean(vs); sd_v = _std(vs, mean_v)
    mean_d = _mean(ds); sd_d = _std(ds, mean_d)

    version = 1
    if previous:
        version = (previous.baseline_version or 0) + 1

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    return BaselineParameters(
        id_hash=id_hash,
        mean_t=round(mean_t, 6),
        sd_t=round(sd_t, 6),
        mean_e=round(mean_e, 6),
        sd_e=round(sd_e, 6),
        mean_v=round(mean_v, 6),
        sd_v=round(sd_v, 6),
        mean_d=round(mean_d, 6),
        sd_d=round(sd_d, 6),
        baseline_window_count=len(use),
        baseline_last_update=now,
        baseline_version=version,
        baseline_frozen_at=now,
        baseline_status="active",
    )
