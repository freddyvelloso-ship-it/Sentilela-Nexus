"""
sentinela.app.api.auth_router
=============================
Login e gestao de usuarios (apenas master pode criar usuarios).
"""

from __future__ import annotations

from datetime import timedelta
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from ..auth import (
    Token, UserOut,
    authenticate_user, create_access_token,
    get_current_user, hash_password, require_master,
)
from ..config import settings
from ..db import AsyncSession, get_db

router = APIRouter(prefix="/api/auth", tags=["Auth"])

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 horas


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str = "pibic"


@router.post("/login", response_model=Token)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais invalidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        data={"sub": user["email"], "role": user["role"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.post("/bootstrap", status_code=201, summary="Criar primeiro usuario master (uso unico)")
async def bootstrap_master(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    x_bootstrap_token: str = Header(default=""),
):
    flag = await db.execute(text("SELECT value FROM system_config WHERE key = 'bootstrap_used'"))
    if flag.fetchone():
        raise HTTPException(status_code=410, detail="Bootstrap ja utilizado e permanentemente desabilitado.")
    if not settings.bootstrap_token:
        raise HTTPException(status_code=403, detail="Bootstrap desabilitado.")
    if not hmac.compare_digest(x_bootstrap_token.encode(), settings.bootstrap_token.encode()):
        raise HTTPException(status_code=403, detail="Bootstrap token invalido.")

    existing = await db.execute(text("SELECT id FROM sentinela_users WHERE role = 'master'"))
    if existing.fetchone():
        await db.execute(text("INSERT INTO system_config(key, value) VALUES ('bootstrap_used', 'true') ON CONFLICT (key) DO UPDATE SET value='true', updated_at=NOW()"))
        await db.commit()
        raise HTTPException(status_code=409, detail="Ja existe um master. Use o login normal.")

    pw_hash = hash_password(body.password)
    await db.execute(
        text("INSERT INTO sentinela_users (email, password_hash, role) VALUES (:e, :p, 'master')"),
        {"e": body.email, "p": pw_hash},
    )
    await db.execute(text("INSERT INTO system_config(key, value) VALUES ('bootstrap_used', 'true') ON CONFLICT (key) DO UPDATE SET value='true', updated_at=NOW()"))
    await db.commit()
    return {"status": "ok", "message": f"Master '{body.email}' criado. Remova BOOTSTRAP_TOKEN do .env."}


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_master),
):
    if body.role not in ("master", "pibic"):
        raise HTTPException(status_code=400, detail="role deve ser master ou pibic")
    existing = await db.execute(
        text("SELECT id FROM sentinela_users WHERE email = :e"), {"e": body.email}
    )
    if existing.fetchone():
        raise HTTPException(status_code=409, detail="Email ja cadastrado")
    pw_hash = hash_password(body.password)
    await db.execute(
        text("INSERT INTO sentinela_users (email, password_hash, role) VALUES (:email, :pw, :role)"),
        {"email": body.email, "pw": pw_hash, "role": body.role},
    )
    await db.commit()
    return {"status": "ok", "email": body.email, "role": body.role}


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_master),
):
    result = await db.execute(
        text("SELECT id, email, role, created_at FROM sentinela_users ORDER BY created_at")
    )
    rows = result.fetchall()
    return [{"id": r[0], "email": r[1], "role": r[2], "created_at": str(r[3])} for r in rows]
