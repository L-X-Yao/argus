"""Argus for an AI assistant: a Model Context Protocol (MCP) server on stdio.

An MCP client (Claude Desktop, Claude Code, any other) starts this as a subprocess and calls its
tools. Every tool asks the Argus page that holds command authority, through the backend's
websocket (backend/ws_manager.py): the page answers with what it shows, and each change waits
for the operator, who approves or declines it there. The assistant holds no command authority
of its own: nothing it asks reaches the vehicle unless the operator lets it.

    python -m backend.mcp_server

Environment:
    ARGUS_URL       the Argus backend, http://127.0.0.1:8100 when unset
    GCS_AUTH_TOKEN  its access token, when it has one

Written on the standard library and websockets, which Argus needs anyway. The MCP SDK would add
some 15 MB to the Windows package (pywin32, cryptography and more) for transports and sign-in
that stdio does not use. tests/test_contract_mcp_client.py holds this server to the official
TypeScript SDK's client, the one Claude Desktop and Claude Code are built on.

Both eras of the protocol are served (https://modelcontextprotocol.io/specification): requests
that carry their version in _meta (2026-07-28, with server/discover), and the initialize
handshake of 2025-11-25 and earlier.
"""

from __future__ import annotations

import inspect
import json
import os
import queue
import sys
import threading
import time
import uuid
from collections.abc import Callable
from urllib.parse import quote, urlsplit

from websockets.sync.client import connect

from .config import VERSION

MODERN = ("2026-07-28",)
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
# structuredContent came with this one.
STRUCTURED_SINCE = "2025-06-18"
SERVER_INFO = {"name": "argus-gcs", "title": "Argus GCS", "version": VERSION}
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER = "io.modelcontextprotocol/serverInfo"

INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, PARSE_ERROR = -32600, -32601, -32602, -32700
UNSUPPORTED_VERSION = -32022

READ_TIMEOUT = 15.0
# How long a proposal waits for the operator before it is withdrawn from the page.
DECISION_TIMEOUT = 300.0
PROGRESS_EVERY = 10.0

INSTRUCTIONS = (
    "Argus is a ground control station for ArduPilot vehicles. These tools read what the "
    "operator's Argus page shows and propose changes, which the operator approves or declines "
    "in the page: nothing changes on the vehicle otherwise. Call get_status first. Proposals "
    "are refused while the vehicle is armed. Read each result: a proposal can be declined, "
    "time out, or fail on the flight controller."
)

_NO_ARGS = {"type": "object", "additionalProperties": False}
_REASON = {
    "type": "string",
    "maxLength": 500,
    "description": "One or two sentences for the operator: what this is for. Shown with the proposal.",
}
TOOLS = [
    {
        "name": "get_status",
        "title": "Vehicle status",
        "description": (
            "What the Argus page shows about the vehicle now: the link, vehicle type, flight mode, "
            "armed or not, position, altitudes, speeds, battery, GPS, home, the mission item being "
            "flown, and the latest messages of the flight controller."
        ),
        "inputSchema": _NO_ARGS,
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "get_mission",
        "title": "Planned mission",
        "description": (
            "The mission planned in the Argus page, in order, as the page would upload it, and the "
            "takeoff altitude it uses. The upload adds a takeoff before the first item and a return "
            "to launch after the last. Not what the flight controller holds, unless the operator "
            "uploaded this plan."
        ),
        "inputSchema": _NO_ARGS,
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "get_parameters",
        "title": "Flight controller parameters",
        "description": (
            "Values of flight controller parameters as the Argus page last read them. Give exact "
            "names, such as WPNAV_SPEED, or a prefix ending in *, such as BATT_*. At most 200 values "
            "come back. When the page has not read the parameters, the result says so: the operator "
            "reads them in the Params view."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 200},
            },
            "required": ["names"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "propose_mission",
        "title": "Propose a mission",
        "description": (
            "Ask the operator to make this the planned mission and upload it to the flight controller. "
            "Nothing changes until the operator approves it in the Argus page, where the route is drawn "
            "on the map. The call waits for that decision, up to 5 minutes, and returns it, with the "
            "upload's result. Refused while the vehicle is armed. The upload adds a takeoff to "
            "takeoff_alt before the first waypoint and a return to launch after the last."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "waypoints": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 500,
                    "items": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number", "minimum": -90, "maximum": 90},
                            "lon": {"type": "number", "minimum": -180, "maximum": 180},
                            "alt": {"type": "number", "description": "Metres above home."},
                            "type": {
                                "type": "string",
                                "enum": ["wp", "loiter_time", "loiter_turns", "spline"],
                                "description": "Waypoint kind. wp when left out.",
                            },
                            "loiter_param": {
                                "type": "number",
                                "minimum": 0,
                                "description": "Seconds for loiter_time, turns for loiter_turns.",
                            },
                            "delay": {"type": "number", "minimum": 0, "description": "Seconds to wait here."},
                            "speed": {
                                "type": "number",
                                "minimum": 0,
                                "description": "Metres per second from here on. 0 keeps the speed.",
                            },
                        },
                        "required": ["lat", "lon", "alt"],
                        "additionalProperties": False,
                    },
                },
                "takeoff_alt": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": "Metres above home. The page's default altitude when left out.",
                },
                "reason": _REASON,
            },
            "required": ["waypoints"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "propose_parameters",
        "title": "Propose parameter changes",
        "description": (
            "Ask the operator to set these flight controller parameters. Nothing changes until the "
            "operator approves in the Argus page, which shows each old and new value. The call waits "
            "for that decision, up to 5 minutes, and returns what the flight controller confirmed. "
            "Refused while the vehicle is armed, and for names the page has not read."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "values": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "minProperties": 1,
                    "maxProperties": 50,
                },
                "reason": _REASON,
            },
            "required": ["values"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
]
# What the page is asked for each tool, and whether the operator decides.
_KINDS = {
    "get_status": ("status", False),
    "get_mission": ("mission", False),
    "get_parameters": ("parameters", False),
    "propose_mission": ("propose_mission", True),
    "propose_parameters": ("propose_parameters", True),
}
_TOOLS = {tool["name"]: tool for tool in TOOLS}


