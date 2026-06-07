"""
sentinela.app.main
==================
FastAPI application entry point.
"""

from __future__ import annotations

import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .middleware import SecurityHeadersMiddleware
from .db import init_db
from .api.auth_router import router as auth_router
from .api.ingest import router as ingest_router
from .api.dashboard import router as dashboard_router
from .api.export import router as export_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("sentinela")

STATIC_DIR = pathlib.Path(__file__).parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_init_db:
        log.warning("AUTO_INIT_DB=true — criando tabelas no startup. Use apenas em desenvolvimento/piloto controlado.")
        await init_db()
    else:
        log.info("AUTO_INIT_DB=false — assumindo migrations aplicadas externamente.")
    yield
    log.info("SENTINELA encerrando.")


app = FastAPI(
    title="SENTINELA",
    description="Dashboard de pesquisa SUPREME V4",
    version="1.0.0",
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Bootstrap-Token"],
)

# Rotas API (registradas ANTES do mount de arquivos estaticos)
app.include_router(auth_router)
app.include_router(ingest_router)
app.include_router(dashboard_router)
app.include_router(export_router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "sentinela"}


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"status": "ok", "message": "SENTINELA API — dashboard nao encontrado"}


# Arquivos estaticos adicionais (css, js, imagens) montados em /static
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
