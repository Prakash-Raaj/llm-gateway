from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import generate_key, hash_key, require_admin

# Every route in this router requires the admin key

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class CreateKeyRequest(BaseModel):
    name: str

# Returned once at creation: the only time the full key is visible
class CreatedKey(BaseModel):
    id: int
    name: str
    key: str
    created_at: datetime

# Safe to list: no key, no hash
class KeyInfo(BaseModel):
    id: int
    name: str
    key_prefix: str
    created_at: datetime
    revoked_at: datetime | None

# Create a key: store only its hash, return the plain key once

@router.post("/keys", response_model=CreatedKey, status_code=201)

async def create_key(body: CreateKeyRequest, request: Request):
    key = generate_key()
    row = await request.app.state.db.fetchrow(
        """INSERT INTO api_keys (name, key_prefix, key_hash)
            VALUES ($1, $2, $3)
            RETURNING id, name, created_at""", 
            body.name, key[:10], hash_key(key)
    )
    return CreatedKey(**dict(row), key=key)


# List all keys (active and revoked)
@router.get("/keys", response_model=list[KeyInfo])

async def list_keys(request: Request):
    rows = await request.app.state.db.fetch(
        "SELECT id, name, key_prefix, created_at, revoked_at FROM api_keys ORDER BY id"
    )
    return [KeyInfo(**dict(r)) for r in rows]

# Revoke a key (soft delete: mark it, keep the row)
@router.delete("/keys/{key_id}", response_model=KeyInfo)

async def revoke_key(key_id: int, request: Request):
    row = await request.app.state.db.fetchrow(
        """UPDATE api_keys SET revoked_at = now()
           WHERE id = $1 AND revoked_at IS NULL
           RETURNING id, name, key_prefix, created_at, revoked_at""",
           key_id
    )
    if row is None:
        raise HTTPException(404, "Key not found or already revoked")
    return KeyInfo(**dict(row))