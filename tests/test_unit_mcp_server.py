"""backend/mcp_server.py: MCP on stdio in both eras, and its tools asking the operator's page."""

import json
import socket
import threading
import time

import pytest
import uvicorn
from websockets.sync.client import connect

from backend import mcp_server as mcp
from backend.mcp_server import LEGACY, MODERN, Backend, Request, Server, Unreachable

META = "io.modelcontextprotocol/protocolVersion"
CAPS = "io.modelcontextprotocol/clientCapabilities"
TOOL_NAMES = [
    "get_status",
    "get_mission",
    "get_parameters",
    "propose_mission",
    "propose_parameters",
    "propose_flight_command",
    "check_proposal",
    "withdraw_proposal",
]
WITHDRAWN = {"ok": False, "error": "Withdrawn by the assistant.", "result": {"outcome": "withdrawn"}}


class FakeBackend(Backend):
    """The backend as the server sees it, with the page played by the test: respond() says how
    the page takes each request, and settle() moves one on. Waiting is the real Backend's."""

    def __init__(self):
        super().__init__("ws://fake")
        self.asked: list[tuple[str, dict]] = []
        self.withdrawn: list[str] = []
        self.unreachable: str | None = None

        def respond(kind, args):
            if kind.startswith("propose_"):
                return {"state": "waiting"}
            return {"answer": {"ok": True, "result": {"mode": "LOITER"}}}

        self.respond = respond

    def ask(self, kind, args):
        if self.unreachable:
            raise Unreachable(self.unreachable)
        rid = f"p{len(self.asked) + 1}"
        self.asked.append((kind, args))
        with self._changed:
            self._requests[rid] = Request(kind, time.monotonic())
        self.settle(rid, **self.respond(kind, args))
        return rid

    def settle(self, rid, state=None, answer=None):
        with self._changed:
            request = self._requests[rid]
            if state:
                request.state = state
            if answer is not None:
                request.state, request.answer = "answered", answer
            self._changed.notify_all()

    def withdraw(self, rid):
        self.withdrawn.append(rid)
        # As the page does: a proposal still waiting is answered withdrawn, a running one goes on.
        if self.get(rid).state == "waiting":
            self.settle(rid, answer=WITHDRAWN)


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


def outcome(response: dict) -> dict:
    result = response["result"]
    assert result["isError"] is False, result
    return result["structuredContent"]


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
        assert [t["name"] for t in tools] == TOOL_NAMES
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
        assert result["resultType"] == "complete" and len(result["tools"]) == len(TOOL_NAMES)
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


class TestArguments:
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
            ("propose_parameters", {"values": {"BATT_CAPACITY": "large"}}, "must be a number"),
            ("propose_parameters", {"values": {}}, "has 0 entries"),
            ("propose_parameters", {"values": {"X": 1}, "reason": "x" * 501}, "longer than 500"),
            ("propose_flight_command", {}, "command is missing"),
            ("propose_flight_command", {"command": "arm"}, "must be one of rtl, hold, land"),
            ("propose_flight_command", {"command": "takeoff"}, "must be one of"),
            ("propose_flight_command", {"command": "rtl", "altitude": 30}, "not an argument"),
            ("check_proposal", {"proposal": ""}, "is empty"),
            ("check_proposal", {"proposal": "p1", "wait_seconds": 120}, "at most 50"),
            ("withdraw_proposal", {}, "proposal is missing"),
        ],
    )
    def test_checked_before_the_page_is_asked(self, server, wire, page, name, arguments, problem):
        result = call(server, wire, 1, name, arguments)["result"]
        assert result["isError"] is True and problem in result["content"][0]["text"]
        assert not page.asked

    def test_a_number_json_should_not_carry_is_refused(self, server, wire, page):
        # Python's json reads NaN, which no client should send and no FC should get.
        line = '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"propose_parameters","arguments":{"values":{"X":NaN}}}}'
        server.handle_line(line)
        assert wire.answer(1)["result"]["isError"] is True
        assert not page.asked


class TestReads:
    @pytest.mark.parametrize(
        ("name", "kind"), [("get_status", "status"), ("get_mission", "mission"), ("get_parameters", "parameters")]
    )
    def test_what_each_asks_the_page(self, server, wire, page, name, kind):
        arguments = {"names": ["BATT_*"]} if name == "get_parameters" else {}
        call(server, wire, 1, name, arguments)
        assert page.asked == [(kind, arguments)]

    def test_a_refusal_of_the_page_is_an_error_the_model_can_read(self, server, wire, page):
        page.respond = lambda kind, args: {"answer": {"ok": False, "error": "The page has not read the parameters."}}
        result = call(server, wire, 1, "get_parameters", {"names": ["X"]})["result"]
        assert result["isError"] is True and "not read" in result["content"][0]["text"]

    def test_no_argus_is_an_error_that_says_what_to_do(self, server, wire, page):
        page.unreachable = "No Argus at ws://127.0.0.1:8100/ws: refused. Start Argus"
        result = call(server, wire, 1, "get_status")["result"]
        assert result["isError"] is True and "Start Argus" in result["content"][0]["text"]


