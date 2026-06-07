"""
engine.red_flags
================
Calcula red flags por janela conforme spec do projeto de doutorado.

Red Flag de Reatividade: IEO > 1.5 SD + variacao PANAS na mesma janela
Red Flag de Dissonancia:  IEO > 1.5 SD sem elevacao psicometrica correspondente
Red Flag de Cronicidade:  IEO normal + OLBI ou SRQ20 elevados por >= 2 janelas
"""
from __future__ import annotations
from typing import Optional

IEO_THRESHOLD_SD = 1.5   # z-score IEO para disparo de reatividade/dissonancia
CHRONIC_WINDOWS  = 2     # janelas consecutivas para cronicidade
CALIBRATION_MIN  = 4     # minimo de janelas validas para ativar flags


def check_reatividade(
    ieo_z: Optional[float],
    panas_na_current: Optional[float],
    panas_na_prev:    Optional[float],
    panas_pa_current: Optional[float],
    panas_pa_prev:    Optional[float],
) -> Optional[str]:
    """
    Reatividade: IEO > 1.5 SD E (aumento NA ou reducao PA) na mesma janela.
    Retorna 'moderado', 'maior' ou None.
    """
    if ieo_z is None or ieo_z < IEO_THRESHOLD_SD:
        return None

    na_aumentou = (panas_na_current is not None and panas_na_prev is not None
                   and panas_na_current > panas_na_prev)
    pa_reduziu  = (panas_pa_current is not None and panas_pa_prev is not None
                   and panas_pa_current < panas_pa_prev)

    if na_aumentou or pa_reduziu:
        return "maior" if ieo_z > 2.0 else "moderado"
    return None


def check_dissonancia(
    ieo_z:            Optional[float],
    dass_stable:      bool,
    olbi_stable:      bool,
    srq_stable:       bool,
) -> Optional[str]:
    """
    Dissonancia: IEO critico SEM elevacao psicometrica.
    Sinal de risco mascarado — prioridade maxima.
    """
    if ieo_z is None or ieo_z < IEO_THRESHOLD_SD:
        return None
    if dass_stable and olbi_stable and srq_stable:
        return "maior" if ieo_z > 2.0 else "moderado"
    return None


def check_cronicidade(
    ieo_z:        Optional[float],
    olbi_high_streak: int,
    srq_high_streak:  int,
) -> Optional[str]:
    """
    Cronicidade: IEO normal + OLBI ou SRQ elevados por >= 2 janelas consecutivas.
    """
    if ieo_z is not None and abs(ieo_z) > IEO_THRESHOLD_SD:
        return None  # nao e cronicidade, e reatividade
    if olbi_high_streak >= CHRONIC_WINDOWS or srq_high_streak >= CHRONIC_WINDOWS:
        streak = max(olbi_high_streak, srq_high_streak)
        return "maior" if streak >= 3 else "moderado"
    return None
