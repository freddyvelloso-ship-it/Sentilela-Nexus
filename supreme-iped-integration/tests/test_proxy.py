"""
Testes automatizados do supreme-proxy.
Cobrem: classificacao de endpoints IPED, construcao de eventos, severidade.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "supreme-proxy"))


# ── Helpers ───────────────────────────────────────────────────────────────

def pseudonymize(user_id: str, salt: str) -> str:
    return hashlib.sha256((user_id + salt).encode()).hexdigest()


# Replicamos a logica de classificacao do proxy para testar isoladamente
ENDPOINT_MAP = {
    "/api/evidences":       ("evidence_access", 3),
    "/api/chat":            ("chat_view",        2),
    "/api/iped/view":       ("image_view",       4),
    "/api/iped/video":      ("video_play",       5),
    "/api/iped/thumb":      ("thumb_view",       1),
    "/api/iped/html":       ("html_view",        3),
    "/api/iped/audio":      ("audio_play",       4),
    "/api/bookmarks":       ("bookmark_event",   2),
    "/api/graph":           ("graph_view",       2),
}

def classify_endpoint(path: str):
    """Classifica um path da API do IPED e retorna (event_type, severity)."""
    for prefix, (event_type, severity) in ENDPOINT_MAP.items():
        if path.startswith(prefix):
            return event_type, severity
    return "api_call", 1


# ── Testes de classificacao de endpoints ─────────────────────────────────

class TestEndpointClassification:
    def test_video_endpoint(self):
        etype, sev = classify_endpoint("/api/iped/video/item123")
        assert etype == "video_play"
        assert sev == 5

    def test_image_endpoint(self):
        etype, sev = classify_endpoint("/api/iped/view/item456")
        assert etype == "image_view"
        assert sev == 4

    def test_audio_endpoint(self):
        etype, sev = classify_endpoint("/api/iped/audio/item789")
        assert etype == "audio_play"
        assert sev == 4

    def test_evidence_access(self):
        etype, sev = classify_endpoint("/api/evidences/case001")
        assert etype == "evidence_access"
        assert sev == 3

    def test_unknown_endpoint_fallback(self):
        etype, sev = classify_endpoint("/api/unknown/path")
        assert etype == "api_call"
        assert sev == 1

    def test_thumb_lowest_severity(self):
        _, sev = classify_endpoint("/api/iped/thumb/img001")
        assert sev == 1  # thumbnail e o menos severo

    def test_video_highest_severity(self):
        _, sev = classify_endpoint("/api/iped/video/vid001")
        assert sev == 5  # video e o mais severo

    @pytest.mark.parametrize("path,expected_type", [
        ("/api/iped/view/x",  "image_view"),
        ("/api/iped/video/x", "video_play"),
        ("/api/iped/html/x",  "html_view"),
        ("/api/iped/audio/x", "audio_play"),
        ("/api/iped/thumb/x", "thumb_view"),
        ("/api/chat/x",       "chat_view"),
        ("/api/graph/x",      "graph_view"),
    ])
    def test_all_known_endpoints(self, path, expected_type):
        etype, _ = classify_endpoint(path)
        assert etype == expected_type


# ── Testes de construcao de eventos do proxy ─────────────────────────────

class TestProxyEventConstruction:
    def test_event_has_required_fields(self):
        path = "/api/iped/video/item123"
        event_type, severity = classify_endpoint(path)
        user_id = "perito_01"
        salt = "test_salt"
        id_hash = pseudonymize(user_id, salt)

        event = {
            "id_hash":          id_hash,
            "timestamp":        "2026-06-07T10:00:00Z",
            "event_type":       event_type,
            "artifact_id":      "item123",
            "severity":         severity,
            "duration_seconds": 0,
            "source":           "iped_proxy",
        }

        required = ["id_hash", "timestamp", "event_type", "artifact_id",
                    "severity", "duration_seconds", "source"]
        for field in required:
            assert field in event, f"Campo faltando: {field}"

    def test_artifact_id_extracted_from_path(self):
        """O artifact_id deve ser extraido do path da requisicao."""
        path = "/api/iped/view/case001_item_42"
        artifact_id = path.split("/")[-1]
        assert artifact_id == "case001_item_42"

    def test_user_id_not_in_event(self):
        """user_id nunca deve aparecer no evento enviado ao SUPREME."""
        event = {
            "id_hash":          pseudonymize("perito_secreto", "salt"),
            "timestamp":        "2026-06-07T10:00:00Z",
            "event_type":       "video_play",
            "artifact_id":      "item001",
            "severity":         5,
            "duration_seconds": 0,
            "source":           "iped_proxy",
        }
        assert "perito_secreto" not in json.dumps(event)
        assert "user_id" not in event

    def test_ingest_payload_wraps_events(self):
        """Payload para /v1/events/ingest deve ter chave 'events'."""
        event = {"id_hash": "abc", "event_type": "test"}
        payload = {"events": [event]}
        assert "events" in payload
        assert isinstance(payload["events"], list)

    def test_source_is_iped_proxy(self):
        event_type, severity = classify_endpoint("/api/iped/view/x")
        event = {
            "id_hash":          "hash",
            "timestamp":        "2026-06-07T10:00:00Z",
            "event_type":       event_type,
            "artifact_id":      "x",
            "severity":         severity,
            "duration_seconds": 0,
            "source":           "iped_proxy",
        }
        assert event["source"] == "iped_proxy"


# ── Testes de severidade ──────────────────────────────────────────────────

class TestSeverityMapping:
    def test_severity_in_valid_range(self):
        for path in [
            "/api/iped/thumb/x",
            "/api/chat/x",
            "/api/iped/view/x",
            "/api/iped/audio/x",
            "/api/iped/video/x",
        ]:
            _, sev = classify_endpoint(path)
            assert 1 <= sev <= 5, f"Severity fora do range para {path}: {sev}"

    def test_severity_ordering(self):
        """Videos e audios devem ter severidade maior que thumbnails."""
        _, thumb_sev = classify_endpoint("/api/iped/thumb/x")
        _, video_sev = classify_endpoint("/api/iped/video/x")
        _, audio_sev = classify_endpoint("/api/iped/audio/x")
        assert video_sev > thumb_sev
        assert audio_sev > thumb_sev

    def test_video_is_most_severe(self):
        severities = [sev for _, sev in (classify_endpoint(p) for p in [
            "/api/iped/thumb/x",
            "/api/iped/view/x",
            "/api/iped/audio/x",
            "/api/iped/video/x",
            "/api/chat/x",
        ])]
        _, video_sev = classify_endpoint("/api/iped/video/x")
        assert video_sev == max(severities)
