"""backend/mcp_server.py: MCP on stdio in both eras, and its tools asking the operator's page."""

import json
import socket
import threading
import time

import pytest
import uvicorn
from websockets.sync.client import connect

from backend import mcp_server as mcp
from backend.mcp_server import DECISION_TIMEOUT, LEGACY, MODERN, READ_TIMEOUT, Backend, Server, Unreachable

META = "io.modelcontextprotocol/protocolVersion"
CAPS = "io.modelcontextprotocol/clientCapabilities"


class FakeBackend:
    """The backend as the server sees it. With hold set, a request waits until it is released."""

    def __init__(self, reply=None):
        self.reply = {"ok": True, "result": {"mode": "LOITER"}} if reply is None else reply
        self.asked: list[tuple] = []
        self.hold = threading.Event()
        self.release = threading.Event()
        self.withdrawn = threading.Event()

    def ask(self, kind, args, timeout, cancelled, note=None):
        self.asked.append((kind, args, timeout))
        if self.hold.is_set():
            while not self.release.is_set():
                if cancelled.is_set():
                    self.withdrawn.set()
                    return None
                if note:
                    note(12.0)
                time.sleep(0.01)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class Wire:
    """What the server writes to stdout, as messages."""

    def __init__(self):
        self.out: list[dict] = []
        self._lock = threading.Lock()

    def write(self, msg: dict) -> None:
        json.dumps(msg, allow_nan=False)
        with self._lock:
            self.out.append(msg)

    def answer(self, rid, timeout: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                found = [m for m in self.out if m.get("id") == rid and ("result" in m or "error" in m)]
            if found:
                assert len(found) == 1
                return found[0]
            time.sleep(0.01)
        raise AssertionError(f"no answer to {rid!r}: {self.out}")

    def notifications(self) -> list[dict]:
        with self._lock:
            return [m for m in self.out if "id" not in m]


@pytest.fixture
def wire():
    return Wire()


@pytest.fixture
def page():
    return FakeBackend()


@pytest.fixture
def server(page, wire):
    return Server(page, wire.write)


def send(server: Server, rid, method: str, params: dict | None = None) -> None:
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        msg["id"] = rid
    if params is not None:
        msg["params"] = params
    server.handle_line(json.dumps(msg))


def modern(**params) -> dict:
    return {**params, "_meta": {META: MODERN[0], CAPS: {}, **params.pop("_meta", {})}}


def initialize(server: Server, wire: Wire, version: str = "2025-06-18") -> dict:
    send(
        server,
        0,
        "initialize",
        {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
    )
    send(server, None, "notifications/initialized")
    return wire.answer(0)["result"]


def call(server: Server, wire: Wire, rid, name: str, arguments=None, params: dict | None = None) -> dict:
    send(
        server, rid, "tools/call", {"name": name, "arguments": {} if arguments is None else arguments, **(params or {})}
    )
    return wire.answer(rid)


class TestLegacyEra:
    def test_initialize_takes_a_version_it_knows(self, server, wire):
        result = initialize(server, wire, "2025-03-26")
        assert result["protocolVersion"] == "2025-03-26"
        assert result["capabilities"] == {"tools": {"listChanged": False}}
        assert result["serverInfo"]["name"] == "argus-gcs" and result["instructions"]
        assert "resultType" not in result

    def test_initialize_offers_its_newest_for_a_version_it_does_not_know(self, server, wire):
        assert initialize(server, wire, "2024-01-01")["protocolVersion"] == LEGACY[0]

    def test_tools_are_listed(self, server, wire):
        initialize(server, wire)
        send(server, 1, "tools/list")
        tools = wire.answer(1)["result"]["tools"]
        assert [t["name"] for t in tools] == [
            "get_status",
            "get_mission",
            "get_parameters",
            "propose_mission",
            "propose_parameters",
        ]
        for tool in tools:
            assert tool["description"] and tool["inputSchema"]["type"] == "object"

    def test_a_call_gives_text_and_structured_content(self, server, wire):
        initialize(server, wire, "2025-06-18")
        result = call(server, wire, 1, "get_status")["result"]
        assert result["isError"] is False
        assert json.loads(result["content"][0]["text"]) == {"mode": "LOITER"}
        assert result["structuredContent"] == {"mode": "LOITER"}

    def test_no_structured_content_for_a_version_before_it(self, server, wire):
        initialize(server, wire, "2025-03-26")
        assert "structuredContent" not in call(server, wire, 1, "get_status")["result"]

    def test_ping(self, server, wire):
        send(server, 9, "ping")
        assert wire.answer(9)["result"] == {}


class TestModernEra:
    def test_discover(self, server, wire):
        send(server, "d", "server/discover", modern())
        result = wire.answer("d")["result"]
        assert result["resultType"] == "complete"
        assert result["supportedVersions"] == [*MODERN, *LEGACY]
        assert result["capabilities"] == {"tools": {}}
        assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "argus-gcs"

    def test_a_request_carries_its_own_version_with_no_handshake(self, server, wire):
        send(server, 1, "tools/list", modern())
        result = wire.answer(1)["result"]
        assert result["resultType"] == "complete" and len(result["tools"]) == 5
        result = call(server, wire, 2, "get_status", params={"_meta": modern()["_meta"]})["result"]
        assert result["resultType"] == "complete" and result["structuredContent"] == {"mode": "LOITER"}

    def test_a_request_without_client_capabilities_is_malformed(self, server, wire):
        send(server, 1, "tools/list", {"_meta": {META: MODERN[0]}})
        assert wire.answer(1)["error"]["code"] == -32602

    def test_a_version_it_does_not_serve_is_named_with_those_it_does(self, server, wire):
        send(server, 1, "tools/list", {"_meta": {META: "1900-01-01", CAPS: {}}})
        error = wire.answer(1)["error"]
        assert error["code"] == -32022
        assert error["data"] == {"supported": [*MODERN, *LEGACY], "requested": "1900-01-01"}


class TestMessages:
    def test_text_that_is_no_json(self, server, wire):
        server.handle_line("{not json")
        assert wire.answer(None)["error"]["code"] == -32700

    def test_a_batch_is_no_longer_a_message(self, server, wire):
        server.handle_line(json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"}]))
        assert wire.answer(None)["error"]["code"] == -32600

    @pytest.mark.parametrize("rid", [None, True, 1.5, [1]])
    def test_an_id_that_is_no_string_or_integer(self, server, wire, rid):
        server.handle_line(json.dumps({"jsonrpc": "2.0", "id": rid, "method": "ping"}))
        assert wire.answer(None)["error"]["code"] == -32600

    def test_an_unknown_method(self, server, wire):
        send(server, 1, "resources/list")
        assert wire.answer(1)["error"]["code"] == -32601

    def test_an_unknown_tool_is_a_protocol_error(self, server, wire, page):
        send(server, 1, "tools/call", {"name": "arm", "arguments": {}})
        assert wire.answer(1)["error"]["code"] == -32602
        assert not page.asked

    def test_notifications_and_responses_get_no_answer(self, server, wire):
        send(server, None, "notifications/initialized")
        server.handle_line(json.dumps({"jsonrpc": "2.0", "id": 5, "result": {}}))
        server.handle_line("   ")
        assert wire.out == []

    def test_every_message_is_one_line(self):
        lines: list[bytes] = []

        class Stream:
            def write(self, data):
                lines.append(data)

            def flush(self):
                pass

        mcp.stdout_writer(Stream())({"jsonrpc": "2.0", "id": 1, "result": {"text": "two\nlines"}})
        assert len(lines) == 1 and lines[0].count(b"\n") == 1 and lines[0].endswith(b"\n")


class TestTools:
    @pytest.mark.parametrize(
        ("name", "arguments", "problem"),
        [
            ("get_parameters", {}, "names is missing"),
            ("get_parameters", {"names": []}, "has 0 items"),
            ("get_status", {"verbose": True}, "not an argument"),
            ("propose_mission", {"waypoints": [{"lat": 91, "lon": 0, "alt": 10}]}, "at most 90"),
            ("propose_mission", {"waypoints": [{"lat": 30, "lon": 120}]}, "alt is missing"),
            ("propose_mission", {"waypoints": [{"lat": 30, "lon": 120, "alt": 10, "drop": True}]}, "not an argument"),
            ("propose_mission", {"waypoints": [{"lat": 30, "lon": 120, "alt": 10, "type": "land"}]}, "one of"),
            ("propose_mission", {"waypoints": [{"lat": 30, "lon": 120, "alt": 10}], "takeoff_alt": 0}, "more than 0"),
            ("propose_parameters", {"values": {"WPNAV_SPEED": "fast"}}, "must be a number"),
            ("propose_parameters", {"values": {}}, "has 0 entries"),
            ("propose_parameters", {"values": {"X": 1}, "reason": "x" * 501}, "longer than 500"),
        ],
    )
    def test_arguments_are_checked_before_the_page_is_asked(self, server, wire, page, name, arguments, problem):
        result = call(server, wire, 1, name, arguments)["result"]
        assert result["isError"] is True and problem in result["content"][0]["text"]
        assert not page.asked

    def test_a_number_json_should_not_carry_is_refused(self, server, wire, page):
        # Python's json reads NaN, which no client should send and no FC should get.
        line = '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"propose_parameters","arguments":{"values":{"X":NaN}}}}'
        server.handle_line(line)
        assert wire.answer(1)["result"]["isError"] is True
        assert not page.asked

    @pytest.mark.parametrize(
        ("name", "kind", "timeout"),
        [
            ("get_status", "status", READ_TIMEOUT),
            ("get_mission", "mission", READ_TIMEOUT),
            ("get_parameters", "parameters", READ_TIMEOUT),
            ("propose_mission", "propose_mission", DECISION_TIMEOUT),
            ("propose_parameters", "propose_parameters", DECISION_TIMEOUT),
        ],
    )
    def test_what_each_tool_asks_the_page(self, server, wire, page, name, kind, timeout):
        arguments = {
            "get_parameters": {"names": ["BATT_*"]},
            "propose_mission": {"waypoints": [{"lat": 30.5, "lon": 120.1, "alt": 20}], "reason": "survey"},
            "propose_parameters": {"values": {"WPNAV_SPEED": 500}},
        }.get(name, {})
        call(server, wire, 1, name, arguments)
        assert page.asked == [(kind, arguments, timeout)]

    def test_a_refusal_of_the_page_is_an_error_the_model_can_read(self, server, wire, page):
        page.reply = {"ok": False, "error": "The vehicle is armed: proposals wait until it is disarmed."}
        result = call(server, wire, 1, "propose_parameters", {"values": {"X": 1}})["result"]
        assert result["isError"] is True and "armed" in result["content"][0]["text"]

    def test_no_argus_is_an_error_that_says_what_to_do(self, server, wire, page):
        page.reply = Unreachable("No Argus at ws://127.0.0.1:8100/ws: refused. Start Argus")
        result = call(server, wire, 1, "get_status")["result"]
        assert result["isError"] is True and "Start Argus" in result["content"][0]["text"]

    def test_a_cancelled_call_is_withdrawn_and_answered_no_more(self, server, wire, page):
        page.hold.set()
        send(server, 7, "tools/call", {"name": "propose_parameters", "arguments": {"values": {"X": 1}}})
        time.sleep(0.05)
        send(server, None, "notifications/cancelled", {"requestId": 7, "reason": "user stopped"})
        assert page.withdrawn.wait(2)
        time.sleep(0.1)
        assert not [m for m in wire.out if m.get("id") == 7]

    def test_a_long_wait_sends_progress_to_a_client_that_asked_for_it(self, server, wire, page):
        page.hold.set()
        send(server, 3, "tools/call", {"name": "get_status", "arguments": {}, "_meta": {"progressToken": "p3"}})
        time.sleep(0.1)
        page.release.set()
        wire.answer(3)
        notes = wire.notifications()
        assert notes and all(n["method"] == "notifications/progress" for n in notes)
        assert {n["params"]["progressToken"] for n in notes} == {"p3"}

    def test_no_progress_without_a_token(self, server, wire, page):
        page.hold.set()
        send(server, 3, "tools/call", {"name": "get_status", "arguments": {}})
        time.sleep(0.1)
        page.release.set()
        wire.answer(3)
        assert wire.notifications() == []

    def test_the_end_of_input_withdraws_what_waits(self, server, wire, page):
        page.hold.set()
        send(server, 4, "tools/call", {"name": "propose_parameters", "arguments": {"values": {"X": 1}}})
        time.sleep(0.05)
        server.close(grace=2)
        assert page.withdrawn.is_set()
        assert not [m for m in wire.out if m.get("id") == 4]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def argus(monkeypatch):
    """The real backend on a port of its own."""
    monkeypatch.delenv("GCS_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("backend.auth._token", None)
    monkeypatch.setattr("backend.auth.TOKEN_FILE", type("Missing", (), {"exists": lambda self: False})())
    from backend.app import app

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    yield f"ws://127.0.0.1:{port}/ws"
    server.should_exit = True
    thread.join(10)


def open_page(url: str, answer):
    """A page on the websocket that answers each request with answer(request)."""
    ws = connect(url, proxy=None, open_timeout=5)
    asked: list[dict] = []

    def run():
        try:
            for text in ws:
                msg = json.loads(text)
                if msg.get("type") in ("assistant_request", "assistant_cancel"):
                    asked.append(msg)
                    if msg["type"] == "assistant_request":
                        reply = answer(msg)
                        if reply is not None:
                            ws.send(json.dumps({"type": "assistant_reply", "id": msg["id"], **reply}))
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()
    time.sleep(0.2)
    return ws, asked


class TestThroughTheBackend:
    def test_the_page_answers_through_argus(self, argus):
        page, asked = open_page(argus, lambda m: {"ok": True, "result": {"kind": m["kind"], "args": m["args"]}})
        reply = Backend(argus).ask("parameters", {"names": ["BATT_*"]}, 5, threading.Event())
        assert reply["ok"] is True
        assert reply["result"] == {"kind": "parameters", "args": {"names": ["BATT_*"]}}
        page.close()

    def test_with_no_page_open_the_answer_says_so(self, argus):
        reply = Backend(argus).ask("status", {}, 5, threading.Event())
        assert reply["ok"] is False and "No Argus page is open" in reply["error"]

    def test_a_proposal_that_waits_too_long_is_withdrawn_from_the_page(self, argus):
        page, asked = open_page(argus, lambda m: None)
        reply = Backend(argus).ask("propose_parameters", {"values": {"X": 1}}, 0.5, threading.Event())
        assert reply["ok"] is False and "withdrawn" in reply["error"]
        time.sleep(0.3)
        assert [m["type"] for m in asked] == ["assistant_request", "assistant_cancel"]
        page.close()

    def test_a_page_that_closes_ends_the_wait(self, argus):
        page, asked = open_page(argus, lambda m: None)
        backend = Backend(argus)
        threading.Timer(0.3, page.close).start()
        reply = backend.ask("propose_parameters", {"values": {"X": 1}}, 10, threading.Event())
        assert reply["ok"] is False and "closed" in reply["error"]

    def test_the_page_learns_an_assistant_is_there_before_it_asks_anything(self, argus):
        page = connect(argus, proxy=None, open_timeout=5)
        Backend(argus).connect_soon()
        presence = json.loads(page.recv(timeout=5))
        while presence.get("type") != "assistant_presence":
            presence = json.loads(page.recv(timeout=5))
        assert presence == {"type": "assistant_presence", "count": 1}
        page.close()

    def test_no_argus_at_the_address(self):
        with pytest.raises(Unreachable, match="No Argus at ws://127.0.0.1:"):
            Backend(f"ws://127.0.0.1:{free_port()}/ws").ask("status", {}, 1, threading.Event())

    def test_the_token_goes_in_the_address_and_never_in_messages(self, monkeypatch):
        monkeypatch.setenv("ARGUS_URL", "https://gcs.example:8443/")
        monkeypatch.setenv("GCS_AUTH_TOKEN", "a b&c")
        assert mcp.backend_url() == "wss://gcs.example:8443/ws?token=a%20b%26c"
        assert mcp.redact(mcp.backend_url()) == "wss://gcs.example:8443/ws"
