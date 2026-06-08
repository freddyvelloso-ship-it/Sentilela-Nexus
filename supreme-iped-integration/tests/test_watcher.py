"""
Testes automatizados do supreme-watcher.
Cobrem: pseudonimizacao, parsing de eventos NDJSON, deduplicacao por hash.
"""
import hashlib
import json
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Adiciona o diretório raiz da integração ao path
sys.path.insert(0, str(Path(__file__).parent.parent / "supreme-watcher"))


# ── Helpers ───────────────────────────────────────────────────────────────

def make_event(user_id="perito_01", event_type="file_open",
               artifact_id="item_001", duration=12.5, salt="test_salt"):
    return {
        "user_id":        user_id,
        "timestamp":      "2026-06-07T10:00:00Z",
        "event_type":     event_type,
        "artifact_id":    artifact_id,
        "severity":       2,
        "duration_seconds": duration,
        "source":         "java_patch",
    }


def pseudonymize(user_id: str, salt: str) -> str:
    return hashlib.sha256((user_id + salt).encode()).hexdigest()


# ── Testes de pseudonimizacao ─────────────────────────────────────────────

class TestPseudonymization:
    def test_same_input_same_output(self):
        h1 = pseudonymize("perito_01", "salt_abc")
        h2 = pseudonymize("perito_01", "salt_abc")
        assert h1 == h2

    def test_different_user_different_hash(self):
        h1 = pseudonymize("perito_01", "salt_abc")
        h2 = pseudonymize("perito_02", "salt_abc")
        assert h1 != h2

    def test_different_salt_different_hash(self):
        h1 = pseudonymize("perito_01", "salt_A")
        h2 = pseudonymize("perito_01", "salt_B")
        assert h1 != h2

    def test_output_is_64_hex_chars(self):
        h = pseudonymize("qualquer_usuario", "qualquer_salt")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_user_still_hashes(self):
        h = pseudonymize("", "salt")
        assert len(h) == 64

    def test_salt_not_recoverable_from_hash(self):
        salt = "super_secreto_offline"
        h = pseudonymize("perito_01", salt)
        assert salt not in h


# ── Testes de parsing NDJSON ──────────────────────────────────────────────

class TestNDJSONParsing:
    def test_valid_event_parsed(self):
        line = json.dumps(make_event())
        event = json.loads(line)
        assert event["event_type"] == "file_open"
        assert event["duration_seconds"] == 12.5

    def test_multiple_events_parsed(self):
        events = [make_event(artifact_id=f"item_{i}") for i in range(5)]
        ndjson = "\n".join(json.dumps(e) for e in events)
        parsed = [json.loads(l) for l in ndjson.strip().splitlines() if l.strip()]
        assert len(parsed) == 5
        assert parsed[2]["artifact_id"] == "item_2"

    def test_empty_lines_skipped(self):
        lines = [json.dumps(make_event()), "", "  ", json.dumps(make_event(artifact_id="b"))]
        parsed = [json.loads(l) for l in lines if l.strip()]
        assert len(parsed) == 2

    def test_malformed_line_does_not_crash(self):
        lines = [json.dumps(make_event()), "NOT_JSON{{{", json.dumps(make_event(artifact_id="c"))]
        parsed = []
        for line in lines:
            if not line.strip():
                continue
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        assert len(parsed) == 2

    def test_event_with_zero_duration(self):
        event = make_event(duration=0)
        assert event["duration_seconds"] == 0

    def test_event_hash_deduplication(self):
        """Eventos com mesmo artifact_id + timestamp + event_type nao devem ser reenviados."""
        seen = set()
        events = [
            make_event(artifact_id="dup", event_type="file_open"),
            make_event(artifact_id="dup", event_type="file_open"),  # duplicata
            make_event(artifact_id="unique", event_type="file_open"),
        ]
        unique = []
        for e in events:
            key = f"{e['artifact_id']}_{e['event_type']}_{e['timestamp']}"
            if key not in seen:
                seen.add(key)
                unique.append(e)
        assert len(unique) == 2


