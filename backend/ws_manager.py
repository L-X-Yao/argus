from __future__ import annotations

import asyncio
import json
import logging
import math
import uuid
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect

from . import commands
from .config import cfg
from .drone_link import DroneLink
from .locale_text import lt

logger = logging.getLogger(__name__)


def _strict(obj, path: list, found: list):
    """A copy of obj that JSON can carry: a NaN or an infinity becomes None, and found gets
    where each one was and which it was."""
    if isinstance(obj, float):
        if math.isfinite(obj):
            return obj
        found.append([*path, "NaN" if obj != obj else "Infinity" if obj > 0 else "-Infinity"])
        return None
    if isinstance(obj, dict):
        return {key: _strict(value, [*path, key], found) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_strict(value, [*path, i], found) for i, value in enumerate(obj)]
    return obj


def dumps(msg: dict) -> str:
    """JSON that the page can parse. A float the FC sent as NaN (the variances of an estimator
    that has diverged, an attitude) is written by json.dumps as the bare word NaN, which is
    no JSON: JSON.parse threw, and since NaN never equals itself the value went out again
    with every push. The page dropped every state message from then on and went on showing
    the last values it had, with no alarm. Each such value goes as null now, and
    "_nonfinite" lists where they were for the page to put back: see restoreNonFinite in
    src/lib/ws.ts."""
    try:
        return json.dumps(msg, allow_nan=False)
    except ValueError:
        found: list = []
        clean = _strict(msg, [], found)
        clean["_nonfinite"] = found
        return json.dumps(clean, allow_nan=False)


_VALID_LOCALES = frozenset(("zh", "en", "ja", "ko", "de", "fr", "es", "pt", "ru", "ar"))


def validate_port(port) -> bool:
    return isinstance(port, str) and len(port) <= 200 and "\x00" not in port


# An assistant (backend/mcp_server.py, the AI's way in) is a client of its own kind. It reads
# what the operator's page answers, and asks that page for changes, which the operator approves
# or declines there. It never holds command authority: nothing it sends reaches the vehicle.
_FROM_ASSISTANT = frozenset(("assistant_hello", "assistant_request", "assistant_cancel"))
# Requests of one assistant waiting for the page at once: an AI in a loop floods nobody.
_MAX_WAITING = 20
_NO_PAGE = (
    "No Argus page is open. Open Argus in a browser: the page answers for the vehicle, "
    "and the operator approves changes there."
)
_PAGE_CLOSED = "The Argus page that was asked has closed."
_CLOSED_RUNNING = (
    "The Argus page closed while the approved change was running: it may have been made. "
    "Read get_status and get_mission before anything else."
)
# What a page says of a request before its answer: queued for the operator, or approved and on
# its way to the vehicle. Only the answer ends it.
_STATES = ("waiting", "running")


@dataclass
class _Asked:
    """A request on its way: who asked it, its id there, the page asked, and whether the
    operator has approved it."""

    assistant: WebSocket
    rid: str
    page: WebSocket
    running: bool = False


def sanitize_baud(baud) -> int:
    try:
        baud = int(baud)
    except (TypeError, ValueError):
        return cfg.SERIAL_BAUD
    return baud if baud in cfg.VALID_BAUD_RATES else cfg.SERIAL_BAUD


