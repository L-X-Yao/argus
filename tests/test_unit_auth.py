"""Unit tests for auth module."""
import hashlib
import hmac
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.auth import verify_token, auth_required, generate_token, TOKEN_FILE


class TestAuthNoToken:
    def test_no_token_allows_all(self):
        import backend.auth as auth
        auth._token = None
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        old_env = os.environ.pop('GCS_AUTH_TOKEN', None)
        try:
            assert auth_required() is False
            assert verify_token('anything') is True
        finally:
            if old_env:
                os.environ['GCS_AUTH_TOKEN'] = old_env


class TestAuthWithToken:
    def test_generated_token_verifies(self):
        import backend.auth as auth
        auth._token = None
        token = generate_token()
        assert len(token) == 32
        assert verify_token(token) is True
        assert verify_token('wrong') is False
        assert auth_required() is True
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        auth._token = None

    def test_token_file_permissions(self):
        import backend.auth as auth
        auth._token = None
        generate_token()
        if TOKEN_FILE.exists():
            mode = TOKEN_FILE.stat().st_mode & 0o777
            assert mode == 0o600, f'Token file should be 0600, got {oct(mode)}'
            TOKEN_FILE.unlink()
        auth._token = None

    def test_env_token(self):
        import backend.auth as auth
        auth._token = None
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        os.environ['GCS_AUTH_TOKEN'] = 'test_env_token_123'
        try:
            assert verify_token('test_env_token_123') is True
            assert verify_token('wrong') is False
        finally:
            del os.environ['GCS_AUTH_TOKEN']
            auth._token = None
