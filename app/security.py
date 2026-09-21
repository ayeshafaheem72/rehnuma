"""Roles, rate limits, safe inputs, and the headers a browser should be told to enforce."""
import hashlib
import hmac
import os
import re
import secrets
import time

from fastapi import HTTPException, Request, Response, status
from starlette.datastructures import MutableHeaders

ADMIN_COOKIE = "rehnuma_admin"
ADMIN_TTL_S = 60 * 60 * 8

# Render sets RENDER on every service it runs. Everything that must be strict in
# production but convenient on a laptop keys off this one flag.
IS_PROD = bool(os.environ.get("RENDER"))

# Hard ceilings, independent of the admin-configurable settings. A config mistake
# must not be able to open the door wider than this.
MAX_MESSAGE_CHARS = 4_000
MAX_PASTE_CHARS = 200_000
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

# With no configured secret in production the key is random per process: admin sessions
# then end on restart, which is the safe way to fail.
_PROCESS_SECRET = secrets.token_bytes(32)


def _secret() -> bytes:
    raw = os.environ.get("SECRET_KEY") or os.environ.get("ADMIN_PASSWORD")
    if raw:
        return hashlib.sha256(raw.encode()).digest()
    return _PROCESS_SECRET if IS_PROD else hashlib.sha256(b"rehnuma-dev-only").digest()


def admin_password() -> str:
    """No built-in password in production: an unset one means admin sign-in is off,
    never that it is guessable. The fallback exists for a local checkout only."""
    pw = os.environ.get("ADMIN_PASSWORD")
    if pw:
        return pw
    return "" if IS_PROD else "rehnuma"


def check_password(candidate: str) -> bool:
    expected = admin_password()
    if not expected:
        return False
    # constant-time compare so the endpoint cannot be used as an oracle
    return hmac.compare_digest((candidate or "").encode(), expected.encode())


def _sign(expires: int) -> str:
    return hmac.new(_secret(), f"admin|{expires}".encode(), hashlib.sha256).hexdigest()


def grant_admin(response: Response):
    """The cookie carries its own expiry, signed. Copying it out of a browser therefore
    buys an attacker at most the time that is left on it, not an open-ended session."""
    expires = int(time.time()) + ADMIN_TTL_S
    response.set_cookie(
        ADMIN_COOKIE, f"{expires}.{_sign(expires)}",
        httponly=True, samesite="strict",
        secure=IS_PROD,  # HTTPS-only once deployed
        max_age=ADMIN_TTL_S, path="/",
    )


def revoke_admin(response: Response):
    response.delete_cookie(ADMIN_COOKIE, path="/")


def is_admin(request: Request) -> bool:
    got = request.cookies.get(ADMIN_COOKIE, "")
    stamp, _, sig = got.partition(".")
    if not stamp.isdigit() or not sig:
        return False
    expires = int(stamp)
    return expires > time.time() and hmac.compare_digest(sig, _sign(expires))


def require_admin(request: Request):
    """FastAPI dependency guarding every admin route."""
    if not is_admin(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin sign-in required.")
    return True


def client_ip(request: Request) -> str:
    """The caller's address, for rate limits and the sign-in log.

    Behind Render every socket peer is the proxy, so keying limits on it would make the
    whole panel share one allowance. Cloudflare sets CF-Connecting-IP itself and discards
    any copy a client sends, which is why it is preferred over X-Forwarded-For.
    """
    if IS_PROD:
        for header in ("cf-connecting-ip", "x-real-ip"):
            value = request.headers.get(header)
            if value:
                return value.split(",")[0].strip()[:64]
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[-1].strip()[:64]   # the hop our own proxy appended
    return request.client.host if request.client else "unknown"


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
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(self)",
    # No inline or third-party script: every script is served from this origin. Inline
    # styles stay allowed because the truck-art layout sets a few directly.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "media-src 'self' blob:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}


class SecurityHeadersMiddleware:
    """Plain ASGI rather than @app.middleware("http"): the latter buffers the body path
    in a way that fights streamed replies, and the tutor streams."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope.get("path", "").startswith("/api")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for k, v in SECURITY_HEADERS.items():
                    headers.setdefault(k, v)
                if is_api:
                    headers["Cache-Control"] = "no-store"
                elif "cache-control" not in headers:
                    # Pages and scripts revalidate on every load (a cheap 304 when nothing has
                    # changed). Without this a browser may serve yesterday's script for hours
                    # after a deploy, which is how a fixed bug looks unfixed to the panel.
                    headers["Cache-Control"] = "no-cache"
            await send(message)

        await self.app(scope, receive, send_with_headers)
