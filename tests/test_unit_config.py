"""Tests for backend/config.py — configuration defaults and env overrides."""

import os
from unittest.mock import patch

import pytest

from backend.config import BodyTooLarge, Config, _env, json_object


class TestEnvHelper:
    def test_returns_default_when_unset(self):
        assert _env("ARGUS_NONEXISTENT_KEY_12345", 42) == 42

    def test_blank_value_counts_as_unset(self):
        with patch.dict(os.environ, {"ARGUS_TEST_BLANK": ""}):
            assert _env("ARGUS_TEST_BLANK", "127.0.0.1") == "127.0.0.1"

    def test_returns_env_value_with_type_cast(self):
        with patch.dict(os.environ, {"ARGUS_TEST_INT": "9999"}):
            assert _env("ARGUS_TEST_INT", 0) == 9999

    def test_string_default(self):
        with patch.dict(os.environ, {"ARGUS_TEST_STR": "hello"}):
            assert _env("ARGUS_TEST_STR", "") == "hello"

    def test_float_cast(self):
        with patch.dict(os.environ, {"ARGUS_TEST_F": "3.14"}):
            assert _env("ARGUS_TEST_F", 0.0) == 3.14

    def test_explicit_cast_function(self):
        with patch.dict(os.environ, {"ARGUS_TEST_CAST": "1"}):
            assert _env("ARGUS_TEST_CAST", False, cast=bool) is True


class TestConfigDefaults:
    def test_host_type(self):
        assert isinstance(Config.HOST, str)

    def test_port_type(self):
        assert isinstance(Config.PORT, int)

    def test_push_intervals(self):
        assert Config.WS_PUSH_INTERVAL_CONNECTED < Config.WS_PUSH_INTERVAL_IDLE

    def test_timeouts_positive(self):
        assert Config.TCP_CONNECT_TIMEOUT > 0
        assert Config.TCP_READ_TIMEOUT > 0
        assert Config.SERIAL_READ_TIMEOUT > 0

    def test_tile_cache_max(self):
        assert Config.TILE_CACHE_MAX > 0


class _FakeRequest:
    """Just what json_object reads: headers and a chunked body stream."""

    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = headers if headers is not None else {"content-length": str(len(body))}
        self.read_to = 0

    async def stream(self):
        # Emulate a real transport: the body arrives in chunks, not at once.
        for i in range(0, len(self._body), 65536):
            self.read_to = i + 65536
            yield self._body[i : i + 65536]


class TestJsonObjectBodyCap:
    """Audit 2026-11-16 M1: a request body past the cap is refused, not buffered."""

    @pytest.mark.asyncio
    async def test_oversized_content_length_is_refused_before_any_read(self):
        request = _FakeRequest(b"", headers={"content-length": str(Config.MAX_JSON_BODY + 1)})
        with pytest.raises(BodyTooLarge):
            await json_object(request)
        assert request.read_to == 0

    @pytest.mark.asyncio
    async def test_a_stream_past_the_cap_is_cut_off_midway(self):
        body = b"x" * (Config.MAX_JSON_BODY + 70000)
        request = _FakeRequest(body, headers={})
        with pytest.raises(BodyTooLarge):
            await json_object(request)
        assert request.read_to < len(body)

    @pytest.mark.asyncio
    async def test_a_body_under_the_cap_parses(self):
        assert await json_object(_FakeRequest(b'{"token": "t"}')) == {"token": "t"}

    @pytest.mark.asyncio
    async def test_what_is_no_json_object_still_answers_empty(self):
        assert await json_object(_FakeRequest(b"[1, 2]")) == {}
        assert await json_object(_FakeRequest(b"")) == {}
