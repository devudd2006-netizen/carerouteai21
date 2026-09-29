"""CareRoute AI — authentication primitives: password hashing, JWTs, MFA (OTP) flow,
device passkey-style credential simulation. No raw biometric data is ever stored."""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from jose import JWTError, jwt

from config import settings

# PBKDF2-SHA256 password hashing (stdlib, no external dependency issues).
_PBKDF2_ITERATIONS = 240_000

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, iters, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def create_access_token(user_id: int, role: str, minutes: int | None = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "exp": expire, "typ": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("typ") != "access":
            return None
        return payload
    except JWTError:
        return None


# ----------------------------------------------------------------- MFA / OTP
def generate_otp() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def otp_expiry(minutes: int = 5) -> datetime:
    return datetime.utcnow() + timedelta(minutes=minutes)


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


# ------------------------------------------- device passkey-style credential
def generate_device_challenge() -> str:
    return secrets.token_urlsafe(32)


def enroll_device_secret(user_id: int, device_name: str) -> tuple[str, str]:
    """Returns (device_secret_shown_once, secret_hash). The secret itself is NOT stored."""
    secret = secrets.token_urlsafe(32)
    return secret, hash_password(f"{user_id}:{device_name}:{secret}")


def verify_device_secret(user_id: int, device_name: str, secret: str, secret_hash: str) -> bool:
    return verify_password(f"{user_id}:{device_name}:{secret}", secret_hash)