class Unreachable(Exception):
    """No Argus backend to talk to: not running, another address, or a token missing."""


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_arguments(schema: dict, value, where: str = "arguments") -> str | None:
    """What is wrong with value for this schema, or None. Covers what the tools here use; the
    page checks each request again before anything is shown to the operator."""
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return f"{where} must be an object"
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                return f"{where}.{name} is missing"
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            if name in properties:
                problem = check_arguments(properties[name], item, f"{where}.{name}")
            elif extra is False:
                problem = f"{where}.{name} is not an argument of this tool"
            elif isinstance(extra, dict):
                problem = check_arguments(extra, item, f"{where}.{name}")
            else:
                problem = None
            if problem:
                return problem
        if len(value) < schema.get("minProperties", 0) or len(value) > schema.get("maxProperties", len(value)):
            return f"{where} has {len(value)} entries"
        return None
    if kind == "array":
        if not isinstance(value, list):
            return f"{where} must be a list"
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            return f"{where} has {len(value)} items"
        for i, item in enumerate(value):
            problem = check_arguments(schema.get("items", {}), item, f"{where}[{i}]")
            if problem:
                return problem
        return None
    if kind == "number":
        if not _is_number(value) or value != value or value in (float("inf"), float("-inf")):
            return f"{where} must be a number"
        if "minimum" in schema and value < schema["minimum"]:
            return f"{where} must be at least {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{where} must be at most {schema['maximum']}"
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            return f"{where} must be more than {schema['exclusiveMinimum']}"
        return None
    if kind == "string":
        if not isinstance(value, str):
            return f"{where} must be text"
        if "enum" in schema and value not in schema["enum"]:
            return f"{where} must be one of {', '.join(schema['enum'])}"
        if len(value) > schema.get("maxLength", len(value)):
            return f"{where} is longer than {schema['maxLength']} characters"
        return None
    return None


def backend_url() -> str:
    """The backend's websocket, from ARGUS_URL and GCS_AUTH_TOKEN."""
    base = urlsplit(os.environ.get("ARGUS_URL") or "http://127.0.0.1:8100")
    scheme = "wss" if base.scheme in ("https", "wss") else "ws"
    url = f"{scheme}://{base.netloc}/ws"
    token = os.environ.get("GCS_AUTH_TOKEN")
    return f"{url}?token={quote(token, safe='')}" if token else url


