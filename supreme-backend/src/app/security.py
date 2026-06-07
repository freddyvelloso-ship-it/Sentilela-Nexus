"""Dependências de segurança do SUPREME."""

from __future__ import annotations

import hmac
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def require_ingest_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token ausente")
    expected = get_settings().api_ingest_token
    if not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token de ingestão inválido")


def require_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token ausente")
    expected = get_settings().api_secret_key
    if not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token inválido")
