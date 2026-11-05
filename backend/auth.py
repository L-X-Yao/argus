"""Simple token-based authentication for remote operation mode."""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from fastapi import Request, Response, WebSocket
from fastapi.responses import JSONResponse

TOKEN_FILE = Path(__file__).resolve().parent.parent / ".gcs_token"
COOKIE_NAME = "argus_session"
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
_token: str | None = None


def _load_token() -> str | None:
    global _token
    if _token:
        return _token
    if TOKEN_FILE.exists():
        _token = TOKEN_FILE.read_text().strip()
        return _token
    env_token = os.environ.get("GCS_AUTH_TOKEN")
    if env_token:
        _token = env_token
        return _token
    return None


def generate_token() -> str:
    token = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    fd = os.open(str(TOKEN_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode())
    finally:
        os.close(fd)
    global _token
    _token = token
    return token


def verify_token(provided: str) -> bool:
    expected = _load_token()
    if not expected:
        return True
    # hmac.compare_digest raises TypeError on non-str/bytes input (e.g. null,
    # int, list from a malformed JSON body). Reject those upfront as invalid
    # rather than letting the 500 leak.
    if not isinstance(provided, (str, bytes)):
        return False
    # Compare bytes: for str, compare_digest raises on non-ASCII input.
    if isinstance(provided, str):
        provided = _utf8(provided)
    return hmac.compare_digest(provided, _utf8(expected))


def _utf8(text: str) -> bytes:
    # surrogatepass: a JSON body can hold a lone surrogate, which encode() rejects.
    return text.encode("utf-8", "surrogatepass")


def _cookie_value(token: str) -> str:
    # A keyed digest, not the token: any token text stays valid in a cookie
    # header, and the cookie stops working when the token changes.
    return hmac.new(_utf8(token), b"argus-session", hashlib.sha256).hexdigest()


def set_session_cookie(response: Response, secure: bool) -> None:
    """Authorize this browser. Map tiles load as images and cannot carry a header."""
    response.set_cookie(
        COOKIE_NAME,
        _cookie_value(_load_token()),
        httponly=True,
        samesite="strict",
        secure=secure,
    )


def _verify_cookie(value: str) -> bool:
    return hmac.compare_digest(_utf8(value), _utf8(_cookie_value(_load_token())))


def _from_own_page(request: Request) -> bool:
    """Browsers attach the cookie on their own, and SameSite does not separate ports on one host."""
    # Fetch metadata covers every request, image loads included, but browsers
    # only send it on https and localhost. Origin covers writes everywhere.
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return False
    origin = (request.headers.get("origin") or "").rstrip("/")
    return request.method in SAFE_METHODS or not origin or origin in request.app.state.cors_origins


def auth_required() -> bool:
    return _load_token() is not None


async def auth_middleware(request: Request, call_next):
    if not auth_required():
        return await call_next(request)
    # Not request.url.path: older Starlette builds it from the Host header.
    path = request.scope["path"]
    # `/sw.js` and `/manifest.json` MUST be reachable without an Authorization
    # header — browsers don't send auth on service-worker installs or manifest
    # fetches, and a 401 here breaks PWA install/refresh entirely.
    if (
        path in ("/health", "/", "/index.html", "/sw.js", "/manifest.json")
        or path.startswith("/assets")
        or path.startswith("/lib")
        or path.startswith("/images")
    ):
        return await call_next(request)
    if path in ("/api/auth/login", "/api/auth/status"):
        return await call_next(request)
    header = request.headers.get("Authorization")
    if header is not None:
        if not verify_token(header.replace("Bearer ", "")):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        return await call_next(request)
    if not _verify_cookie(request.cookies.get(COOKIE_NAME, "")):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    if not _from_own_page(request):
        return JSONResponse(status_code=403, content={"error": "origin not allowed"})
    return await call_next(request)


def verify_ws_token(ws: WebSocket) -> bool:
    if not auth_required():
        return True
    token = ws.query_params.get("token", "")
    return verify_token(token)
