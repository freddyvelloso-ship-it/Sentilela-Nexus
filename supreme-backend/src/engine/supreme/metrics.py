"""
engine.supreme.metrics
======================
Window Metrics Engine -- spec SUPREME V4 secoes 33-36.

Para cada janela de 14 dias calcula:
    T = soma total de minutos de sessao na janela
    E = total de eventos validos
    V = volume ponderado de exposicao (soma dos pesos W_k por evento)
    D = densidade de eventos: E / T  (eventos/min)
    DQ = Data Quality: proporcao de dias com evento sobre dias esperados
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from .models import EventRecord, SessionRecord, WindowMetrics, event_weight

# -- Parametros da janela (spec secao 33) -------------------------------------
WINDOW_DAYS     = 14
DQ_MIN_REQUIRED = 0.5   # janelas com DQ < 0.5 nao alimentam o modelo


def compute_window_metrics(
    id_hash:      str,
    window_start: date,
    events:       Sequence[EventRecord],
    sessions:     Sequence[SessionRecord],
    expected_days: int = WINDOW_DAYS,
) -> WindowMetrics:
    """
    Calcula T, E, V, D para uma janela de 14 dias.

    Args:
        id_hash:       Identificador pseudonimizado.
        window_start:  Data de inicio da janela (inclusive).
        events:        Eventos do id_hash dentro da janela.
        sessions:      Sessoes do id_hash com sobreposicao na janela.
        expected_days: Numero de dias esperados na janela (para DQ).

    Returns:
        WindowMetrics com todos os campos calculados.
    """
    window_end = window_start + timedelta(days=expected_days)

    # Filtrar eventos dentro da janela
    window_events = [
        e for e in events
        if window_start <= e.timestamp.date() < window_end
    ]

    # Filtrar sessoes com sobreposicao na janela
    window_sessions = [
        s for s in sessions
        if s.session_start.date() < window_end
        and s.session_end.date() >= window_start
    ]

    # -- T: soma de minutos de sessao na janela --------------------------------
    t_minutes = sum(s.duration_minutes for s in window_sessions)

    # -- E: contagem de eventos validos ----------------------------------------
    e_events = len(window_events)

    # -- V: volume ponderado = Sigma W_k (spec secao 34.3) --------------------
    # V = Sigma W_evento = Sigma (COPINE_weight x media_multiplier) por evento.
    # Derivacao da Etapa 3: V = Sigma_sessoes (IEO_window_raw x duration_min)
    #   = Sigma_sessoes (Sigma W_evento / duration_min x duration_min) = Sigma W_evento.
    # A duracao cancela-se algebricamente -- nao ha fator de duracao.
    v_volume = sum(
        event_weight(e.media_type, e.severity)
        for e in window_events
    )

    # -- D: densidade = E / T (eventos/min) ------------------------------------
    d_density = (e_events / t_minutes) if t_minutes > 0 else 0.0

    # -- DQ: Data Quality -------------------------------------------------------
    # Proporcao de dias com pelo menos 1 evento sobre os dias esperados.
    # Dias sem eventos = possivel falha no pipeline de extracao.
    days_with_events = len({e.timestamp.date() for e in window_events})
    dq_score = round(days_with_events / expected_days, 4)

    return WindowMetrics(
        id_hash=id_hash,
        window_start=window_start,
        t_minutes=round(t_minutes, 4),
        e_events=e_events,
        v_volume=round(v_volume, 4),
        d_density=round(d_density, 6),
        dq_score=dq_score,
    )


def generate_windows(
    study_start: date,
    study_end:   date,
    step_days:   int = WINDOW_DAYS,
) -> list[date]:
    """
    Gera sequencia de datas de inicio das janelas quinzenais.

    Args:
        study_start: Inicio do estudo.
        study_end:   Fim do estudo (ou data atual para janela corrente).
        step_days:   Passo da janela (padrao: 14 dias).

    Returns:
        Lista de datas de inicio de cada janela.
    """
    windows = []
    current = study_start
    while current < study_end:
        windows.append(current)
        current += timedelta(days=step_days)
    return windows


def is_valid_for_baseline(metric: WindowMetrics) -> bool:
    """
    Uma janela e valida para compor o baseline se DQ >= 0.5 e T > 0.
    A ausencia de critical_load_flag e verificada externamente pelo caller.
    """
    return metric.dq_score >= DQ_MIN_REQUIRED and metric.t_minutes > 0
