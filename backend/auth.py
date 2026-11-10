"""Simple token-based authentication for remote operation mode."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
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
    """Tell our pages from other sites' pages, which a browser lets reach a local server."""
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin in request.app.state.cors_origins:
        return True
    if origin and request.method not in SAFE_METHODS:
        return False
    # Fetch metadata also covers image loads, which carry no Origin, but browsers
    # only send it on https and localhost.
    return request.headers.get("sec-fetch-site", "same-origin") in ("same-origin", "none")


def _is_this_machine(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower().rstrip(".") == "localhost"


def _asked_by_our_name(request: Request) -> bool:
    """Tell the names we answer to from one that another site has pointed at this machine.
    After DNS rebinding a hostile page is same-origin with us to the browser: it sends no
    Origin on a read, no Fetch Metadata, and may add any header. Only Host still names it.
    0.0.0.0 reaches this machine too, from any page, and browsers send it no Fetch Metadata."""
    host = request.headers.get("host", "").strip().lower()
    name = host[1 : host.find("]")] if host.startswith("[") else host.rsplit(":", 1)[0]
    return _is_this_machine(name) or name in request.app.state.own_hosts


def auth_required() -> bool:
    return _load_token() is not None


async def auth_middleware(request: Request, call_next):
    # Not request.url.path: older Starlette builds it from the Host header.
    path = request.scope["path"]
    # Holds with or without a token. Another site's page cannot set Authorization
    # without a CORS preflight, so a request that carries it is not such a page.
    if path.startswith("/api/") and "Authorization" not in request.headers and not _from_own_page(request):
        return JSONResponse(status_code=403, content={"error": "origin not allowed"})
    if not auth_required():
        # Nothing else stands between a page and the API here, and the rule above lets any
        # request with an Authorization header through.
        if path.startswith("/api/") and not _asked_by_our_name(request):
            return JSONResponse(status_code=403, content={"error": "host not allowed"})
        return await call_next(request)
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
    return await call_next(request)


def refuse_if_exposed(host: str) -> None:
    """Without a token, whoever reaches the websocket can arm the vehicle. That is fine on this
    machine and nowhere else. A blank host binds every interface."""
    if auth_required():
        return
    if not _is_this_machine(host):
        raise SystemExit(
            f"Refusing to listen on {host or 'every interface'} without a token: anyone who can "
            "reach it could arm the vehicle. Set GCS_AUTH_TOKEN, or listen on 127.0.0.1."
        )


def verify_ws_token(ws: WebSocket) -> bool:
    if not auth_required():
        return True
    token = ws.query_params.get("token", "")
    return verify_token(token)
