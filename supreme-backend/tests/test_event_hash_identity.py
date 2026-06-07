from datetime import datetime, timezone

from src.engine.supreme.models import EventRecord


def test_event_hash_ignores_duration_for_late_enrichment():
    base = dict(
        timestamp=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
        event_type="image_view",
        media_type="image",
        severity=3,
        user_identifier="hash-do-perito",
        source_tool="iped",
    )
    immediate = EventRecord(**base, duration_seconds=0.0)
    enriched = EventRecord(**base, duration_seconds=42.4)
    assert immediate.event_hash == enriched.event_hash