class TestProposals:
    def propose(self, server, wire, rid=1):
        return outcome(call(server, wire, rid, "propose_parameters", {"values": {"BATT_CAPACITY": 4000}}))

    def test_a_proposal_returns_its_id_at_once(self, server, wire, page):
        proposed = self.propose(server, wire)
        assert proposed["proposal"] == "p1" and proposed["state"] == "waiting"
        assert page.asked == [("propose_parameters", {"values": {"BATT_CAPACITY": 4000}})]

    def test_a_flight_command_is_a_proposal_like_the_others(self, server, wire, page):
        proposed = outcome(call(server, wire, 1, "propose_flight_command", {"command": "rtl", "reason": "Low battery"}))
        assert proposed["proposal"] == "p1" and proposed["state"] == "waiting"
        assert page.asked == [("propose_command", {"command": "rtl", "reason": "Low battery"})]
        page.settle("p1", answer={"ok": True, "result": {"mode": "RTL"}})
        checked = outcome(call(server, wire, 2, "check_proposal", {"proposal": "p1", "wait_seconds": 0}))
        assert checked == {"proposal": "p1", "state": "done", "result": {"mode": "RTL"}}

    def test_the_instructions_tell_a_flight_command_from_a_change(self):
        assert "mission or parameter change is refused while the vehicle is armed" in mcp.INSTRUCTIONS
        assert "flight command" in mcp.INSTRUCTIONS and "slide" in mcp.INSTRUCTIONS
        tool = next(t for t in mcp.TOOLS if t["name"] == "propose_flight_command")
        assert tool["inputSchema"]["properties"]["command"]["enum"] == ["rtl", "hold", "land"]
        assert "Refused while the vehicle is armed" not in tool["description"]

    def test_one_the_page_refuses_at_once_is_an_error(self, server, wire, page):
        page.respond = lambda kind, args: {
            "answer": {"ok": False, "error": "The vehicle is armed.", "result": {"outcome": "refused"}}
        }
        result = call(server, wire, 1, "propose_parameters", {"values": {"X": 1}})["result"]
        assert result["isError"] is True and "armed" in result["content"][0]["text"]

    def test_one_the_page_never_takes_is_withdrawn(self, server, wire, page, monkeypatch):
        monkeypatch.setattr(mcp, "TAKEN_TIMEOUT", 0.2)
        page.respond = lambda kind, args: {}
        result = call(server, wire, 1, "propose_parameters", {"values": {"X": 1}})["result"]
        assert result["isError"] is True and "did not take" in result["content"][0]["text"]
        assert page.withdrawn == ["p1"]

    @pytest.mark.parametrize(
        ("answer", "expected"),
        [
            (
                {"ok": True, "result": {"values": {"BATT_CAPACITY": 4000}}},
                {"state": "done", "result": {"values": {"BATT_CAPACITY": 4000}}},
            ),
            (
                {"ok": False, "error": "The operator declined it.", "result": {"outcome": "declined"}},
                {"state": "declined"},
            ),
            ({"ok": False, "error": "did not confirm", "result": {"outcome": "failed"}}, {"state": "failed"}),
            (
                {"ok": False, "error": "The Argus page closed while the approved change was running"},
                {"state": "failed"},
            ),
        ],
    )
    def test_check_gives_the_decision(self, server, wire, page, answer, expected):
        self.propose(server, wire)
        page.settle("p1", answer=answer)
        checked = outcome(call(server, wire, 2, "check_proposal", {"proposal": "p1", "wait_seconds": 0}))
        assert checked["proposal"] == "p1"
        assert {k: checked[k] for k in expected} == expected

    def test_check_waits_for_the_operator_and_returns_when_they_decide(self, server, wire, page):
        self.propose(server, wire)
        threading.Timer(0.2, page.settle, args=("p1",), kwargs={"answer": {"ok": True, "result": {}}}).start()
        started = time.monotonic()
        checked = outcome(call(server, wire, 2, "check_proposal", {"proposal": "p1", "wait_seconds": 10}))
        assert checked["state"] == "done" and time.monotonic() - started < 3

    def test_check_while_it_waits_or_runs(self, server, wire, page):
        self.propose(server, wire)
        assert (
            outcome(call(server, wire, 2, "check_proposal", {"proposal": "p1", "wait_seconds": 0}))["state"]
            == "waiting"
        )
        page.settle("p1", state="running")
        assert (
            outcome(call(server, wire, 3, "check_proposal", {"proposal": "p1", "wait_seconds": 0}))["state"]
            == "running"
        )

    @pytest.mark.parametrize("tool", ["check_proposal", "withdraw_proposal"])
    def test_a_proposal_it_does_not_know(self, server, wire, page, tool):
        call(server, wire, 1, "get_status")  # a read is no proposal
        for proposal in ("nope", "p1"):
            result = call(server, wire, proposal, tool, {"proposal": proposal})["result"]
            assert result["isError"] is True and "No proposal" in result["content"][0]["text"]

    def test_withdrawing_one_that_waits(self, server, wire, page):
        self.propose(server, wire)
        withdrawn = outcome(call(server, wire, 2, "withdraw_proposal", {"proposal": "p1"}))
        assert withdrawn["state"] == "withdrawn" and page.withdrawn == ["p1"]

    def test_one_already_approved_goes_on(self, server, wire, page):
        self.propose(server, wire)
        page.settle("p1", state="running")
        withdrawn = outcome(call(server, wire, 2, "withdraw_proposal", {"proposal": "p1"}))
        assert withdrawn["state"] == "running" and page.withdrawn == []
        page.settle("p1", answer={"ok": True, "result": {"values": {"BATT_CAPACITY": 4000}}})
        assert outcome(call(server, wire, 3, "check_proposal", {"proposal": "p1"}))["state"] == "done"

    def test_a_long_check_sends_progress_to_a_client_that_asked_for_it(self, server, wire, page, monkeypatch):
        monkeypatch.setattr(mcp, "PROGRESS_EVERY", 0.05)
        self.propose(server, wire)
        call(
            server,
            wire,
            2,
            "check_proposal",
            {"proposal": "p1", "wait_seconds": 0.3},
            {"_meta": {"progressToken": "t2"}},
        )
        notes = wire.notifications()
        assert notes and all(n["method"] == "notifications/progress" for n in notes)
        assert {n["params"]["progressToken"] for n in notes} == {"t2"}

    def test_no_progress_without_a_token(self, server, wire, page, monkeypatch):
        monkeypatch.setattr(mcp, "PROGRESS_EVERY", 0.05)
        self.propose(server, wire)
        call(server, wire, 2, "check_proposal", {"proposal": "p1", "wait_seconds": 0.3})
        assert wire.notifications() == []

    def test_a_cancelled_check_gets_no_answer_and_leaves_the_proposal(self, server, wire, page):
        self.propose(server, wire)
        send(server, 7, "tools/call", {"name": "check_proposal", "arguments": {"proposal": "p1", "wait_seconds": 20}})
        time.sleep(0.1)
        send(server, None, "notifications/cancelled", {"requestId": 7, "reason": "user stopped"})
        time.sleep(0.8)
        assert not [m for m in wire.out if m.get("id") == 7]
        assert page.withdrawn == []

    def test_a_propose_call_cancelled_before_the_page_took_it_is_withdrawn(self, server, wire, page):
        page.respond = lambda kind, args: {}
        send(server, 7, "tools/call", {"name": "propose_parameters", "arguments": {"values": {"X": 1}}})
        time.sleep(0.1)
        send(server, None, "notifications/cancelled", {"requestId": 7})
        time.sleep(0.8)
        assert page.withdrawn == ["p1"]
        assert not [m for m in wire.out if m.get("id") == 7]

    def test_the_end_of_input_stops_the_waits(self, server, wire, page):
        self.propose(server, wire)
        send(server, 4, "tools/call", {"name": "check_proposal", "arguments": {"proposal": "p1", "wait_seconds": 30}})
        time.sleep(0.05)
        started = time.monotonic()
        server.close(grace=2)
        assert time.monotonic() - started < 2
        assert not [m for m in wire.out if m.get("id") == 4]


