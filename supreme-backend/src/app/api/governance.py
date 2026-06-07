"""Endpoints LGPD/governança: auditoria e direito ao apagamento."""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..db import erase_subject, get_db, upsert_consent
from ..security import require_api_token

class ConsentRequest(BaseModel):
    status: str

router = APIRouter(prefix="/governance", tags=["Governance"], dependencies=[Depends(require_api_token)])

@router.delete("/subjects/{id_hash}")
async def delete_subject(
    id_hash: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_actor: Annotated[str | None, Header(alias="X-Actor")] = None,
):
    actor = f"api:{(x_actor or 'unspecified')};ip={request.client.host if request.client else 'unknown'}"
    deleted = await erase_subject(db, id_hash=id_hash, actor=actor)
    return {"status": "erased", "id_hash": id_hash, "deleted": deleted}


@router.post("/consent/{id_hash}")
async def set_consent(
    id_hash: str,
    body: ConsentRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_actor: Annotated[str | None, Header(alias="X-Actor")] = None,
):
    actor = f"api:{(x_actor or 'unspecified')};ip={request.client.host if request.client else 'unknown'}"
    await upsert_consent(db, id_hash=id_hash, status=body.status, actor=actor)
    return {"status": "ok", "id_hash": id_hash, "consent": body.status}
