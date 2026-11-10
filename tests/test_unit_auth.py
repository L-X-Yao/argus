"""Unit tests for authentication flow.

Tests token generation, validation, middleware behavior, file I/O,
auth-disable mode, and concurrent access patterns.
"""

import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backend.auth as auth_module
from backend.app import app
from backend.auth import TOKEN_FILE, auth_required, generate_token, verify_token
from backend.drone_link import DroneLink
from backend.ws_manager import WSManager


@pytest.fixture(autouse=True)
def _reset_auth_state():
    """Reset auth module state before and after each test."""
    auth_module._token = None
    old_env = os.environ.pop("GCS_AUTH_TOKEN", None)
    existed = TOKEN_FILE.exists()
    if existed:
        backup = TOKEN_FILE.read_text()
        TOKEN_FILE.unlink()
    yield
    auth_module._token = None
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
    if existed:
        TOKEN_FILE.write_text(backup)
    if old_env is not None:
        os.environ["GCS_AUTH_TOKEN"] = old_env
    else:
        os.environ.pop("GCS_AUTH_TOKEN", None)


@pytest.fixture
def client():
    """FastAPI TestClient with app state initialized."""
    if not hasattr(app.state, "link"):
        app.state.link = DroneLink()
        app.state.ws_mgr = WSManager(app.state.link)
    return TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


class TestTokenGeneration:
    def test_token_is_32_hex_chars(self):
        token = generate_token()
        assert len(token) == 32
        assert all(c in "0123456789abcdef" for c in token)

    def test_token_is_different_each_time(self):
        t1 = generate_token()
        auth_module._token = None
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        t2 = generate_token()
        assert t1 != t2

    def test_token_file_created_on_generate(self):
        assert not TOKEN_FILE.exists()
        generate_token()
        assert TOKEN_FILE.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file mode not applicable on Windows (uses ACLs instead)")
    def test_token_file_has_correct_permissions(self):
        generate_token()
        mode = TOKEN_FILE.stat().st_mode & 0o777
        assert mode == 0o600, f"Expected 0600, got {oct(mode)}"


class TestTokenValidation:
    def test_correct_token_passes(self):
        token = generate_token()
        assert verify_token(token) is True

    def test_wrong_token_fails(self):
        generate_token()
        assert verify_token("aaaabbbbccccddddeeeeffffgggghhhh") is False

    def test_empty_string_fails_when_auth_active(self):
        generate_token()
        assert verify_token("") is False

    def test_partial_token_fails(self):
        token = generate_token()
        assert verify_token(token[:16]) is False

    def test_token_from_file_read(self):
        """Token written to file can be read back for validation."""
        token = generate_token()
        auth_module._token = None  # force reload from file
        assert verify_token(token) is True

    def test_env_token_validation(self):
        """GCS_AUTH_TOKEN environment variable is accepted."""
        os.environ["GCS_AUTH_TOKEN"] = "env_secret_token_12345678"
        assert verify_token("env_secret_token_12345678") is True
        assert verify_token("wrong_value") is False


class TestNonAsciiTokens:
    def test_wrong_non_ascii_token_fails_without_raising(self):
        generate_token()
        assert verify_token("令牌") is False

    def test_non_ascii_configured_token_passes(self):
        os.environ["GCS_AUTH_TOKEN"] = "令牌123"
        assert verify_token("令牌123") is True

    def test_login_with_a_wrong_non_ascii_token_returns_401(self, client):
        generate_token()
        r = client.post("/api/auth/login", json={"token": "令牌"})
        assert r.status_code == 401


class TestAuthDisableMode:
    def test_no_token_means_auth_not_required(self):
        assert auth_required() is False

    def test_no_token_allows_any_value(self):
        assert verify_token("anything_at_all") is True

    def test_no_token_allows_empty_string(self):
        assert verify_token("") is True