class Backend:
    """The websocket to the Argus backend, as an assistant: asks the operator's page and waits."""

    def __init__(self, url: str):
        self.url = url
        self._lock = threading.Lock()
        self._ws = None
        self._waiting: dict[str, queue.Queue] = {}

    def _connection(self):
        with self._lock:
            if self._ws is not None:
                return self._ws
            options = {"open_timeout": 5, "max_size": 8 * 1024 * 1024}
            # Straight to Argus: websockets 15 and later would take a proxy from the environment.
            if "proxy" in inspect.signature(connect).parameters:
                options["proxy"] = None
            try:
                ws = connect(self.url, **options)
                ws.send(json.dumps({"type": "assistant_hello", "name": "argus-mcp", "version": VERSION}))
                while json.loads(ws.recv(timeout=5)).get("type") != "assistant_welcome":
                    pass
            except Exception as exc:
                raise Unreachable(
                    f"No Argus at {redact(self.url)}: {exc}. Start Argus, set ARGUS_URL to its address, "
                    "and GCS_AUTH_TOKEN when it has a token."
                ) from exc
            self._ws = ws
            threading.Thread(target=self._read, args=(ws,), daemon=True).start()
            return ws

    def connect_soon(self) -> None:
        """Connect now, without waiting: the page shows an assistant is there from the moment its
        client starts it. With no Argus yet, the first tool call tries again."""

        def run():
            try:
                self._connection()
            except Unreachable:
                pass

        threading.Thread(target=run, daemon=True).start()

    def _read(self, ws) -> None:
        try:
            for text in ws:
                msg = json.loads(text)
                if msg.get("type") == "assistant_reply" and msg.get("id") in self._waiting:
                    self._waiting[msg["id"]].put(msg)
        except Exception:
            pass
        with self._lock:
            if self._ws is ws:
                self._ws = None
        for waiting in list(self._waiting.values()):
            waiting.put({"ok": False, "error": "The connection to Argus closed."})

    def ask(
        self,
        kind: str,
        args: dict,
        timeout: float,
        cancelled: threading.Event,
        waiting_note: Callable[[float], None] | None = None,
    ) -> dict | None:
        """The page's answer, or None when the request was cancelled. Raises Unreachable."""
        ws = self._connection()
        rid = uuid.uuid4().hex
        answers: queue.Queue = queue.Queue()
        self._waiting[rid] = answers
        try:
            ws.send(json.dumps({"type": "assistant_request", "id": rid, "kind": kind, "args": args}))
            started = time.monotonic()
            noted = started
            while True:
                if cancelled.is_set():
                    self._cancel(ws, rid)
                    return None
                now = time.monotonic()
                if now - started >= timeout:
                    self._cancel(ws, rid)
                    return {"ok": False, "error": f"No answer in {timeout:.0f} s: the request was withdrawn."}
                if waiting_note and now - noted >= PROGRESS_EVERY:
                    noted = now
                    waiting_note(now - started)
                try:
                    return answers.get(timeout=0.5)
                except queue.Empty:
                    continue
        finally:
            self._waiting.pop(rid, None)

    @staticmethod
    def _cancel(ws, rid: str) -> None:
        try:
            ws.send(json.dumps({"type": "assistant_cancel", "id": rid}))
        except Exception:
            pass


def redact(url: str) -> str:
    return url.split("?", 1)[0]


