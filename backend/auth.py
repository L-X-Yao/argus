"""Simple token-based authentication for remote operation mode."""
from __future__ import annotations
import hashlib
import hmac
import os
import time
from pathlib import Path

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse

from .config import cfg

TOKEN_FILE = Path(__file__).resolve().parent.parent / '.gcs_token'
_token: str | None = None


def _load_token() -> str | None:
    global _token
    if _token:
        return _token
    if TOKEN_FILE.exists():
        _token = TOKEN_FILE.read_text().strip()
        return _token
    env_token = os.environ.get('GCS_AUTH_TOKEN')
    if env_token:
        _token = env_token
        return _token
    return None


def generate_token() -> str:
    token = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    global _token
    _token = token
    return token


def verify_token(provided: str) -> bool:
    expected = _load_token()
    if not expected:
        return True
    return hmac.compare_digest(provided, expected)


def auth_required() -> bool:
    return _load_token() is not None


async def auth_middleware(request: Request, call_next):
    if not auth_required():
        return await call_next(request)
    path = request.url.path
    if path in ('/health', '/', '/index.html') or path.startswith('/assets') or path.startswith('/lib') or path.startswith('/images'):
        return await call_next(request)
    if path == '/api/auth/login':
        return await call_next(request)
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        token = request.query_params.get('token', '')
    if not verify_token(token):
        return JSONResponse(status_code=401, content={'error': 'unauthorized'})
    return await call_next(request)


def verify_ws_token(ws: WebSocket) -> bool:
    if not auth_required():
        return True
    token = ws.query_params.get('token', '')
    return verify_token(token)
