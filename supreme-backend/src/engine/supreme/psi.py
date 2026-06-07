"""
engine.supreme.psi
==================
Pipeline PSI — Psychological Suffering Index.

PSI = 0.35·z_DASS + 0.30·z_OLBI + 0.20·z_SRQ + 0.15·z_PANAS_neg

Normalizado ao baseline individual (mesmo protocolo do OEI).
Classificação OEI-PSI: convergence | baseline | residual_burden | divergence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("supreme.psi")

# Pesos do PSI (artigo seção 4.3)
W_DASS = 0.35
W_OLBI = 0.30
W_SRQ = 0.20
W_PANAS_NEG = 0.15

# Threshold para classificação OEI-PSI (em z-scores)
# OEI > 0 = acima do baseline individual → "alto"
# PSI > 0 = acima do baseline individual → "alto"
PSI_THRESHOLD = 0.0
OEI_THRESHOLD = 0.0


@dataclass
class PSIResult:
    psi_score: float
    z_dass: Optional[float]
    z_olbi: Optional[float]
    z_srq: Optional[float]
    z_panas_neg: Optional[float]
    dass_raw: Optional[float]
    olbi_raw: Optional[float]
    srq_raw: Optional[float]
    panas_neg_raw: Optional[float]
    convergence_class: str


def _safe_z(
    value: Optional[float],
    mean: Optional[float],
    sd: Optional[float],
) -> Optional[float]:
    """Z-score com proteção contra sd=0 e dados ausentes."""
    if value is None or mean is None or sd is None:
        return None
    if sd < 1e-9:
        return 0.0
    return (value - mean) / sd


def compute_psi(
    dass_raw: Optional[float],
    olbi_raw: Optional[float],
    srq_raw: Optional[float],
    panas_neg_raw: Optional[float],
    # Baseline individual (médias e SDs calculados nas primeiras janelas)
    mean_dass: Optional[float] = None,
    sd_dass: Optional[float] = None,
    mean_olbi: Optional[float] = None,
    sd_olbi: Optional[float] = None,
    mean_srq: Optional[float] = None,
    sd_srq: Optional[float] = None,
    mean_panas: Optional[float] = None,
    sd_panas: Optional[float] = None,
    # OEI da mesma janela (para classificação convergência/divergência)
    oei_score: Optional[float] = None,
) -> PSIResult:
    """
    Calcula o PSI composto para uma janela de 14 dias.

    Sem baseline congelado, usa z=0 para componentes ausentes
    (primeiro período de calibração — 4-8 janelas).
    """
    z_dass = _safe_z(dass_raw, mean_dass, sd_dass)
    z_olbi = _safe_z(olbi_raw, mean_olbi, sd_olbi)
    z_srq = _safe_z(srq_raw, mean_srq, sd_srq)
    z_panas_neg = _safe_z(panas_neg_raw, mean_panas, sd_panas)

    # Pesos disponíveis (normaliza se algum componente estiver ausente)
    components: list[tuple[float, float]] = []

    if z_dass is not None:
        components.append((W_DASS, z_dass))
    if z_olbi is not None:
        components.append((W_OLBI, z_olbi))
    if z_srq is not None:
        components.append((W_SRQ, z_srq))
    if z_panas_neg is not None:
        components.append((W_PANAS_NEG, z_panas_neg))

    if not components:
        psi_score = 0.0
    else:
        total_weight = sum(weight for weight, _ in components)
        psi_score = sum(weight * z for weight, z in components) / total_weight

    # Classificação OEI × PSI
    convergence_class = _classify(oei_score, psi_score)

    log.debug(
        "PSI calculado | z_dass=%.3f z_olbi=%.3f z_srq=%.3f "
        "z_panas=%.3f → PSI=%.3f [%s]",
        z_dass or 0,
        z_olbi or 0,
        z_srq or 0,
        z_panas_neg or 0,
        psi_score,
        convergence_class,
    )

    return PSIResult(
        psi_score=psi_score,
        z_dass=z_dass,
        z_olbi=z_olbi,
        z_srq=z_srq,
        z_panas_neg=z_panas_neg,
        dass_raw=dass_raw,
        olbi_raw=olbi_raw,
        srq_raw=srq_raw,
        panas_neg_raw=panas_neg_raw,
        convergence_class=convergence_class,
    )


def _classify(oei_score: Optional[float], psi_score: float) -> str:
    """
    Classifica a relação OEI-PSI numa janela (artigo seção 4.4):
      convergence    — OEI alto + PSI alto
      baseline       — OEI baixo + PSI baixo
      residual_burden— OEI baixo + PSI alto
      divergence     — OEI alto + PSI baixo (risco mascarado — sinal prioritário)
    """
    if oei_score is None:
        return "baseline"

    oei_high = oei_score > OEI_THRESHOLD
    psi_high = psi_score > PSI_THRESHOLD

    if oei_high and psi_high:
        return "convergence"
    if not oei_high and not psi_high:
        return "baseline"
    if not oei_high and psi_high:
        return "residual_burden"

    # oei_high and not psi_high
    return "divergence"


# Scores brutos dos instrumentos


def score_panas_short(responses: list[float]) -> dict[str, float]:
    """
    PANAS-short (10 itens, escala 1-5).
    Itens 1-5 = Afeto Positivo, Itens 6-10 = Afeto Negativo.
    """
    assert len(responses) == 10, f"PANAS-short requer 10 itens, recebeu {len(responses)}"
    pa = sum(responses[:5])
    na = sum(responses[5:])
    return {"pa": pa, "na": na, "pa_mean": pa / 5, "na_mean": na / 5}


def score_dass21(responses: list[float]) -> dict[str, float]:
    """
    DASS-21 (21 itens, escala 0-3).
    Depressão: itens 3,5,10,13,16,17,21 (índices 2,4,9,12,15,16,20)
    Ansiedade: itens 2,4,7,9,15,19,20   (índices 1,3,6,8,14,18,19)
    Estresse:  itens 1,6,8,11,12,14,18  (índices 0,5,7,10,11,13,17)
    Score multiplicado por 2 (convenção DASS-21 → DASS-42 equivalente).
    """
    assert len(responses) == 21
    dep_idx = [2, 4, 9, 12, 15, 16, 20]
    anx_idx = [1, 3, 6, 8, 14, 18, 19]
    str_idx = [0, 5, 7, 10, 11, 13, 17]

    dep = sum(responses[i] for i in dep_idx) * 2
    anx = sum(responses[i] for i in anx_idx) * 2
    stress = sum(responses[i] for i in str_idx) * 2
    total = dep + anx + stress

    return {
        "depression": dep,
        "anxiety": anx,
        "stress": stress,
        "total": total,
    }


def score_olbi(responses: list[float]) -> dict[str, float]:
    """
    OLBI (16 itens, escala 1-4).
    Itens reversos (positivos): 2,4,6,9,11,13,15 → invertidos (5 - x).
    Exaustão:       itens 1-8.
    Desengajamento: itens 9-16.
    """
    assert len(responses) == 16

    # Itens reversos (1-based → 0-based): 1,3,5,8,10,12,14
    reverse_idx = {1, 3, 5, 8, 10, 12, 14}
    scored = [5 - response if index in reverse_idx else response for index, response in enumerate(responses)]

    exhaustion = sum(scored[:8])
    disengagement = sum(scored[8:])
    total = exhaustion + disengagement

    return {
        "exhaustion": exhaustion,
        "disengagement": disengagement,
        "total": total,
    }


def score_srq20(responses: list[float]) -> dict[str, float]:
    """
    SRQ-20 (20 itens, 0=não / 1=sim).
    Score total = soma de respostas afirmativas (0-20).
    Ponto de corte sugerido: >= 8 (indicativo de sofrimento psicológico geral).
    """
    assert len(responses) == 20
    total = sum(int(response > 0) for response in responses)
    return {"total": total, "above_cutoff": total >= 8}