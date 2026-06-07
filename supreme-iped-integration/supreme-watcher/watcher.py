"""
supreme-watcher.py
==================
Agente complementar ao proxy: lê o arquivo NDJSON do patch Java diretamente,
pseudonimiza identidades e envia eventos fechados (com duration_seconds preciso)
para o SUPREME /events/ingest.

O proxy (proxy.py) captura eventos em tempo real via interceptação da API.
O watcher captura os mesmos eventos com duração exata assim que o item é fechado
(evento "close" do patch Java) e evita duplicatas via event_hash.

Portanto os dois rodam juntos:
  - proxy.py  → captura imediato (duration pode ser 0 ou proxy de vídeo)
  - watcher.py → captura tardio com duration_seconds real, substitui via upsert

Configuração (variáveis de ambiente):
  SUPREME_AUDIT_LOG    Arquivo NDJSON do patch Java (default: ~/supreme_audit.ndjson)
  SUPREME_API_URL      URL do backend SUPREME
  SUPREME_API_TOKEN    JWT de autenticação
  SUPREME_SALT         Salt de pseudonimização (manter OFFLINE em produção)
  SUPREME_USER_ID      Fallback de user_id se Java não registrou
  WATCHER_POLL_SECS    Intervalo de polling em segundos (default: 30)
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Configuração ───────────────────────────────────────────────────────────

AUDIT_LOG_PATH  = Path(os.environ.get(
    "SUPREME_AUDIT_LOG", Path.home() / "supreme_audit.ndjson"
))
SUPREME_API_URL = os.environ.get("SUPREME_API_URL",   "http://localhost:8000")
SUPREME_TOKEN   = os.environ.get("SUPREME_API_TOKEN", "")
SALT            = os.environ.get("SUPREME_SALT",      "")
USER_FALLBACK   = os.environ.get("SUPREME_USER_ID",   "unknown")
POLL_SECS       = int(os.environ.get("WATCHER_POLL_SECS", "30"))

# Arquivo de estado: registra bytes já lidos para não reprocessar
STATE_FILE = Path(os.environ.get(
    "WATCHER_STATE_FILE",
    Path.home() / ".supreme_watcher_state.json"
))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [watcher] %(levelname)s %(message)s")
log = logging.getLogger("supreme-watcher")


# ── Pseudonimização ────────────────────────────────────────────────────────

def pseudonymize(user_id: str) -> str:
    """SHA-256(user_id + SALT). O salt NUNCA vai para o banco SUPREME."""
    return hashlib.sha256(f"{user_id}{SALT}".encode()).hexdigest()


def compute_event_hash(event: dict) -> str:
    """
    Hash determinístico do evento conforme spec SUPREME V4, seção 11.
    Garante deduplicação via INSERT ... ON CONFLICT DO NOTHING no banco.
    """
    key = {k: event[k] for k in
           ["user_identifier", "timestamp", "event_type", "media_type",
            "severity", "source_tool"]}
    return hashlib.sha256(
        json.dumps(key, sort_keys=True).encode()
    ).hexdigest()


# ── Mapeamentos ────────────────────────────────────────────────────────────

_MEDIA_TYPE_MAP = {
    "video": "video",
    "image": "image",
    "audio": "preview",
    "text":  "preview",
    "application": "preview",
}

def classify_media_type(iped_mime: str) -> str:
    if not iped_mime:
        return "preview"
    top = iped_mime.split("/")[0].lower()
    return _MEDIA_TYPE_MAP.get(top, "preview")


def severity_from_entry(entry: dict) -> int:
    """
    Mapeia campos IPED → escala COPINE 1-5.
    nudityClass (1-5) do IPED é mapeamento direto.
    ai:csam/aiCsam ≥ 60 → 5; ai:porn/aiPorn ≥ 60 → 3; default 1.
    """
    ai_csam = entry.get("aiCsam") or entry.get("ai:csam")
    ai_porn = entry.get("aiPorn") or entry.get("ai:porn")
    nudity  = entry.get("nudityClass")
    try:
        if ai_csam and float(ai_csam) >= 60:
            return 5
    except (ValueError, TypeError):
        pass
    try:
        if ai_porn and float(ai_porn) >= 60:
            return 3
    except (ValueError, TypeError):
        pass
    try:
        if nudity:
            return max(1, min(5, int(nudity)))
    except (ValueError, TypeError):
        pass
    return 1


def event_type_from_entry(entry: dict) -> str:
    """Deriva event_type a partir do mediaType e do evento Java."""
    java_event = entry.get("event", "")
    if java_event == "classification_event":
        return "classification_event"
    mime = (entry.get("mediaType") or "").lower()
    if "video" in mime:
        return "video_play"
    if "image" in mime:
        return "image_view"
    return "file_open"


# ── Construção do evento SUPREME ───────────────────────────────────────────

def build_supreme_event(entry: dict) -> dict:
    """
    Transforma uma entrada "close" do SupremeAuditLogger em um
    EventRecord conforme o schema do SUPREME V4.
    """
    raw_user   = entry.get("userId") or USER_FALLBACK
    id_hash    = pseudonymize(raw_user)

    open_ts    = int(entry.get("openTs",  0))
    close_ts   = int(entry.get("closeTs", 0))

    if close_ts > open_ts > 0:
        duration_secs = round((close_ts - open_ts) / 1000.0, 2)
    else:
        # fallback: duração do arquivo de vídeo se disponível
        file_dur_ms = entry.get("fileDurationMs")
        try:
            duration_secs = round(float(file_dur_ms) / 1000.0, 2) if file_dur_ms else 0.0
        except (ValueError, TypeError):
            duration_secs = 0.0

    # Timestamp = abertura do item (ISO8601 UTC)
    if open_ts:
        ts_iso = datetime.fromtimestamp(open_ts / 1000.0, tz=timezone.utc).isoformat()
    else:
        ts_iso = datetime.now(timezone.utc).isoformat()

    event = {
        "timestamp":        ts_iso,
        "event_type":       event_type_from_entry(entry),
        "media_type":       classify_media_type(entry.get("mediaType", "")),
        "severity":         severity_from_entry(entry),
        "duration_seconds": duration_secs,
        "user_identifier":  id_hash,   # já pseudonimizado
        "source_tool":      "iped",
    }
    event["event_hash"] = compute_event_hash(event)
    return event


# ── Estado de progresso ────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"offset": 0}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


# ── Ingestão no SUPREME ────────────────────────────────────────────────────

def ingest_batch(events: list[dict]) -> bool:
    if not events:
        return True
    headers = {
        "Authorization": f"Bearer {SUPREME_TOKEN}",
        "Content-Type":  "application/json",
    }
    try:
        resp = requests.post(
            f"{SUPREME_API_URL}/v1/events/ingest",
            json={"events": events},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            result = resp.json()
            log.info(
                f"Ingeridos {result.get('events_stored', '?')} de "
                f"{result.get('events_received', '?')} eventos"
            )
            return True
        else:
            log.error(f"SUPREME retornou {resp.status_code}: {resp.text[:300]}")
            return False
    except requests.RequestException as e:
        log.error(f"Erro ao conectar ao SUPREME: {e}")
        return False


# ── Loop principal ─────────────────────────────────────────────────────────

def run():
    if not SALT or len(SALT) < 32:
        raise SystemExit("SUPREME_SALT ausente ou fraco; defina segredo offline >=32 caracteres")
    if not SUPREME_TOKEN or len(SUPREME_TOKEN) < 32:
        raise SystemExit("SUPREME_API_TOKEN ausente ou fraco; defina token >=32 caracteres")
    log.info("supreme-watcher iniciado")
    log.info(f"Monitorando: {AUDIT_LOG_PATH}")
    log.info(f"SUPREME API: {SUPREME_API_URL}")
    log.info(f"Intervalo de polling: {POLL_SECS}s")

    state = load_state()

    while True:
        events_batch = []

        if AUDIT_LOG_PATH.exists():
            try:
                with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
                    f.seek(state["offset"])
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            log.warning(f"Linha inválida ignorada: {line[:80]}")
                            continue

                        # O watcher processa apenas eventos "close"
                        # (tem open_ts e close_ts — duração completa disponível)
                        # e "classification_event" (bookmark).
                        event_kind = entry.get("event", "")
                        if event_kind not in ("close", "classification_event"):
                            continue

                        try:
                            supreme_event = build_supreme_event(entry)
                            events_batch.append(supreme_event)
                        except Exception as e:
                            log.error(f"Erro ao construir evento: {e} | entrada: {entry}")

                    state["offset"] = f.tell()
            except OSError as e:
                log.error(f"Erro ao ler arquivo de auditoria: {e}")

        if events_batch:
            success = ingest_batch(events_batch)
            if success:
                save_state(state)
            else:
                log.warning("Ingestão falhou — offset não avançado, retry no próximo ciclo")
        else:
            # Sem novos eventos — salva offset para não reprocessar linhas ignoradas
            save_state(state)

        time.sleep(POLL_SECS)


if __name__ == "__main__":
    run()
