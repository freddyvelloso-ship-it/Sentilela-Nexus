"""
engine.supreme.models
=====================
Contratos Pydantic do SUPREME V4.

Todos os modelos são imutáveis (frozen) após construção para garantir
que dados de exposição não sejam alterados silenciosamente no pipeline.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# ENUMS
# =============================================================================

class EventType(str, Enum):
    FILE_OPEN            = "file_open"
    IMAGE_VIEW           = "image_view"
    VIDEO_PLAY           = "video_play"
    CLASSIFICATION_EVENT = "classification_event"


class MediaType(str, Enum):
    IMAGE   = "image"
    VIDEO   = "video"
    PREVIEW = "preview"


class SourceTool(str, Enum):
    IPED       = "iped"
    GRIFFEYE   = "griffeye"
    CELLEBRITE = "cellebrite"


class PsychometricInstrument(str, Enum):
    SRQ20      = "SRQ20"
    DASS21     = "DASS21"
    OLBI       = "OLBI"
    PANAS_SHORT = "PANAS_SHORT"


class BaselineStatus(str, Enum):
    ACTIVE   = "active"
    ARCHIVED = "archived"


class HealthStatus(str, Enum):
    OK          = "ok"
    RETRY       = "retry"
    DEAD_LETTER = "dead_letter"
    ERROR       = "error"


# =============================================================================
# PESOS — Spec seções 9 e 10
# =============================================================================

MEDIA_WEIGHTS: dict[MediaType, float] = {
    MediaType.IMAGE:   1.0,
    MediaType.VIDEO:   1.5,
    MediaType.PREVIEW: 0.5,
}

SEVERITY_WEIGHTS: dict[int, float] = {
    1: 0.5,   # Very low — non erotic / contextual
    2: 0.8,   # Low — nudity / non sexual
    3: 1.0,   # Moderate — explicit sexual context
    4: 1.3,   # High — severe sexual activity
    5: 1.6,   # Extreme — extreme abuse
}


def event_weight(media_type: MediaType, severity: int) -> float:
    """W_k = severity_weight × media_weight (spec seção 34)."""
    return SEVERITY_WEIGHTS[severity] * MEDIA_WEIGHTS[media_type]


# =============================================================================
# EVENTO (contrato de ingestão)
# =============================================================================

class EventRecord(BaseModel, frozen=True):
    """
    Contrato de ingestão de evento operacional.
    Spec seção 7 — Event Data Contract.
    """
    timestamp:        datetime
    event_type:       EventType
    media_type:       MediaType
    severity:         int        = Field(ge=1, le=5)
    duration_seconds: float      = Field(ge=0.0)
    user_identifier:  str        = Field(min_length=1)
    source_tool:      SourceTool = SourceTool.IPED

    # Calculado automaticamente — não enviado pelo cliente
    event_hash: Optional[str] = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if isinstance(v, str):
            v = datetime.fromisoformat(v)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode="after")
    def compute_hash(self) -> EventRecord:
        if self.event_hash is None:
            key = {
                "user_identifier": self.user_identifier,
                "timestamp":       self.timestamp.isoformat(),
                "event_type":      self.event_type.value,
                "media_type":      self.media_type.value,
                "severity":        self.severity,
                "source_tool":     self.source_tool.value,
            }
            h = hashlib.sha256(
                json.dumps(key, sort_keys=True).encode()
            ).hexdigest()
            # Pydantic frozen: usamos model_copy para definir o hash
            object.__setattr__(self, "event_hash", h)
        return self

    def weight(self) -> float:
        return event_weight(self.media_type, self.severity)


class IngestRequest(BaseModel):
    """Payload do endpoint POST /events/ingest."""
    events: list[EventRecord] = Field(min_length=1)


class IngestResponse(BaseModel):
    status:          Literal["success"]
    events_received: int
    events_stored:   int


# =============================================================================
# SESSÃO (spec seção 14)
# =============================================================================

class SessionRecord(BaseModel, frozen=True):
    """
    Sessão comportamental derivada do agrupamento de eventos.
    gap_threshold = 300s; min = 5s; max = 12h.
    """
    session_id:       str
    id_hash:          str
    session_start:    datetime
    session_end:      datetime
    duration_minutes: float
    event_count:      int


# =============================================================================
# MÉTRICAS DE JANELA (spec seções 33-36)
# =============================================================================

class WindowMetrics(BaseModel, frozen=True):
    """
    Métricas comportamentais agregadas por janela de 14 dias.
    T = exposure time (min); E = event count; V = volume; D = density.
    """
    id_hash:      str
    window_start: date
    t_minutes:    float    # Exposure Time
    e_events:     int      # Event Count
    v_volume:     float    # Exposure Volume = Σ W_k × duration
    d_density:    float    # Density = E / T (events/min)
    dq_score:     float    # Data Quality [0, 1]


# =============================================================================
# BASELINE (spec seção 37)
# =============================================================================

class BaselineParameters(BaseModel):
    """
    Parâmetros de baseline individual.
    Congelado após fase inicial (4-8 janelas com DQ ≥ 0.5).
    """
    id_hash:                     str
    mean_t:                      float
    sd_t:                        float
    mean_e:                      float
    sd_e:                        float
    mean_v:                      float
    sd_v:                        float
    mean_d:                      float
    sd_d:                        float
    baseline_window_count:       int
    baseline_last_update:        Optional[datetime] = None
    baseline_version:            int              = 1
    baseline_frozen_at:          Optional[datetime] = None
    baseline_status:             BaselineStatus   = BaselineStatus.ACTIVE
    recalibration_justification: Optional[str]    = None

    def is_frozen(self) -> bool:
        return self.baseline_frozen_at is not None

    def sd_safe(self, var: str) -> float:
        """Retorna SD com floor de 0.001 para evitar divisão por zero."""
        val = getattr(self, f"sd_{var}", 0.0) or 0.0
        return max(val, 0.001)


# =============================================================================
# Z-SCORES (spec seção 38)
# =============================================================================

class ZScores(BaseModel, frozen=True):
    z_t: float
    z_e: float
    z_v: float
    z_d: float


def compute_z_scores(metrics: WindowMetrics, baseline: BaselineParameters) -> ZScores:
    """z_X = (X - mean_X_baseline) / sd_X_baseline (spec seção 38.1)."""
    return ZScores(
        z_t=(metrics.t_minutes - baseline.mean_t) / baseline.sd_safe("t"),
        z_e=(metrics.e_events  - baseline.mean_e) / baseline.sd_safe("e"),
        z_v=(metrics.v_volume  - baseline.mean_v) / baseline.sd_safe("v"),
        z_d=(metrics.d_density - baseline.mean_d) / baseline.sd_safe("d"),
    )


# =============================================================================
# IEO RECORD (spec seções 39 & 42)
# =============================================================================

class IEORecord(BaseModel, frozen=True):
    """
    Resultado do pipeline IEO para uma janela quinzenal.
    Pipeline unificado de 5 etapas (spec seção 39).
    """
    id_hash:      str
    window_start: date
    ieo_score:    float    # IEO_final = IEO_sat + 0.1·z_D
    ieo_linear:   float    # 0.5·z_T + 0.3·z_E + 0.2·z_V
    ieo_sat:      float    # 1 / (1 + exp(-1·(ieo_linear - 1)))
    z_t:          float
    z_e:          float
    z_v:          float
    z_d:          float


# =============================================================================
# PSICOMETRIA (spec seção 23)
# =============================================================================

class PsychometricRecord(BaseModel):
    id_hash:    str
    instrument: PsychometricInstrument
    score:      float = Field(ge=0.0, le=100.0)
    timestamp:  date
    window_ref: Optional[date]  = None
    dq_flag:    Optional[float] = None


# =============================================================================
# RISK FLAG (spec seções 43-45)
# =============================================================================

class CriticalLoadFlag(BaseModel, frozen=True):
    """
    Flag de exposição crítica.
    Condição: IEO_final > 1.5 × SD_baseline E Δpsych ≥ 1.0 × SD_baseline.
    """
    id_hash:             str
    timestamp:           date
    ieo_value:           float
    psychometric_change: float
    flag_confirmed:      bool = False


# =============================================================================
# HEALTH / OBSERVABILIDADE (spec seção 52, C6)
# =============================================================================

class HealthResponse(BaseModel):
    status:                 Literal["ok", "degraded"]
    database:               Literal["connected", "error"]
    queue_analytics_size:   int
    queue_dead_letter_size: int    # alerta se > 0 (C6)
    last_pipeline_run:      Optional[str] = None


class SystemHealthLog(BaseModel):
    pipeline_stage: str
    status:         HealthStatus
    error_message:  Optional[str] = None
    id_hash:        Optional[str] = None
    window_start:   Optional[date] = None


# =============================================================================
# DEAD LETTER QUEUE (C6)
# =============================================================================

class DLQEntry(BaseModel):
    id_hash:      Optional[str] = None
    window_start: Optional[date] = None
    payload:      dict
    error:        str