class WSManager:
    def __init__(self, link: DroneLink):
        self.link = link
        self._clients: set[WebSocket] = set()
        # Connection order (earliest first). `set` gives no ordering, so we
        # track it separately to identify the session operator — the
        # earliest-connected client — for the implicit-pilot rule below.
        self._order: list[WebSocket] = []
        self._pilot_ws: WebSocket | None = None
        self._roles: dict[int, str] = {}
        self._assistants: set[WebSocket] = set()
        self._asked: dict[str, _Asked] = {}
        self._asked_total = 0
        # In every key: a page keeps its requests across a restart of the backend, and an
        # answer to one of before must not land on a new one with the same number.
        self._session = uuid.uuid4().hex[:8]

    @property
    def client_count(self) -> int:
        """Pages, not assistants: what the pages show as the number of operators and viewers."""
        return len(self._clients - self._assistants)

    @property
    def assistant_count(self) -> int:
        return len(self._assistants & self._clients)

    def operator(self) -> WebSocket | None:
        """The page with command authority: the pilot, or else the page that connected first."""
        if self._pilot_ws is not None and self._pilot_ws in self._clients:
            return self._pilot_ws
        return next((c for c in self._order if c in self._clients and c not in self._assistants), None)

    async def broadcast(self, msg: dict) -> None:
        text = dumps(msg)
        for ws in list(self._clients):
            try:
                await ws.send_text(text)
            except Exception:
                # WebSocketDisconnect inherits from Exception, not from any
                # of the legacy stdlib network errors — catching it specifically
                # would require importing the WS-impl class. A bare Exception
                # here is correct because broadcast() failures should never
                # take down the receive_loop of another (still-healthy) client.
                self._clients.discard(ws)

    async def handle_client(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        self._order.append(ws)
        if self.assistant_count:
            await ws.send_text(dumps({"type": "assistant_presence", "count": self.assistant_count}))
        try:
            recv_task = asyncio.create_task(self._receive_loop(ws))
            push_task = asyncio.create_task(self._push_loop(ws))
            done, pending = await asyncio.wait(
                [recv_task, push_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            for t in done:
                if t.exception() is not None:
                    pass
        except (ConnectionError, RuntimeError):
            pass
        finally:
            self._clients.discard(ws)
            self._order = [c for c in self._order if c is not ws]
            # Clear this client's role + pilot reference so the next observer
            # to call request_handoff doesn't auto-promote because the dead
            # ws is no longer `in self._clients` (auditor finding).
            self._roles.pop(id(ws), None)
            if self._pilot_ws is ws:
                self._pilot_ws = None
            await self._forget(ws)

    async def _forget(self, ws: WebSocket) -> None:
        """What was asked by or of a client that has gone."""
        was_assistant = ws in self._assistants
        self._assistants.discard(ws)
        for key, asked in list(self._asked.items()):
            if asked.assistant is ws:
                # Nobody to answer: a change still waiting is withdrawn, one running goes on.
                del self._asked[key]
                await self._send(asked.page, {"type": "assistant_cancel", "id": key})
            elif asked.page is ws:
                del self._asked[key]
                error = _CLOSED_RUNNING if asked.running else _PAGE_CLOSED
                await self._send(
                    asked.assistant, {"type": "assistant_reply", "id": asked.rid, "ok": False, "error": error}
                )
        if was_assistant:
            await self._presence()

    @staticmethod
    async def _send(ws: WebSocket, msg: dict) -> None:
        try:
            await ws.send_text(dumps(msg))
        except Exception:
            pass  # gone: its own receive loop cleans up

    async def _presence(self) -> None:
        for page in list(self._clients - self._assistants):
            await self._send(page, {"type": "assistant_presence", "count": self.assistant_count})

    async def _from_assistant(self, ws: WebSocket, msg_type: str, msg: dict) -> None:
        if msg_type == "assistant_hello":
            if ws not in self._assistants:
                self._assistants.add(ws)
                self._roles.pop(id(ws), None)
                if self._pilot_ws is ws:
                    self._pilot_ws = None
                await self._presence()
            await self._send(ws, {"type": "assistant_welcome"})
            return
        if msg_type not in _FROM_ASSISTANT:
            await self._send(ws, {"type": "assistant_error", "error": f"{msg_type!r} is not open to an assistant"})
            return
        rid = msg.get("id")
        if not isinstance(rid, str) or not 0 < len(rid) <= 100:
            return  # nothing to answer to
        if msg_type == "assistant_cancel":
            # The page answers it: withdrawn if it still waits, its result if it was approved.
            for key, asked in list(self._asked.items()):
                if asked.assistant is ws and asked.rid == rid:
                    await self._send(asked.page, {"type": "assistant_cancel", "id": key})
            return
        kind, args = msg.get("kind"), msg.get("args", {})
        if not isinstance(kind, str) or not isinstance(args, dict):
            await self._send(ws, {"type": "assistant_reply", "id": rid, "ok": False, "error": "kind and args"})
            return
        if sum(1 for asked in self._asked.values() if asked.assistant is ws) >= _MAX_WAITING:
            error = f"{_MAX_WAITING} requests are already waiting for the page"
            await self._send(ws, {"type": "assistant_reply", "id": rid, "ok": False, "error": error})
            return
        page = self.operator()
        if page is None:
            await self._send(ws, {"type": "assistant_reply", "id": rid, "ok": False, "error": _NO_PAGE})
            return
        self._asked_total += 1
        key = f"{self._session}-{self._asked_total}"
        self._asked[key] = _Asked(ws, rid, page)
        await self._send(page, {"type": "assistant_request", "id": key, "kind": kind, "args": args})

    def _asked_of(self, page: WebSocket, msg: dict) -> tuple[str, _Asked] | None:
        key = msg.get("id")
        asked = self._asked.get(key) if isinstance(key, str) else None
        return (key, asked) if asked is not None and asked.page is page else None

    async def _to_assistant(self, page: WebSocket, msg: dict) -> None:
        """A page's answer, passed on to the assistant that asked, if it asked this page."""
        found = self._asked_of(page, msg)
        if found is None:
            return
        key, asked = found
        del self._asked[key]
        reply = {"type": "assistant_reply", "id": asked.rid, "ok": msg.get("ok") is True}
        if "result" in msg:
            reply["result"] = msg["result"]
        if isinstance(msg.get("error"), str):
            reply["error"] = msg["error"][:2000]
        await self._send(asked.assistant, reply)

    async def _state_to_assistant(self, page: WebSocket, msg: dict) -> None:
        """Where a request stands before its answer: waiting for the operator, or running."""
        found = self._asked_of(page, msg)
        state = msg.get("state")
        if found is None or state not in _STATES:
            return
        _, asked = found
        if state == "running":
            asked.running = True
        await self._send(asked.assistant, {"type": "assistant_state", "id": asked.rid, "state": state})

    async def _receive_loop(self, ws: WebSocket) -> None:
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue
                msg_type = msg.get("type", "")
                if ws in self._assistants or msg_type == "assistant_hello":
                    await self._from_assistant(ws, msg_type, msg)
                    continue
                if msg_type == "assistant_reply":
                    await self._to_assistant(ws, msg)
                    continue
                if msg_type == "assistant_state":
                    await self._state_to_assistant(ws, msg)
                    continue
                if msg_type == "connect":
                    port = msg.get("port", "tcp:localhost:5770")
                    baud = msg.get("baud", cfg.SERIAL_BAUD)
                    if not validate_port(port):
                        await ws.send_text(
                            dumps(
                                {
                                    "type": "connect_result",
                                    "ok": False,
                                    "error": lt("err_connect", self.link.locale),
                                }
                            )
                        )
                        continue
                    baud = sanitize_baud(baud)
                    ok = await asyncio.to_thread(self.link.connect, port, baud)
                    await ws.send_text(
                        dumps(
                            {
                                "type": "connect_result",
                                "ok": ok,
                                "error": "" if ok else lt("err_connect", self.link.locale),
                            }
                        )
                    )
                elif msg_type == "disconnect":
                    await asyncio.to_thread(self.link.disconnect)
                    await ws.send_text(
                        dumps(
                            {
                                "type": "connect_result",
                                "ok": True,
                                "error": "",
                            }
                        )
                    )
                elif msg_type == "set_locale":
                    locale = msg.get("locale", "zh")
                    if locale in _VALID_LOCALES:
                        self.link.locale = locale
                elif msg_type == "set_role":
                    role = msg.get("role", "observer")
                    self._roles[id(ws)] = role
                    if role == "pilot":
                        self._pilot_ws = ws
                    await self.broadcast(
                        {
                            "type": "role_update",
                            "clients": self.client_count,
                            "pilot_connected": self._pilot_ws in self._clients,
                        }
                    )
                elif msg_type == "request_handoff":
                    if self._pilot_ws and self._pilot_ws != ws and self._pilot_ws in self._clients:
                        await self._pilot_ws.send_text(dumps({"type": "handoff_request", "from": id(ws)}))
                    else:
                        self._pilot_ws = ws
                        self._roles[id(ws)] = "pilot"
                        await ws.send_text(dumps({"type": "handoff_granted"}))
                elif msg_type == "handoff_accept":
                    target_id = msg.get("target")
                    for client in self._clients:
                        if id(client) == target_id:
                            self._pilot_ws = client
                            self._roles[id(client)] = "pilot"
                            self._roles[id(ws)] = "observer"
                            await client.send_text(dumps({"type": "handoff_granted"}))
                            await ws.send_text(dumps({"type": "handoff_released"}))
                            break
                elif msg_type == "command":
                    # Observer clients must not be able to control the
                    # vehicle. Auditor finding: previously every connected
                    # client could call commands.execute() — meaning a
                    # passive viewer could arm/takeoff. Reject unless this ws
                    # holds the pilot role (the implicit-pilot fallback
                    # below covers the single-client case where no role has
                    # been set yet).
                    role = self._roles.get(id(ws))
                    # With no explicit pilot assigned, command authority belongs
                    # to the earliest-connected client (the session operator);
                    # later joiners observe. The previous `client_count == 1`
                    # gate stripped the operator's authority the instant ANY
                    # second client connected — an observer opening the page
                    # silently disabled the operator's commands, with no way to
                    # reclaim them (nothing in the frontend sends set_role /
                    # request_handoff). Earliest-connected preserves the GCS
                    # "one operator, rest observe" default with zero UI wiring.
                    # Fallback (operator is None): tests populate _clients
                    # directly, bypassing _order — a lone client still commands.
                    operator = next((c for c in self._order if c in self._clients and c not in self._assistants), None)
                    if operator is None:
                        operator = ws if self.client_count == 1 else None
                    is_implicit_pilot = self._pilot_ws is None and role is None and operator is ws
                    if role != "pilot" and not is_implicit_pilot:
                        await ws.send_text(
                            dumps(
                                {
                                    "type": "cmd_result",
                                    "ok": False,
                                    "error": lt("err_observer_no_cmd", self.link.locale),
                                }
                            )
                        )
                        continue
                    cmd = msg.get("cmd", "")
                    param = msg.get("param")
                    result = commands.execute(cmd, param, self.link, data=msg)
                    if result:
                        await ws.send_text(dumps({"type": "cmd_result", **result}))
        except WebSocketDisconnect:
            pass
        except (ConnectionError, RuntimeError):
            logger.warning("receive_loop error", exc_info=True)

    async def _push_loop(self, ws: WebSocket) -> None:
        # Use the monotonic emitted-count as our cursor for events. The array
        # itself is trimmed (100 → 50) periodically, so an index-based cursor
        # ended up replaying or dropping events depending on the cursor's
        # position at trim time (auditor drone_link C5).
        event_seq_cursor = self.link._events_emitted_total
        param_cursor = len(self.link.param_mgr._messages)
        param_gen = self.link.param_mgr._fetch_gen
        dl_cursor = len(self.link.mission._dl_messages)
        log_cursor = len(self.link.log_dl._log_messages)
        last_sent: dict = {}
        push_count = 0
        try:
            while True:
                if ws in self._assistants:
                    # It asks the page and reads its answers, not the stream.
                    await asyncio.sleep(1.0)
                    continue
                state = self.link.get_state()
                push_count += 1
                if push_count % 10 == 1:
                    delta = state
                else:
                    delta = {k: v for k, v in state.items() if last_sent.get(k) != v}
                    delta["type"] = "state"
                    delta["connected"] = state["connected"]
                if delta:
                    await ws.send_text(dumps(delta))
                    last_sent.update(state)
                with self.link._state_lock:
                    events = list(self.link.events)
                    events_total = self.link._events_emitted_total
                    dlmsg = list(self.link.mission._dl_messages)
                    logmsg = list(self.link.log_dl._log_messages)
                    pmsg = list(self.link.param_mgr._messages)
                    param_gen_now = self.link.param_mgr._fetch_gen
                # Send any events with seq > our last-sent seq. The array may
                # have trimmed older entries; if cursor < oldest-available
                # seq, we accept the loss (the trimmed events are gone).
                if events_total > event_seq_cursor:
                    for ev in events:
                        if ev.get("seq", 0) > event_seq_cursor:
                            out = {
                                "type": "event",
                                "time": ev["time"],
                                "text": ev["text"],
                                "event_type": ev.get("event_type", ""),
                            }
                            # The command an acknowledgement answers (DroneLink.add_event).
                            if "cmd" in ev:
                                out["cmd"] = ev["cmd"]
                            await ws.send_text(dumps(out))
                    event_seq_cursor = events_total
                if dl_cursor > len(dlmsg):
                    dl_cursor = 0
                if len(dlmsg) > dl_cursor:
                    for msg in dlmsg[dl_cursor:]:
                        await ws.send_text(dumps(msg))
                    dl_cursor = len(dlmsg)
                if log_cursor > len(logmsg):
                    log_cursor = 0
                if len(logmsg) > log_cursor:
                    for msg in logmsg[log_cursor:]:
                        await ws.send_text(dumps(msg))
                    log_cursor = len(logmsg)
                # A new request_all() clears _messages and refills it. Reset the
                # cursor on the generation change, not just on an observed length
                # drop: if the clear+refill lands within one push cycle and the
                # new length equals the old cursor, the length guard never fires
                # and 0 params are delivered (empty panel — the CI params flake).
                if param_gen_now != param_gen:
                    param_cursor = 0
                    param_gen = param_gen_now
                if param_cursor > len(pmsg):
                    param_cursor = 0
                if len(pmsg) > param_cursor:
                    batch = pmsg[param_cursor:]
                    pvals = [m for m in batch if m["type"] == "param_value"]
                    others = [m for m in batch if m["type"] != "param_value"]
                    if pvals:
                        await ws.send_text(
                            dumps(
                                {
                                    "type": "param_batch",
                                    "params": pvals,
                                }
                            )
                        )
                    for msg in others:
                        await ws.send_text(dumps(msg))
                    param_cursor = len(pmsg)
                if self.link.inspector_enabled:
                    await ws.send_text(
                        dumps(
                            {
                                "type": "inspector",
                                "messages": self.link.get_inspector_data(),
                            }
                        )
                    )
                with self.link._state_lock:
                    if self.link._console_buf:
                        text = "".join(self.link._console_buf)
                        self.link._console_buf.clear()
                    else:
                        text = ""
                if text:
                    await ws.send_text(
                        dumps(
                            {
                                "type": "console_output",
                                "text": text,
                            }
                        )
                    )
                interval = cfg.WS_PUSH_INTERVAL_CONNECTED if self.link.connected else cfg.WS_PUSH_INTERVAL_IDLE
                await asyncio.sleep(interval)
        except WebSocketDisconnect:
            pass
        except (ConnectionError, RuntimeError):
            logger.warning("push_loop error", exc_info=True)
