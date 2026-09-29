"""CareRoute AI — request dependencies: authentication, principal resolution, rate limiting."""
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from audit import audit
from authz import Principal
from database import get_db
from models import User
from security import decode_token

# --- simple in-memory rate limiter (per identity, production would use Redis) ---
_RATE: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
RATE_LIMIT = 120  # requests
RATE_WINDOW = 60  # seconds


def rate_limit(request: Request):
    key = request.headers.get("authorization", "")[:48] or (request.client.host if request.client else "anon")
    now = time.time()
    q = _RATE[key]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Too many requests. Please slow down.")
    q.append(now)


def _device_from_ua(user_agent: str | None) -> str:
    return (user_agent or "unknown")[:120]


async def get_request_meta(request: Request) -> dict:
    return {"ip": request.client.host if request.client else None,
            "device": _device_from_ua(request.headers.get("user-agent"))}


def get_current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    payload = decode_token(auth.removeprefix("Bearer ").strip())
    if not payload:
        raise HTTPException(401, "Session expired or invalid. Please sign in again.")
    user = db.query(User).filter(User.id == int(payload["sub"]), User.active == True).first()  # noqa: E712
    if not user:
        raise HTTPException(401, "Account not found or deactivated")
    return Principal(user, db)


def require_roles(*roles):
    def checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in roles:
            audit(principal.db, principal, "ACCESS_DENIED",
                  purpose=f"role {principal.role} not in {roles}",
                  ip=None, device=None, result="DENIED")
            raise HTTPException(403, "You do not have permission for this action")
        return principal
    return checker


def require_admin_role(principal: Principal = Depends(get_current_principal)) -> Principal:
    """Strongest protection: admin-only endpoints."""
    return require_roles("ADMIN")(principal)
