from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import generate_key, hash_key, require_admin

# Every route in this router requires the admin key

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class CreateKeyRequest(BaseModel):
    name: str
    rpm_limit: int = Field(60, gt=0) #requests per minute; must be positive

class UpdateKeyRequest(BaseModel):
    rpm_limit: int = Field(gt=0)

# Returned once at creation: the only time the full key is visible
class CreatedKey(BaseModel):
    id: int
    name: str
    key: str
    rpm_limit: int
    created_at: datetime

# Safe to list: no key, no hash
class KeyInfo(BaseModel):
    id: int
    name: str
    key_prefix: str
    rpm_limit: int
    created_at: datetime
    revoked_at: datetime | None

# Create a key: store only its hash, return the plain key once

@router.post("/keys", response_model=CreatedKey, status_code=201)

async def create_key(body: CreateKeyRequest, request: Request):
    key = generate_key()
    row = await request.app.state.db.fetchrow(
        """INSERT INTO api_keys (name, key_prefix, key_hash, rpm_limit)
            VALUES ($1, $2, $3, $4)
            RETURNING id, name, rpm_limit, created_at""",
            body.name, key[:10], hash_key(key), body.rpm_limit
    )
    return CreatedKey(**dict(row), key=key)


# List all keys (active and revoked)
@router.get("/keys", response_model=list[KeyInfo])

async def list_keys(request: Request):
    rows = await request.app.state.db.fetch(
        "SELECT id, name, key_prefix, rpm_limit, created_at, revoked_at FROM api_keys ORDER BY id"
    )
    return [KeyInfo(**dict(r)) for r in rows]

# Revoke a key (soft delete: mark it, keep the row)
@router.delete("/keys/{key_id}", response_model=KeyInfo)

async def revoke_key(key_id: int, request: Request):
    row = await request.app.state.db.fetchrow(
        """UPDATE api_keys SET revoked_at = now()
           WHERE id = $1 AND revoked_at IS NULL
           RETURNING id, name, key_prefix, rpm_limit, created_at, revoked_at""",
           key_id
    )
    if row is None:
        raise HTTPException(404, "Key not found or already revoked")
    return KeyInfo(**dict(row))

@router.patch("/keys/{key_id}", response_model=KeyInfo)
async def update_key(key_id:int, body:UpdateKeyRequest, request: Request):
    row = await request.app.state.db.fetchrow(
        """UPDATE api_keys SET rpm_limit = $2
        WHERE ID = $1
        RETURNING id, name, key_prefix, rpm_limit, created_at, revoked_at""",
        key_id, body.rpm_limit
    )
    if row is None:
        raise HTTPException(404, "Key not found")
    return KeyInfo(**dict(row))