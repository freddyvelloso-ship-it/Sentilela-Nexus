"""
supreme-proxy.py
================
Proxy HTTP transparente entre o perito e a Web API do IPED.

Função dupla:
  1. Intercepta requisições à API do IPED e gera eventos SUPREME
     com base no endpoint chamado (image_view, video_play, file_open).
  2. Lê o arquivo de auditoria gerado pelo SupremeAuditLogger (patch Java)
     para obter duration_seconds preciso e enriquecer os eventos.

Fluxo:
  Perito → supreme-proxy (porta 8081)
         → IPED Web API (porta 1234)
         → resposta enriquecida com metadados SUPREME

Configuração (variáveis de ambiente):
  IPED_API_URL          URL base da Web API do IPED  (default: http://localhost:1234)
  PROXY_PORT            Porta onde o proxy escuta    (default: 8081)
  SUPREME_AUDIT_LOG     Arquivo NDJSON do patch Java (default: ~/supreme_audit.ndjson)
  SUPREME_API_URL       URL do backend SUPREME       (default: http://localhost:8000)
  SUPREME_API_TOKEN     JWT para autenticação SUPREME
  SUPREME_USER_ID       ID funcional do perito (fallback se não vier do Java)
  SUPREME_SALT          Salt para pseudonimização (manter offline em produção)

Uso:
  pip install httpx fastapi uvicorn
  python proxy.py
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

# ── Configuração ───────────────────────────────────────────────────────────

IPED_API_URL    = os.environ.get("IPED_API_URL",       "http://localhost:1234")
PROXY_PORT      = int(os.environ.get("PROXY_PORT",     "8081"))
SUPREME_API_URL = os.environ.get("SUPREME_API_URL",    "http://localhost:8000")
SUPREME_TOKEN   = os.environ.get("SUPREME_API_TOKEN",  "")
USER_ID_FALLBACK= os.environ.get("SUPREME_USER_ID",    "unknown")
SALT            = os.environ.get("SUPREME_SALT",       "")
AUDIT_LOG_PATH  = Path(os.environ.get(
    "SUPREME_AUDIT_LOG",
    Path.home() / "supreme_audit.ndjson"
))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [proxy] %(levelname)s %(message)s")
log = logging.getLogger("supreme-proxy")

app = FastAPI(title="SUPREME Proxy", docs_url=None)

# ── Cache de duração (lido do arquivo do patch Java) ───────────────────────

class DurationCache:
    """
    Lê o arquivo NDJSON gerado pelo SupremeAuditLogger e mantém
    um índice (itemId → duration_seconds calculado).
    Atualiza de forma incremental a cada requisição relevante.
    """
    def __init__(self, path: Path):
        self.path       = path
        self.offset     = 0                    # bytes já lidos
        self.open_times: dict[str, dict] = {}  # itemId → {open_ts, ...}
        self.durations:  dict[str, float] = {} # itemId → duration_seconds

    def refresh(self):
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                f.seek(self.offset)
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self._process_entry(entry)
                    except json.JSONDecodeError:
                        pass
                self.offset = f.tell()
        except OSError:
            pass

    def _process_entry(self, entry: dict):
        item_id = str(entry.get("itemId", ""))
        event   = entry.get("event", "")
        if event == "open":
            self.open_times[item_id] = entry
        elif event == "close":
            open_entry = self.open_times.pop(item_id, None)
            if open_entry:
                open_ts  = int(open_entry.get("openTs",  0))
                close_ts = int(entry.get("closeTs", 0))
                if close_ts > open_ts > 0:
                    duration = (close_ts - open_ts) / 1000.0
                    self.durations[item_id] = round(duration, 2)

    def get_duration(self, item_id: str) -> Optional[float]:
        self.refresh()
        return self.durations.get(item_id)

    def get_open_entry(self, item_id: str) -> Optional[dict]:
        self.refresh()
        return self.open_times.get(item_id)


duration_cache = DurationCache(AUDIT_LOG_PATH)

# ── Pseudonimização ────────────────────────────────────────────────────────

def pseudonymize(user_id: str) -> str:
    """SHA-256(user_id + SALT) → hex. Nunca armazena o user_id real."""
    return hashlib.sha256(f"{user_id}{SALT}".encode()).hexdigest()


# ── Mapeamento de endpoints → event_type ──────────────────────────────────

def classify_request(path: str, media_type: str) -> Optional[str]:
    """
    Deriva event_type a partir do endpoint da API do IPED e do mediaType do item.

    /sources/{id}/docs/{id}/content  → file_open | image_view | video_play
    /sources/{id}/docs/{id}/thumb    → image_view (preview)
    /sources/{id}/docs/{id}/text     → file_open (leitura de texto)
    POST /bookmarks/...              → classification_event
    """
    lower = path.lower()
    if "/thumb" in lower:
        return "image_view"          # thumbnail = visualização de imagem/preview
    if "/text" in lower:
        return "file_open"
    if "/content" in lower:
        if media_type and "video" in media_type:
            return "video_play"
        if media_type and "image" in media_type:
            return "image_view"
        return "file_open"
    return None


def classify_media_type(iped_content_type: str) -> str:
    """Normaliza tipo MIME do IPED para os 3 tipos SUPREME."""
    if not iped_content_type:
        return "preview"
    ct = iped_content_type.lower()
    if "video" in ct:
        return "video"
    if "image" in ct:
        return "image"
    return "preview"


def severity_from_nudity(nudity_class: Optional[str],
                          ai_csam: Optional[str],
                          ai_porn: Optional[str]) -> int:
    """
    Mapeia campos do IPED para a escala COPINE do SUPREME (1-5).

    nudityClass (1-5) do IPED → severity (1-5) direto.
    ai:csam > 60  → severity 5
    ai:likelyCsam > 60 → severity 4
    ai:porn > 60  → severity 3
    fallback      → 1
    """
    try:
        if ai_csam and float(ai_csam) >= 60:
            return 5
    except ValueError:
        pass
    try:
        if ai_porn and float(ai_porn) >= 60:
            return 3
    except ValueError:
        pass
    try:
        if nudity_class:
            nc = int(nudity_class)
            return max(1, min(5, nc))
    except ValueError:
        pass
    return 1


# ── Extração de itemId e sourceId da URL ──────────────────────────────────

def parse_iped_url(path: str) -> tuple[Optional[str], Optional[str]]:
    """
    /sources/{sourceId}/docs/{itemId}/...
    Retorna (source_id, item_id) ou (None, None).
    """
    parts = path.strip("/").split("/")
    try:
        src_idx  = parts.index("sources")
        docs_idx = parts.index("docs")
        return parts[src_idx + 1], parts[docs_idx + 1]
    except (ValueError, IndexError):
        return None, None


# ── Ingestão de evento no SUPREME ─────────────────────────────────────────

async def ingest_event(event: dict):
    """POST assíncrono para o SUPREME /events/ingest. Não bloqueia o proxy."""
    headers = {
        "Authorization": f"Bearer {SUPREME_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {"events": [event]}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{SUPREME_API_URL}/v1/events/ingest",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                log.warning(f"SUPREME ingest retornou {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log.error(f"Falha ao ingerir evento no SUPREME: {e}")


# ── Proxy principal ────────────────────────────────────────────────────────

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    """
    Encaminha todas as requisições ao IPED, intercepta as relevantes
    para geração de eventos SUPREME.
    """
    # ── 1. Encaminhar ao IPED ──────────────────────────────────────────────
    target_url = f"{IPED_API_URL}/{path}"
    if request.query_params:
        target_url += "?" + str(request.query_params)

    body = await request.body()

    async with httpx.AsyncClient(timeout=30) as client:
        iped_resp = await client.request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers.items()
                     if k.lower() not in ("host", "content-length")},
            content=body,
        )

    # ── 2. Verificar se é uma requisição de item auditável ─────────────────
    request_path = "/" + path
    source_id, item_id = parse_iped_url(request_path)

    is_doc_request    = item_id is not None
    is_bookmark_post  = request.method == "POST" and "bookmarks" in request_path
    is_content_access = any(x in request_path for x in ["/content", "/thumb", "/text"])

    # ── 3. Obter metadata do item para enriquecer o evento ─────────────────
    if is_doc_request and (is_content_access or is_bookmark_post):
        asyncio.ensure_future(
            _build_and_ingest(
                request_path=request_path,
                request_method=request.method,
                source_id=source_id,
                item_id=item_id,
                iped_resp_body=iped_resp.content,
                bookmark_body=body if is_bookmark_post else None,
            )
        )

    # ── 4. Devolver resposta original ao perito ────────────────────────────
    return Response(
        content=iped_resp.content,
        status_code=iped_resp.status_code,
        headers=dict(iped_resp.headers),
        media_type=iped_resp.headers.get("content-type"),
    )


async def _build_and_ingest(
    request_path: str,
    request_method: str,
    source_id: str,
    item_id: str,
    iped_resp_body: bytes,
    bookmark_body: Optional[bytes],
):
    """
    Constrói o evento SUPREME e o envia para ingestão.
    Executado de forma assíncrona para não atrasar a resposta ao perito.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Buscar metadata do item no IPED ───────────────────────────────────
    item_meta = {}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            meta_resp = await client.get(
                f"{IPED_API_URL}/sources/{source_id}/docs/{item_id}"
            )
            if meta_resp.status_code == 200:
                item_meta = meta_resp.json().get("properties", {})
    except Exception as e:
        log.debug(f"Falha ao buscar metadata do item {item_id}: {e}")

    def first(key: str) -> Optional[str]:
        vals = item_meta.get(key)
        return vals[0] if vals else None

    iped_content_type = first("contentType") or first("type") or ""
    nudity_class      = first("nudityClass")
    ai_csam           = first("ai:csam")
    ai_porn           = first("ai:porn")
    file_duration_ms  = first("videoLength") or first("duration")

    # ── Determinar event_type ─────────────────────────────────────────────
    if request_method == "POST" and "bookmarks" in request_path:
        event_type = "classification_event"
    else:
        event_type = classify_request(request_path, iped_content_type)
        if event_type is None:
            return  # não é um endpoint auditável

    # ── Determinar media_type ─────────────────────────────────────────────
    media_type = classify_media_type(iped_content_type)
    if "/thumb" in request_path:
        media_type = "preview"

    # ── Determinar severity ────────────────────────────────────────────────
    severity = severity_from_nudity(nudity_class, ai_csam, ai_porn)

    # ── Determinar duration_seconds ───────────────────────────────────────
    # Prioridade: (1) patch Java → duração real de visualização
    #             (2) duração do arquivo de vídeo como proxy
    #             (3) 0.0 (padrão conservador)
    duration_secs = 0.0
    java_duration = duration_cache.get_duration(item_id)
    if java_duration is not None:
        duration_secs = java_duration
    elif file_duration_ms:
        try:
            duration_secs = float(file_duration_ms) / 1000.0
        except ValueError:
            pass

    # ── Determinar user_identifier ────────────────────────────────────────
    # Tenta ler do cache do patch Java; fallback para env var
    open_entry = duration_cache.get_open_entry(item_id)
    raw_user   = (open_entry or {}).get("userId", USER_ID_FALLBACK)

    # Fix B1+B7: pseudonimizar AQUI, antes de enviar ao SUPREME.
    # O watcher também pseudonimiza, garantindo que ambos gerem o mesmo
    # id_hash e event_hash para o mesmo evento (deduplicação correta).
    id_hash = pseudonymize(raw_user)

    # ── Montar evento SUPREME ─────────────────────────────────────────────
    event = {
        "timestamp":       now_iso,
        "event_type":      event_type,
        "media_type":      media_type,
        "severity":        severity,
        "duration_seconds": duration_secs,
        "user_identifier": id_hash,    # Fix B1: pseudonimizado (SHA-256 + SALT)
        "source_tool":     "iped",
        # campos extras para rastreabilidade (não armazenados no SUPREME)
        "_iped_item_id":   item_id,
        "_iped_source_id": source_id,
    }

    log.info(
        f"Evento: {event_type} | item={item_id} | media={media_type} "
        f"| severity={severity} | duration={duration_secs}s | user={raw_user}"
    )

    await ingest_event(event)


# ── Entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not SALT or len(SALT) < 32:
        raise SystemExit("SUPREME_SALT ausente ou fraco; defina segredo offline >=32 caracteres")
    if not SUPREME_TOKEN or len(SUPREME_TOKEN) < 32:
        raise SystemExit("SUPREME_API_TOKEN ausente ou fraco; defina token >=32 caracteres")
    import uvicorn
    log.info(f"SUPREME Proxy iniciando na porta {PROXY_PORT}")
    log.info(f"Encaminhando para IPED em {IPED_API_URL}")
    log.info(f"Enviando eventos para SUPREME em {SUPREME_API_URL}")
    log.info(f"Arquivo de auditoria Java: {AUDIT_LOG_PATH}")
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT, log_level="warning")