class TestProtectedEndpoints:
    def test_unauthenticated_request_rejected(self, client):
        """Protected endpoint rejects requests without valid token."""
        generate_token()
        r = client.get("/api/session")
        assert r.status_code == 401
        data = r.json()
        assert data["error"] == "unauthorized"

    def test_authenticated_request_passes(self, client):
        """Protected endpoint accepts requests with valid token."""
        token = generate_token()
        r = client.get("/api/session", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_query_param_token_rejected_for_http(self, client):
        """Token in query params is not accepted for HTTP — must use Authorization header."""
        token = generate_token()
        r = client.get(f"/api/session?token={token}")
        assert r.status_code == 401

    def test_health_endpoint_bypasses_auth(self, client):
        """Health endpoint is always accessible regardless of auth."""
        generate_token()
        r = client.get("/health")
        assert r.status_code == 200

    def test_login_endpoint_bypasses_auth(self, client):
        """Login endpoint is accessible without token."""
        token = generate_token()
        r = client.post("/api/auth/login", json={"token": token})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_login_with_bad_token_returns_401(self, client):
        generate_token()
        r = client.post("/api/auth/login", json={"token": "totally_wrong"})
        assert r.status_code == 401


class TestLoginBody:
    @pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b'"text"', b"\xff\xfe", b""])
    def test_a_body_that_is_no_json_object_is_a_wrong_token(self, client, body):
        generate_token()
        r = client.post("/api/auth/login", content=body, headers={"content-type": "application/json"})
        assert (r.status_code, r.json()) == (401, {"ok": False, "error": "invalid token"})


