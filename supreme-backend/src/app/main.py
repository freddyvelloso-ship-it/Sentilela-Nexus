"""
app.main
========
FastAPI entrypoint — SUPREME V4 Backend.

Rotas:
    POST /v1/events/ingest          → ingest.py (seção 48)
    GET  /v1/metrics/{id_hash}      → analytics.py (seção 49)
    GET  /v1/ieo/{id_hash}          → analytics.py (seção 50)
    GET  /v1/risk-flags             → analytics.py (seção 51)
    GET  /v1/health                 → analytics.py (seção 52)
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.analytics import router as analytics_router
from .api.ingest import router as ingest_router
from .api.governance import router as governance_router
from .api.psychometric import forms_router, router as psychometric_router
from .config import get_settings
from .middleware import SecurityHeadersMiddleware
from .observability import PrometheusMiddleware, metrics_response
from .security import require_api_token

settings = get_settings()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("supreme.main")


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("SUPREME V4 iniciando...")
    yield
    log.info("SUPREME V4 encerrando.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SUPREME V4 — Backend Analítico",
    description=(
        "Sistema de medição de Intensidade de Exposição Ocupacional (IEO) "
        "para analistas forenses. Integrado ao IPED."
    ),
    version="4.0.0",
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
if settings.enable_metrics:
    app.add_middleware(PrometheusMiddleware)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Em produção, restringir allow_origins ao domínio do painel.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Actor", "X-Forwarded-For"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ingest_router,       prefix="/v1")
app.include_router(analytics_router,    prefix="/v1")
app.include_router(psychometric_router, prefix="/v1")
app.include_router(governance_router, prefix="/v1")
app.include_router(forms_router)   # /forms/{instrument} sem prefixo versão


# ── Root ─────────────────────────────────────────────────────────────────────


@app.get("/health", include_in_schema=False)
async def public_health():
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
async def root():
    return {"service": "SUPREME V4", "version": "4.0.0", "status": "ok"}

@app.get("/metrics", include_in_schema=False)
async def metrics(_: None = Depends(require_api_token)):
    return metrics_response()
