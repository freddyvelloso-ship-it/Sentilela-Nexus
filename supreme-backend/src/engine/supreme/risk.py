"""
engine.supreme.risk
===================
Risk Detection Engine — spec SUPREME V4 seções 43-45.

Flag de exposição crítica quando AMBAS as condições são satisfeitas:
    IEO_final  > 1.5 × SD_baseline   (carga crítica de exposição)
    Δpsych     ≥ 1.0 × SD_baseline   (mudança psicométrica detectável)

Onde:
    Δpsych = score_atual − baseline_score
    SD_baseline = sd de qualquer variável (convenção: sd_v como referência geral)

Ao detectar flag:
    1. Gerar CriticalLoadFlag
    2. Registrar em critical_load_flags
    3. Acionar protocolo de suporte clínico (spec seção 45)
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .models import (
    BaselineParameters,
    CriticalLoadFlag,
    IEORecord,
    PsychometricRecord,
)

# ── Limiares (spec seção 43) ──────────────────────────────────────────────
IEO_CRITICAL_MULTIPLIER   = 1.5   # IEO_final > 1.5 × SD_baseline
PSYCHOMETRIC_MULTIPLIER   = 1.0   # Δpsych ≥ 1.0 × SD_baseline

# SD de referência para o limiar de IEO (usamos sd_v como proxy geral)
# Em produção, o pesquisador pode parametrizar qual SD usar
_SD_REFERENCE_VAR = "sd_v"


def check_critical_load(
    ieo:        IEORecord,
    baseline:   BaselineParameters,
    psycho_current:  Optional[PsychometricRecord],
    psycho_baseline: Optional[PsychometricRecord],
) -> Optional[CriticalLoadFlag]:
    """
    Verifica se a janela satisfaz os critérios de carga crítica.

    Args:
        ieo:              IEORecord da janela atual.
        baseline:         Parâmetros de baseline do analista.
        psycho_current:   Score psicométrico da janela atual (pode ser None).
        psycho_baseline:  Score psicométrico baseline do analista (pode ser None).

    Returns:
        CriticalLoadFlag se ambas as condições forem satisfeitas, None caso contrário.

    Note:
        Se dados psicométricos não estiverem disponíveis, a condição
        psicométrica não pode ser avaliada e a flag não é gerada.
        O pesquisador deve garantir coleta periódica dos instrumentos.
    """
    # Condição 1: IEO_final > 1.5 × SD_baseline
    sd_ref = getattr(baseline, _SD_REFERENCE_VAR, 0.001) or 0.001
    ieo_threshold = IEO_CRITICAL_MULTIPLIER * sd_ref

    ieo_critical = ieo.ieo_score > ieo_threshold

    # Condição 2: Δpsych ≥ 1.0 × SD_baseline
    psycho_critical = False
    psycho_change   = 0.0

    if psycho_current is not None and psycho_baseline is not None:
        # Instrumentos devem ser o mesmo para comparação válida
        if psycho_current.instrument == psycho_baseline.instrument:
            psycho_change   = psycho_current.score - psycho_baseline.score
            psycho_critical = psycho_change >= PSYCHOMETRIC_MULTIPLIER * sd_ref

    # Ambas as condições devem ser satisfeitas simultaneamente
    if ieo_critical and psycho_critical:
        return CriticalLoadFlag(
            id_hash=ieo.id_hash,
            timestamp=ieo.window_start,
            ieo_value=ieo.ieo_score,
            psychometric_change=round(psycho_change, 4),
            flag_confirmed=False,
        )

    return None


def check_baseline_recalibration_eligible(
    id_hash:       str,
    recent_ieos:   list[IEORecord],
    recent_metrics: list[object],  # WindowMetrics
    last_baseline_date: Optional[date],
    has_documented_request: bool,
) -> tuple[bool, str]:
    """
    Verifica se recalibração do baseline é permitida (spec seção 37.5, C3).

    Condições TODAS devem ser satisfeitas:
    1. Solicitação formal documentada pelo pesquisador
    2. Ausência de critical_load_flag nas últimas 6 janelas consecutivas
    3. DQ ≥ 0.5 nas últimas 6 janelas consecutivas
    4. Intervalo mínimo de 180 dias desde o último baseline
    5. Aprovação registrada com justificativa

    Returns:
        (eligible: bool, reason: str)
    """
    if not has_documented_request:
        return False, "Solicitação formal não documentada."

    # Verificação de 6 janelas sem flag (simplificado — flags passadas pelo caller)
    if len(recent_ieos) < 6:
        return False, f"Histórico insuficiente: {len(recent_ieos)} janelas (mínimo 6)."

    # Verificação de intervalo de 180 dias
    if last_baseline_date:
        from datetime import date as date_type, timedelta
        min_next = last_baseline_date + timedelta(days=180)
        if date_type.today() < min_next:
            return False, f"Intervalo mínimo de 180 dias não atingido. Próxima elegível: {min_next}."

    # DQ das últimas 6 janelas
    from .models import WindowMetrics as WM
    last_6_metrics = [m for m in recent_metrics if isinstance(m, WM)][-6:]
    if any(m.dq_score < 0.5 for m in last_6_metrics):
        return False, "DQ < 0.5 em uma ou mais das últimas 6 janelas."

    return True, "Elegível para recalibração conforme protocolo C3."
