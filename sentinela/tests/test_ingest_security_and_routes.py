import pytest
from fastapi import HTTPException

from src.app.api.ingest import _check_api_key, router, IEO_FULL_UPSERT_SQL, PSI_ONLY_UPDATE_SQL
from src.app.config import settings


def test_ingest_api_key_uses_constant_time_guard_semantics():
    assert _check_api_key(settings.supreme_api_key) is None
    with pytest.raises(HTTPException) as exc:
        _check_api_key("wrong-key")
    assert exc.value.status_code == 403


def test_ingest_router_exposes_ieo_and_psychometric_routes():
    paths = {route.path for route in router.routes}
    assert "/api/v1/ingest/ieo" in paths
    assert "/api/v1/ingest/psychometric" in paths


def test_ieo_upserts_preserve_existing_values_with_coalesce():
    assert "COALESCE(EXCLUDED.ieo_score" in IEO_FULL_UPSERT_SQL
    assert "COALESCE(EXCLUDED.psi_score" in PSI_ONLY_UPDATE_SQL
