"""Roles, rate limits, safe inputs, and the headers a browser should be told to enforce."""
import hashlib
import hmac
import os
import re

from fastapi import HTTPException, Request, Response, status

ADMIN_COOKIE = "rehnuma_admin"

# Hard ceilings, independent of the admin-configurable settings. A config mistake
# must not be able to open the door wider than this.
MAX_MESSAGE_CHARS = 4_000
MAX_PASTE_CHARS = 200_000
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def _secret() -> bytes:
    raw = os.environ.get("SECRET_KEY") or os.environ.get("ADMIN_PASSWORD") or "rehnuma-dev-only"
    return hashlib.sha256(raw.encode()).digest()


def _admin_token() -> str:
    return hmac.new(_secret(), b"admin-session", hashlib.sha256).hexdigest()


def admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD", "rehnuma")


def check_password(candidate: str) -> bool:
    # constant-time compare so the endpoint cannot be used as an oracle
    return hmac.compare_digest((candidate or "").encode(), admin_password().encode())


def grant_admin(response: Response):
    response.set_cookie(
        ADMIN_COOKIE, _admin_token(),
        httponly=True, samesite="strict",
        secure=os.environ.get("RENDER") is not None,  # HTTPS-only once deployed
        max_age=60 * 60 * 8, path="/",
    )


def revoke_admin(response: Response):
    response.delete_cookie(ADMIN_COOKIE, path="/")


def is_admin(request: Request) -> bool:
    got = request.cookies.get(ADMIN_COOKIE, "")
    return bool(got) and hmac.compare_digest(got, _admin_token())


def require_admin(request: Request):
    """FastAPI dependency guarding every admin route."""
    if not is_admin(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin sign-in required.")
    return True


# ---------------------------------------------------------------- inputs

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str, limit: int) -> str:
    """Strip control characters and cap length. Not an injection defence on its own -
    the real defence is in the prompt, which marks uploaded content as data, never
    instructions - but it stops malformed input reaching the model or the database."""
    if value is None:
        return ""
    value = _CONTROL.sub("", str(value))
    return value[:limit].strip()


def safe_id(value: str) -> str:
    """Identifiers are ours - hex only. Rejects anything shaped like an injection."""
    v = re.sub(r"[^a-zA-Z0-9]", "", str(value or ""))[:32]
    if not v:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid identifier.")
    return v


# --------------------------------------------------------------- headers

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(self)",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' https://cdnjs.cloudflare.com 'unsafe-inline'; "
        "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response
