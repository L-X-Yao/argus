"""Simple token-based authentication for remote operation mode."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import socket
import tempfile
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
        token = TOKEN_FILE.read_text().strip()
        if token:
            _token = token
            return _token
        # A blank file is no token (audit 2026-11-16 H1): a crash between the
        # old O_TRUNC and the write used to leave one, and it must not disable
        # auth while the startup guard already believed a token exists. Fall
        # through to the environment.
    env_token = os.environ.get("GCS_AUTH_TOKEN")
    if env_token:
        _token = env_token
        return _token
    return None


def generate_token() -> str:
    token = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    global _token
    # Temp file + fsync + rename (audit 2026-11-16 H1): the old in-place
    # O_TRUNC write could be interrupted into a blank file, which reads as no
    # token. A reader now sees the old token or the new one, never blank.
    fd, tmp = tempfile.mkstemp(dir=str(TOKEN_FILE.parent), prefix=".gcs_token.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(token)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, TOKEN_FILE)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _token = token
    return token


def verify_token(provided: str) -> bool:
    expected = _load_token()
    if not expected:
        # No token configured — or a blank one (H1): there is nothing to
        # verify, and a yes here accepted every secret against a server whose
        # startup guard had already passed because auth_required() was True.
        return False
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


_V6_CHARS = frozenset("0123456789abcdef.:")
_NAME_BAD = frozenset("[]:/@")


def _is_this_machine(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower().rstrip(".") == "localhost"


def _port_ok(rest: str) -> bool:
    """'' or a colon and one to five digits, the forms a Host header has always been read for."""
    if not rest:
        return True
    digits = rest[1:]
    return rest.startswith(":") and 1 <= len(digits) <= 5 and all(c in "0123456789" for c in digits)


def _host_is_ours(host_header: str, own_hosts: set[str]) -> bool:
    """Tell the names we answer to from one that another site has pointed at this machine.
    After DNS rebinding a hostile page is same-origin with us to the browser: it sends no
    Origin on a read, no Fetch Metadata, and may add any header. Only Host still names it.
    0.0.0.0 reaches this machine too, from any page, and browsers send it no Fetch Metadata.

    Read by hand, not by a regex: the header is reachable before any token check, and a
    backtracking pattern there is a quadratic path on one long line of punctuation
    (CodeQL py/polynomial-redos, 2026-11-18)."""
    host = host_header.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        if end < 0:
            return False
        name, rest = host[1:end], host[end + 1 :]
        if ":" not in name or any(c not in _V6_CHARS for c in name):
            return False
        return _port_ok(rest) and (name == "::1" or name in own_hosts)
    name, sep, port = host.partition(":")
    if not name or any(c in _NAME_BAD or c.isspace() for c in name):
        return False
    if sep and (":" in port or not _port_ok(":" + port)):
        return False
    return _is_this_machine(name) or name in own_hosts


def _asked_by_our_name(request: Request) -> bool:
    return _host_is_ours(request.headers.get("host", ""), request.app.state.own_hosts)


def auth_required() -> bool:
    return _load_token() is not None


def _addr_is_this_machine(client) -> bool:
    """The peer's address, not the name it asked by (audit 2026-11-16 L18).
    The two entry points refuse a bind beyond this machine without a token,
    but a direct `uvicorn backend.app:app --host 0.0.0.0` skips them; this
    holds whoever it is asked by. An address that is not one — the test
    client's "testclient" — cannot be judged and passes; uvicorn always
    provides one."""
    if client is None:
        return True
    try:
        addr = ipaddress.ip_address(client.host)
    except ValueError:
        return True
    return addr.is_loopback


def _from_this_machine(request: Request) -> bool:
    return _addr_is_this_machine(request.client)


async def auth_middleware(request: Request, call_next):
    # Not request.url.path: older Starlette builds it from the Host header.
    path = request.scope["path"]
    # A preflight from a page in ARGUS_CORS_ORIGINS goes straight through to
    # the CORS middleware (audit 2026-11-16 L19): it carries no Authorization
    # by design, and the token gate answered it 401, so cross-origin JSON
    # POSTs from an allowed page never ran. Only OPTIONS is let through
    # early, and only for an origin the list already allows — the CORS
    # middleware still answers nothing to any other origin.
    if (
        request.method == "OPTIONS"
        and (request.headers.get("origin") or "").rstrip("/") in request.app.state.cors_origins
    ):
        return await call_next(request)
    # Holds with or without a token. Another site's page cannot set Authorization
    # without a CORS preflight, so a request that carries it is not such a page.
    if path.startswith("/api/") and "Authorization" not in request.headers and not _from_own_page(request):
        return JSONResponse(status_code=403, content={"error": "origin not allowed"})
    if not auth_required():
        # And only this machine talks to it, whatever it asks by (L18): the
        # peer's address, then the name it used (L17).
        if not _from_this_machine(request):
            return JSONResponse(status_code=403, content={"error": "client address not allowed"})
        # Nothing else stands between a page and the server here, and the rule
        # above lets any request with an Authorization header through. Every
        # path is held to our names, not only /api: SECURITY.md promises
        # answers to a loopback name alone, and /docs or /openapi.json under a
        # rebinding name read the whole API schema (audit 2026-11-16 L17).
        if not _asked_by_our_name(request):
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


def ws_exposure_error(ws: WebSocket) -> str | None:
    """The no-token rule for a websocket handshake (audit 2026-11-16 L18/L17).

    `auth_middleware` is an HTTP middleware: Starlette never runs it for a
    websocket scope, so the handshake has to ask the same two questions
    itself, or a direct `uvicorn backend.app:app --host 0.0.0.0` with no
    token hands the command surface to any client that sends no Origin.
    """
    if not _addr_is_this_machine(ws.client):
        return "client address not allowed"
    if not _host_is_ours(ws.headers.get("host", ""), ws.app.state.own_hosts):
        return "host not allowed"
    return None


def verify_ws_token(ws: WebSocket) -> bool:
    if not auth_required():
        return True
    token = ws.query_params.get("token", "")
    return verify_token(token)


def verify_ws_cookie(ws: WebSocket) -> bool:
    """The handshake cookie a logged-in page carries, in place of a token in
    the URL (audit 2026-11-16 L15). Empty when no token is configured, which
    the caller answers for first."""
    return _verify_cookie(ws.cookies.get(COOKIE_NAME, ""))
