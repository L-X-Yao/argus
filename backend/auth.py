"""Simple token-based authentication for remote operation mode."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import socket
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


# A name or an IPv4 address, or an IPv6 address in brackets, then perhaps a port: nothing
# else, so that "[::1].evil.example" is not read as ::1.
_HOST = re.compile(r"(?:\[(?P<v6>[0-9a-f.]*:[0-9a-f:.]*)\]|(?P<name>[^\[\]:/@\s]+))(?::\d{1,5})?\Z")


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
    match = _HOST.match(request.headers.get("host", "").strip().lower())
    if not match:
        return False
    if match["v6"] is not None:
        return match["v6"] == "::1" or match["v6"] in request.app.state.own_hosts
    return _is_this_machine(match["name"]) or match["name"] in request.app.state.own_hosts


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


def _address_on_the_network() -> str | None:
    """This machine's address as another device sees it. Connecting a UDP socket sends
    nothing: it only asks the system which of its addresses leads outward."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            address = probe.getsockname()[0]
    except OSError:
        return None
    return None if _is_this_machine(address) else address


def _origin(address: str, port: int) -> str:
    """The Origin header a browser sends for a page at http://address:port. _from_own_page
    compares it with ARGUS_CORS_ORIGINS as text, so it has to be written the browser's way: a
    name in lower case, an IPv6 address short and in brackets, and no port when it is 80."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        host = address.lower()
    else:
        host = f"[{ip.compressed}]" if ip.version == 6 else ip.compressed
    return f"http://{host}" if port == 80 else f"http://{host}:{port}"


def note_for_other_devices(host: str, port: int, origins: list[str]) -> str | None:
    """What to say at start when Argus listens beyond this machine. A page opened from another
    device is let in only under an address in ARGUS_CORS_ORIGINS (see _from_own_page), and on
    that device the refusal shows up at the login, where nobody can tell what is missing."""
    if _is_this_machine(host):
        return None
    try:
        ip = ipaddress.ip_address(host) if host else None
    except ValueError:
        ip = None
    if ip is not None and ip.is_unspecified and ip.version == 6:
        # asyncio binds "::" for IPv6 only, so no IPv4 address reaches it.
        return (
            "Listening on every IPv6 interface. A page opened from another device needs its "
            f"address in ARGUS_CORS_ORIGINS, for example {_origin('fd00::5', port)}."
        )
    guessed = not host or (ip is not None and ip.is_unspecified)
    address = _address_on_the_network() if guessed else host
    if address is None:
        return (
            "Listening on every interface. A page opened from another device needs its address "
            f"in ARGUS_CORS_ORIGINS, for example {_origin('192.168.1.5', port)}."
        )
    origin = _origin(address, port)
    # The address on the default route: a hotspot this machine provides, a VPN or a second
    # network card can each put the other device on another one.
    lines = [
        f"From another device, open {origin}" + (", this machine's address on its main network." if guessed else ".")
    ]
    if origin not in origins:
        lines += [
            "ARGUS_CORS_ORIGINS does not list it, so the login of a page opened there is refused. "
            "Set ARGUS_CORS_ORIGINS to",
            "  " + ",".join([*origins, origin]),
            "and start Argus again.",
        ]
    if guessed:
        lines.append("A page opened at another address and refused at login names the address to add.")
    return "\n".join(lines)


def verify_ws_token(ws: WebSocket) -> bool:
    if not auth_required():
        return True
    token = ws.query_params.get("token", "")
    return verify_token(token)