class TestSessionCookie:
    TOKEN = "cookie_test_token_123456"

    @pytest.fixture(autouse=True)
    def _configured_token(self):
        os.environ["GCS_AUTH_TOKEN"] = self.TOKEN

    def login(self, client):
        return client.post("/api/auth/login", json={"token": self.TOKEN})

    def test_login_sets_a_protected_session_cookie(self, client):
        cookie = self.login(client).headers["set-cookie"]
        assert cookie.startswith(auth_module.COOKIE_NAME + "=")
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Path=/" in cookie
        assert "Secure" not in cookie
        assert "Max-Age" not in cookie
        assert self.TOKEN not in cookie

    def test_cookie_is_secure_over_https(self):
        https_client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
        assert "Secure" in self.login(https_client).headers["set-cookie"]

    def test_failed_login_sets_no_cookie(self, client):
        r = client.post("/api/auth/login", json={"token": "wrong"})
        assert r.status_code == 401
        assert "set-cookie" not in r.headers

    def test_login_without_auth_sets_no_cookie(self, client):
        del os.environ["GCS_AUTH_TOKEN"]
        r = client.post("/api/auth/login", json={"token": "anything"})
        assert r.json() == {"ok": True}
        assert "set-cookie" not in r.headers

    def test_non_ascii_token_gets_a_usable_cookie(self, client):
        os.environ["GCS_AUTH_TOKEN"] = "令牌 ; 123"
        r = client.post("/api/auth/login", json={"token": "令牌 ; 123"})
        assert r.status_code == 200
        assert client.get("/api/ports").status_code == 200

    def test_cookie_authorizes_rest(self, client):
        assert client.get("/api/ports").status_code == 401
        self.login(client)
        assert client.get("/api/ports").status_code == 200

    @pytest.mark.parametrize("value", ["forged", TOKEN])
    def test_other_cookie_values_are_rejected(self, client, value):
        client.cookies.set(auth_module.COOKIE_NAME, value)
        assert client.get("/api/ports").status_code == 401

    def test_non_ascii_cookie_is_rejected_without_raising(self):
        assert auth_module._verify_cookie("令牌") is False

    def test_cookie_stops_working_when_the_token_changes(self, client):
        self.login(client)
        auth_module._token = "another_token_1234567890"
        assert client.get("/api/ports").status_code == 401

    def test_wrong_bearer_is_not_rescued_by_the_cookie(self, client):
        self.login(client)
        r = client.get("/api/ports", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401

    def test_write_from_a_foreign_origin_is_rejected(self, client):
        self.login(client)
        r = client.post("/api/tile_cache_clear", headers={"origin": "http://evil.example"})
        assert r.status_code == 403

    def test_write_from_an_allowed_origin_passes(self, client):
        self.login(client)
        r = client.post("/api/firmware/download", json={}, headers={"origin": "http://localhost:8100"})
        assert r.json() == {"ok": False, "error": "Invalid params"}

    def test_write_without_an_origin_header_passes(self, client):
        self.login(client)
        r = client.post("/api/firmware/download", json={})
        assert r.json() == {"ok": False, "error": "Invalid params"}

    def test_read_from_a_foreign_origin_passes_the_cookie_check(self, client):
        self.login(client)
        assert client.get("/api/ports", headers={"origin": "http://evil.example"}).status_code == 200

    def test_bearer_write_is_not_subject_to_the_origin_rule(self, client):
        r = client.post(
            "/api/firmware/download",
            json={},
            headers={"Authorization": "Bearer " + self.TOKEN, "origin": "http://evil.example"},
        )
        assert r.json() == {"ok": False, "error": "Invalid params"}

    @pytest.mark.parametrize("site", ["same-site", "cross-site"])
    def test_requests_from_other_pages_are_rejected(self, client, site):
        self.login(client)
        assert client.get("/api/video/stop", headers={"sec-fetch-site": site}).status_code == 403

    @pytest.mark.parametrize("site", ["same-origin", "none"])
    def test_requests_from_the_own_page_pass(self, client, site):
        self.login(client)
        assert client.get("/api/ports", headers={"sec-fetch-site": site}).status_code == 200

    def test_bearer_is_not_subject_to_fetch_metadata(self, client):
        headers = {"Authorization": "Bearer " + self.TOKEN, "sec-fetch-site": "cross-site"}
        assert client.get("/api/ports", headers=headers).status_code == 200

    def test_lone_surrogate_in_the_token_returns_401(self, client):
        r = client.post("/api/auth/login", content='{"token": "\\ud800"}')
        assert r.status_code == 401

    def test_public_path_check_does_not_trust_request_url(self, client, monkeypatch):
        monkeypatch.setattr(Request, "url", property(lambda self: URL("http://x/health")))
        assert client.get("/api/ports").status_code == 401

    def test_websocket_opens_with_its_token_parameter(self, client):
        with client.websocket_connect("/ws?token=" + self.TOKEN) as ws:
            ws.send_json({"type": "disconnect"})

    @pytest.mark.parametrize("url", ["/ws", "/ws?token=wrong"])
    def test_websocket_without_the_right_token_closes_4001(self, client, url):
        self.login(client)
        with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect(url):
            pass
        assert closed.value.code == 4001


class TestRequestsFromOtherPages:
    """Without a token, a browser would otherwise let any website reach these routes."""

    @pytest.mark.parametrize("origin", ["http://evil.example", "http://localhost:9999", "null"])
    def test_write_from_a_foreign_origin_is_rejected(self, client, origin):
        r = client.post("/api/tile_cache_clear", headers={"origin": origin})
        assert r.status_code == 403

    def test_foreign_page_cannot_lock_the_operator_out(self, client):
        r = client.post("/api/auth/generate", headers={"origin": "http://evil.example"})
        assert r.status_code == 403
        assert not TOKEN_FILE.exists()

    @pytest.mark.parametrize("site", ["same-site", "cross-site"])
    def test_image_load_from_another_page_is_rejected(self, client, site):
        r = client.get("/api/video/stop", headers={"sec-fetch-site": site, "sec-fetch-dest": "image"})
        assert r.status_code == 403

    @pytest.mark.parametrize("site", ["same-origin", "none"])
    def test_own_page_passes(self, client, site):
        assert client.get("/api/ports", headers={"sec-fetch-site": site}).status_code == 200

    @pytest.mark.parametrize("origin", ["http://localhost:8100", "http://127.0.0.1:5173", "http://localhost:8100/"])
    def test_write_from_an_allowed_origin_passes(self, client, origin):
        r = client.post("/api/firmware/download", json={}, headers={"origin": origin})
        assert r.json() == {"ok": False, "error": "Invalid params"}

    def test_allowed_origin_on_another_port_passes(self, client):
        headers = {"origin": "http://localhost:5173", "sec-fetch-site": "same-site"}
        assert client.get("/api/ports", headers=headers).status_code == 200

    def test_scripts_without_browser_headers_pass(self, client):
        assert client.get("/api/ports").status_code == 200
        assert client.post("/api/firmware/download", json={}).json() == {"ok": False, "error": "Invalid params"}

    def test_request_with_authorization_skips_the_page_check(self, client):
        headers = {"Authorization": "Bearer x", "origin": "http://evil.example"}
        r = client.post("/api/firmware/download", json={}, headers=headers)
        assert r.json() == {"ok": False, "error": "Invalid params"}

    def test_routes_outside_the_api_are_not_checked(self, client):
        assert client.get("/health", headers={"sec-fetch-site": "cross-site"}).status_code == 200


class TestRequestsUnderAnotherName:
    """DNS rebinding: a hostile page gets its own name pointed at this machine, and is then
    same-origin with us to the browser. Only the Host header still gives it away."""

    REBOUND = {"host": "evil.example:8100"}

    @pytest.mark.parametrize("path", ["/api/session", "/api/log", "/api/video/stop", "/api/auth/status"])
    def test_read_is_refused(self, client, path):
        r = client.get(path, headers=self.REBOUND)
        assert (r.status_code, r.json()) == (403, {"error": "host not allowed"})

    def test_write_with_any_authorization_header_is_refused(self, client):
        # Same-origin to the browser, so the page may add the header that skips the page check.
        headers = {**self.REBOUND, "origin": "http://evil.example:8100", "Authorization": "x"}
        assert client.post("/api/tile_cache_clear", headers=headers).status_code == 403

    def test_rebound_page_cannot_lock_the_operator_out(self, client):
        r = client.post("/api/auth/generate", headers={**self.REBOUND, "Authorization": "x"})
        # By this rule, and not by the route's own check of the peer address, which refuses
        # the test client whatever its Host says.
        assert (r.status_code, r.json()) == (403, {"error": "host not allowed"})
        assert not TOKEN_FILE.exists()

    @pytest.mark.parametrize(
        "host",
        [
            "0.0.0.0:8100",
            "192.168.1.5:8100",
            "localhost.evil.example",
            "[::]:8100",
            "",
            # Forms no browser sends, read strictly all the same.
            "[::1].evil.example:8100",
            "[::1]evil.example",
            "[localhost]",
            "[127.0.0.1]:8100",
            "localhost:8100:evil.example",
            "evil.example@localhost",
            "localhost:port",
            "localhost evil.example",
        ],
    )
    def test_other_names_for_this_machine_are_refused(self, client, host):
        assert client.get("/api/ports", headers={"host": host}).status_code == 403

    @pytest.mark.parametrize(
        "host",
        [
            "localhost:8100",
            "localhost",
            "LOCALHOST:5173",
            "localhost.:8100",
            "127.0.0.1:8100",
            "127.0.0.2",
            "[::1]:8100",
        ],
    )
    def test_loopback_names_pass(self, client, host):
        assert client.get("/api/ports", headers={"host": host}).status_code == 200

    def test_host_of_a_configured_origin_passes(self, client):
        # Not monkeypatch.setattr: since pytest 9.2 it restores from the instance __dict__, which
        # app.state does not keep its values in, and so deletes own_hosts for every later test.
        with patch.object(app.state, "own_hosts", {"gcs.example"}):
            assert client.get("/api/ports", headers={"host": "gcs.example:8100"}).status_code == 200
            assert client.get("/api/ports", headers={"host": "other.example:8100"}).status_code == 403
        assert app.state.own_hosts == {"localhost", "127.0.0.1"}

    def test_default_origins_name_this_machine_only(self):
        from backend.app import _cors_origins
        from backend.auth import _is_this_machine

        assert app.state.own_hosts == {"localhost", "127.0.0.1"}
        assert all(_is_this_machine(host) for host in app.state.own_hosts), _cors_origins

    def test_with_a_token_the_name_is_not_checked(self, client):
        # The page has neither the token nor the cookie, which belong to the real name.
        token = generate_token()
        assert client.get("/api/ports", headers=self.REBOUND).status_code == 401
        headers = {**self.REBOUND, "Authorization": f"Bearer {token}"}
        assert client.get("/api/ports", headers=headers).status_code == 200

    def test_routes_outside_the_api_are_not_checked(self, client):
        assert client.get("/health", headers=self.REBOUND).status_code == 200


class TestConcurrentAuth:
    def test_concurrent_verify_no_race(self):
        """Multiple threads verifying simultaneously should not corrupt state."""
        token = generate_token()
        results = []
        errors = []

        def worker():
            try:
                for _ in range(50):
                    r = verify_token(token)
                    results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Got errors: {errors}"
        assert all(r is True for r in results)

    def test_concurrent_verify_wrong_token(self):
        """Multiple threads verifying wrong tokens should all fail safely."""
        generate_token()
        results = []
        errors = []

        def worker():
            try:
                for _ in range(50):
                    r = verify_token("wrong_token_value_here!!")
                    results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r is False for r in results)
