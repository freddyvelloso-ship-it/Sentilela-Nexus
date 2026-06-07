from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import text

from .config import settings
from .db import AsyncSession, get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Token(BaseModel):
    access_token: str
    token_type: str


class UserOut(BaseModel):
    email: str
    role: str


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _legacy_sha256(password: str) -> str:
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith("$2"):
        return pwd_context.verify(plain, hashed)
    # Compatibilidade controlada com usuários antigos; rehash ocorre no login.
    return _legacy_sha256(plain) == hashed


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(tz=timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    return jwt.encode({**data, "exp": expire, "jti": str(uuid4())}, settings.secret_key, algorithm=settings.algorithm)


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[dict]:
    result = await db.execute(
        text("SELECT id, email, password_hash, role FROM sentinela_users WHERE email = :e"),
        {"e": email},
    )
    row = result.fetchone()
    if not row:
        return None
    if not verify_password(password, row[2]):
        return None
    if not str(row[2]).startswith("$2"):
        await db.execute(
            text("UPDATE sentinela_users SET password_hash = :p WHERE id = :id"),
            {"p": hash_password(password), "id": row[0]},
        )
        await db.commit()
    return {"id": row[0], "email": row[1], "role": row[3]}


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub", "")
        role:  str = payload.get("role", "")
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")
        return {"email": email, "role": role}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")


async def require_master(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "master":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a master")
    return user