class Server:
    """JSON-RPC over newline-delimited stdio, both eras of MCP. One thread per tool call: a
    proposal waits minutes for the operator, and pings and cancellations go on meanwhile."""

    def __init__(self, backend, write: Callable[[dict], None]):
        self.backend = backend
        self.write = write
        self.legacy_version: str | None = None
        self._calls: dict[object, threading.Event] = {}
        self._calls_lock = threading.Lock()

    # ---- the message loop ------------------------------------------------------------------

    def handle_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
        except ValueError:
            self._error(None, PARSE_ERROR, "Parse error")
            return
        if not isinstance(msg, dict):
            # Batches went out of the protocol with 2025-06-18.
            self._error(None, INVALID_REQUEST, "Invalid request: one JSON-RPC message per line")
            return
        method = msg.get("method")
        if not isinstance(method, str):
            return  # a response or something else a client should not send: nothing to answer
        params = msg.get("params")
        params = params if isinstance(params, dict) else {}
        if "id" not in msg:
            self._notification(method, params)
            return
        rid = msg["id"]
        if isinstance(rid, bool) or not isinstance(rid, (str, int)):
            self._error(None, INVALID_REQUEST, "Invalid request: id must be a string or an integer")
            return
        self._request(rid, method, params)

    def close(self, grace: float = 2.0) -> None:
        """End of input: withdraw what still waits for the page, and give it a moment to go."""
        with self._calls_lock:
            events = list(self._calls.values())
        for event in events:
            event.set()
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            with self._calls_lock:
                if not self._calls:
                    return
            time.sleep(0.05)

    def _notification(self, method: str, params: dict) -> None:
        if method == "notifications/cancelled":
            with self._calls_lock:
                event = self._calls.get(params.get("requestId"))
            if event is not None:
                event.set()

    def _request(self, rid, method: str, params: dict) -> None:
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        modern = META_VERSION in meta
        if modern:
            version = meta.get(META_VERSION)
            if not isinstance(version, str) or not isinstance(meta.get(META_CAPABILITIES), dict):
                self._error(rid, INVALID_PARAMS, f"Invalid params: _meta needs {META_VERSION} and {META_CAPABILITIES}")
                return
            if version not in MODERN:
                self._error(
                    rid,
                    UNSUPPORTED_VERSION,
                    "Unsupported protocol version",
                    {"supported": [*MODERN, *LEGACY], "requested": version},
                )
                return
        if method == "initialize" and not modern:
            requested = params.get("protocolVersion")
            self.legacy_version = requested if requested in LEGACY else LEGACY[0]
            self._result(
                rid,
                {
                    "protocolVersion": self.legacy_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                    "instructions": INSTRUCTIONS,
                },
                modern,
            )
        elif method == "server/discover":
            self._result(
                rid,
                {
                    "supportedVersions": [*MODERN, *LEGACY],
                    "capabilities": {"tools": {}},
                    "instructions": INSTRUCTIONS,
                },
                True,
            )
        elif method == "ping":
            self._result(rid, {}, modern)
        elif method == "tools/list":
            self._result(rid, {"tools": TOOLS}, modern)
        elif method == "tools/call":
            name, arguments = params.get("name"), params.get("arguments", {})
            if name not in _TOOLS:
                self._error(rid, INVALID_PARAMS, f"Unknown tool: {name}")
                return
            event = threading.Event()
            with self._calls_lock:
                self._calls[rid] = event
            token = meta.get("progressToken")
            threading.Thread(target=self._call, args=(rid, name, arguments, modern, token, event), daemon=True).start()
        else:
            self._error(rid, METHOD_NOT_FOUND, f"Method not found: {method}")

    # ---- tools -----------------------------------------------------------------------------

    def _call(self, rid, name: str, arguments, modern: bool, token, cancelled: threading.Event) -> None:
        try:
            result = self.run_tool(name, arguments, cancelled, self._progress_note(token, cancelled))
        except Exception as exc:  # never a silent end to a call the client waits for
            result = self._tool_text(f"Argus could not run {name}: {exc}", error=True)
        finally:
            with self._calls_lock:
                self._calls.pop(rid, None)
        if result is not None and not cancelled.is_set():
            self._result(rid, result, modern)

    def run_tool(self, name: str, arguments, cancelled: threading.Event, note=None) -> dict | None:
        """The tools/call result, or None when the call was cancelled."""
        problem = check_arguments(_TOOLS[name]["inputSchema"], arguments)
        if problem:
            return self._tool_text(problem, error=True)
        kind, decided = _KINDS[name]
        try:
            reply = self.backend.ask(kind, arguments, DECISION_TIMEOUT if decided else READ_TIMEOUT, cancelled, note)
        except Unreachable as exc:
            return self._tool_text(str(exc), error=True)
        if reply is None:
            return None
        if not reply.get("ok"):
            return self._tool_text(str(reply.get("error") or "The Argus page refused."), error=True)
        result = reply.get("result")
        structured = result if isinstance(result, dict) else {"result": result}
        return self._tool_text(json.dumps(result, ensure_ascii=False), structured=structured)

    def _tool_text(self, text: str, error: bool = False, structured: dict | None = None) -> dict:
        result: dict = {"content": [{"type": "text", "text": text}], "isError": error}
        if structured is not None and (self.legacy_version is None or self.legacy_version >= STRUCTURED_SINCE):
            result["structuredContent"] = structured
        return result

    def _progress_note(self, token, cancelled: threading.Event):
        if not isinstance(token, (str, int)) or isinstance(token, bool):
            return None

        def note(seconds: float) -> None:
            if not cancelled.is_set():
                params = {"progressToken": token, "progress": round(seconds), "message": "Waiting for the operator"}
                self.write({"jsonrpc": "2.0", "method": "notifications/progress", "params": params})

        return note

    # ---- replies ---------------------------------------------------------------------------

    def _result(self, rid, result: dict, modern: bool) -> None:
        if modern:
            result = {"resultType": "complete", **result, "_meta": {META_SERVER: SERVER_INFO}}
        self.write({"jsonrpc": "2.0", "id": rid, "result": result})

    def _error(self, rid, code: int, message: str, data=None) -> None:
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self.write({"jsonrpc": "2.0", "id": rid, "error": error})


def stdout_writer(stream) -> Callable[[dict], None]:
    lock = threading.Lock()

    def write(msg: dict) -> None:
        # One line per message: json.dumps escapes every newline inside strings.
        data = (json.dumps(msg, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        with lock:
            stream.write(data)
            stream.flush()

    return write


def main() -> int:
    backend = Backend(backend_url())
    backend.connect_soon()
    server = Server(backend, stdout_writer(sys.stdout.buffer))
    print(f"Argus MCP server {VERSION}: {redact(backend_url())}", file=sys.stderr, flush=True)
    for raw in sys.stdin.buffer:
        server.handle_line(raw.decode("utf-8", errors="replace"))
    # End of input: the client is done, and the spec asks for a prompt exit.
    server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