class TestToken:
    def test_the_token_goes_in_the_address_and_never_in_messages(self, monkeypatch):
        monkeypatch.setenv("ARGUS_URL", "https://gcs.example:8443/")
        monkeypatch.setenv("GCS_AUTH_TOKEN", "a b&c")
        assert mcp.backend_url() == "wss://gcs.example:8443/ws?token=a%20b%26c"
        assert mcp.redact(mcp.backend_url()) == "wss://gcs.example:8443/ws"

    def test_for_this_install_the_file_the_page_made_comes_first(self, monkeypatch, tmp_path):
        # As backend/auth.py reads them.
        token_file = tmp_path / ".gcs_token"
        token_file.write_text("from-the-page\n")
        monkeypatch.setattr(mcp, "TOKEN_FILE", token_file)
        monkeypatch.delenv("ARGUS_URL", raising=False)
        monkeypatch.setenv("GCS_AUTH_TOKEN", "from-the-environment")
        assert mcp.access_token() == "from-the-page"
        monkeypatch.setenv("ARGUS_URL", "http://10.0.0.7:8100")
        assert mcp.access_token() == "from-the-environment"
        token_file.unlink()
        monkeypatch.delenv("ARGUS_URL")
        assert mcp.access_token() == "from-the-environment"


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
    """A page on the websocket. answer(request, ws) answers each request, or not."""
    ws = connect(url, proxy=None, open_timeout=5)
    asked: list[dict] = []

    def run():
        try:
            for text in ws:
                msg = json.loads(text)
                if msg.get("type") in ("assistant_request", "assistant_cancel"):
                    asked.append(msg)
                    if msg["type"] == "assistant_request":
                        answer(msg, ws)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()
    time.sleep(0.2)
    return ws, asked


