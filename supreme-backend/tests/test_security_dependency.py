import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.app.security import require_ingest_token


def test_rejects_missing_token():
    with pytest.raises(HTTPException) as exc:
        require_ingest_token(None)
    assert exc.value.status_code == 401


def test_rejects_wrong_token(monkeypatch):
    class Settings:
        api_ingest_token = "b" * 32
    monkeypatch.setattr("src.app.security.get_settings", lambda: Settings())
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="x" * 32)
    with pytest.raises(HTTPException) as exc:
        require_ingest_token(credentials)
    assert exc.value.status_code == 403


def test_accepts_correct_token(monkeypatch):
    class Settings:
        api_ingest_token = "b" * 32
    monkeypatch.setattr("src.app.security.get_settings", lambda: Settings())
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="b" * 32)
    assert require_ingest_token(credentials) is None
