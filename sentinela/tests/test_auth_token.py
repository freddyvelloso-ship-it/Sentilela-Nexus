from jose import jwt

from src.app.auth import create_access_token
from src.app.config import settings


def test_access_token_contains_jti_and_role():
    token = create_access_token({"sub": "admin@local.test", "role": "master"})
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])

    assert payload["sub"] == "admin@local.test"
    assert payload["role"] == "master"
    assert isinstance(payload.get("jti"), str)
    assert len(payload["jti"]) >= 32