def reply(ws, msg, **fields):
    ws.send(json.dumps({"type": "assistant_reply", "id": msg["id"], **fields}))


def state(ws, msg, value):
    ws.send(json.dumps({"type": "assistant_state", "id": msg["id"], "state": value}))


class TestThroughTheBackend:
    def tools(self, url):
        wire = Wire()
        return Server(Backend(url), wire.write), wire

    def test_the_page_answers_through_argus(self, argus):
        page, _ = open_page(argus, lambda m, ws: reply(ws, m, ok=True, result={"kind": m["kind"], "args": m["args"]}))
        server, wire = self.tools(argus)
        result = outcome(call(server, wire, 1, "get_parameters", {"names": ["BATT_*"]}))
        assert result == {"kind": "parameters", "args": {"names": ["BATT_*"]}}
        page.close()

    def test_with_no_page_open_the_answer_says_so(self, argus):
        server, wire = self.tools(argus)
        result = call(server, wire, 1, "get_status")["result"]
        assert result["isError"] is True and "No Argus page is open" in result["content"][0]["text"]

    def test_a_proposal_decided_later_is_found_by_check(self, argus):
        taken: list[tuple] = []
        page, _ = open_page(argus, lambda m, ws: (state(ws, m, "waiting"), taken.append((m, ws))))
        server, wire = self.tools(argus)
        proposed = outcome(call(server, wire, 1, "propose_parameters", {"values": {"BATT_CAPACITY": 4000}}))
        assert proposed["state"] == "waiting"
        msg, ws = taken[0]
        state(ws, msg, "running")
        threading.Timer(
            0.2, reply, args=(ws, msg), kwargs={"ok": True, "result": {"values": {"BATT_CAPACITY": 4000}}}
        ).start()
        checked = outcome(
            call(server, wire, 2, "check_proposal", {"proposal": proposed["proposal"], "wait_seconds": 5})
        )
        assert checked == {
            "proposal": proposed["proposal"],
            "state": "done",
            "result": {"values": {"BATT_CAPACITY": 4000}},
        }
        page.close()

    def test_a_withdrawal_reaches_the_page_and_its_answer_comes_back(self, argus):
        def answer(m, ws):
            state(ws, m, "waiting")

        page, asked = open_page(argus, answer)
        server, wire = self.tools(argus)
        rid = outcome(call(server, wire, 1, "propose_parameters", {"values": {"X": 1}}))["proposal"]

        def on_cancel():
            cancel = next(m for m in asked if m["type"] == "assistant_cancel")
            reply(page, cancel, ok=False, error="Withdrawn by the assistant.", result={"outcome": "withdrawn"})

        threading.Timer(0.3, on_cancel).start()
        assert outcome(call(server, wire, 2, "withdraw_proposal", {"proposal": rid}))["state"] == "withdrawn"
        page.close()

    def test_a_page_that_closes_while_it_runs_says_the_change_may_be_made(self, argus):
        taken: list[tuple] = []
        page, _ = open_page(argus, lambda m, ws: (state(ws, m, "waiting"), taken.append((m, ws))))
        server, wire = self.tools(argus)
        rid = outcome(call(server, wire, 1, "propose_parameters", {"values": {"X": 1}}))["proposal"]
        msg, ws = taken[0]
        state(ws, msg, "running")
        time.sleep(0.2)
        page.close()
        checked = outcome(call(server, wire, 2, "check_proposal", {"proposal": rid, "wait_seconds": 5}))
        assert checked["state"] == "failed" and "may have been made" in checked["error"]

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
            Backend(f"ws://127.0.0.1:{free_port()}/ws").ask("status", {})