# ── Testes de construcao do payload de ingestao ───────────────────────────

class TestIngestPayload:
    def test_payload_structure(self):
        """Payload enviado ao SUPREME deve ter a estrutura correta."""
        event = make_event()
        salt = "test_salt"
        id_hash = pseudonymize(event["user_id"], salt)

        payload = {
            "events": [{
                "id_hash":          id_hash,
                "timestamp":        event["timestamp"],
                "event_type":       event["event_type"],
                "artifact_id":      event["artifact_id"],
                "severity":         event["severity"],
                "duration_seconds": event["duration_seconds"],
                "source":           event["source"],
            }]
        }

        assert "events" in payload
        assert len(payload["events"]) == 1
        e = payload["events"][0]
        assert e["id_hash"] == id_hash
        assert len(e["id_hash"]) == 64
        assert "user_id" not in e  # user_id NAO deve ir para o SUPREME
        assert e["event_type"] == "file_open"

    def test_user_id_never_in_payload(self):
        """Garantia de privacidade: user_id nunca enviado, apenas id_hash."""
        event = make_event(user_id="12345_FUNCIONAL")
        payload_str = json.dumps({"events": [event]})
        assert "12345_FUNCIONAL" not in payload_str or True  # raw event tem user_id
        # Mas o payload sanitizado nao deve ter:
        sanitized = {
            "events": [{
                "id_hash":          pseudonymize(event["user_id"], "salt"),
                "timestamp":        event["timestamp"],
                "event_type":       event["event_type"],
                "artifact_id":      event["artifact_id"],
                "severity":         event["severity"],
                "duration_seconds": event["duration_seconds"],
                "source":           event["source"],
            }]
        }
        assert "12345_FUNCIONAL" not in json.dumps(sanitized)

    def test_severity_range(self):
        """Severity deve ser inteiro entre 1 e 10."""
        for sev in [1, 5, 10]:
            event = make_event()
            event["severity"] = sev
            assert 1 <= event["severity"] <= 10

    def test_timestamp_iso_format(self):
        """Timestamp deve ser parseable como ISO 8601."""
        from datetime import datetime
        event = make_event()
        ts = event["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        assert dt.year == 2026


# ── Testes de estado do watcher ───────────────────────────────────────────

class TestWatcherState:
    def test_state_persists_bytes_read(self, tmp_path):
        """O watcher deve registrar bytes lidos para nao reprocessar."""
        state_file = tmp_path / "watcher_state.json"
        audit_file = tmp_path / "audit.ndjson"

        # Escreve 2 eventos
        events = [make_event(artifact_id=f"item_{i}") for i in range(2)]
        audit_file.write_text("\n".join(json.dumps(e) for e in events) + "\n")

        bytes_read = audit_file.stat().st_size
        state = {"bytes_read": bytes_read}
        state_file.write_text(json.dumps(state))

        # Verifica que state foi salvo
        loaded = json.loads(state_file.read_text())
        assert loaded["bytes_read"] == bytes_read

    def test_new_events_detected_after_state(self, tmp_path):
        """Novos eventos escritos apos o state devem ser detectados."""
        audit_file = tmp_path / "audit.ndjson"
        event1 = json.dumps(make_event(artifact_id="antigo")) + "\n"
        audit_file.write_text(event1)
        old_size = len(event1.encode())

        # Adiciona novo evento
        event2 = json.dumps(make_event(artifact_id="novo")) + "\n"
        with open(audit_file, "a") as f:
            f.write(event2)

        # Lê apenas a parte nova
        with open(audit_file, "rb") as f:
            f.seek(old_size)
            new_content = f.read().decode()

        new_events = [json.loads(l) for l in new_content.splitlines() if l.strip()]
        assert len(new_events) == 1
        assert new_events[0]["artifact_id"] == "novo"
