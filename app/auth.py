import hashlib
import os
import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# Reads the "Authorization: Bearer <token>" header.
# auto_error=False -> we send our own 401 instead of FastAPI's default 403.
bearer = HTTPBearer(auto_error=False)

# Who is calling (passed to endpoints that need it, e.g. for usage logs later)
class ApiKey(BaseModel):
    id: int
    name: str
    rpm_limit: int


# New random key: "gw_" + 32 random bytes as URL-safe text
def generate_key() -> str:
    return "gw_" + secrets.token_urlsafe(32)


# One-way fingerprint of a key; this is what we store and look up
def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(401, message, headers={"WWW-Authenticate": "Bearer"})

# Dependency for protected routes: valid, non-revoked gateway key required
async def require_api_key(
        request: Request,
        creds: HTTPAuthorizationCredentials | None = Depends(bearer)
)->ApiKey:
    if creds is None:
        raise _unauthorized("Missing API Key")

    row = await request.app.state.db.fetchrow(
        "SELECT id, name, rpm_limit FROM api_keys WHERE key_hash = $1 AND revoked_at IS NULL",
        hash_key(creds.credentials)
    )
    if row is None:
        raise _unauthorized("Invalid or revoked API key")
    return ApiKey(**dict(row))

# Dependency for admin routes: must match ADMIN_API_KEY from .env
async def require_admin(
        creds: HTTPAuthorizationCredentials | None = Depends(bearer)
)-> None:
    admin_key = os.environ.get("ADMIN_API_KEY")
    if not admin_key or creds is None or not secrets.compare_digest(creds.credentials, admin_key):
        raise _unauthorized("Admin key required")