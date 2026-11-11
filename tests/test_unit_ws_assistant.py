"""The assistant's place among the websocket clients (backend/ws_manager.py).

An assistant (backend/mcp_server.py) asks the operator's page and reads its answers. It never
holds command authority, whatever order the clients connected in.
"""

import asyncio
import json

import pytest
import pytest_asyncio
from fastapi import WebSocketDisconnect

from backend.drone_link import DroneLink
from backend.locale_text import lt
from backend.ws_manager import _CLOSED_RUNNING, _MAX_WAITING, _NO_PAGE, _PAGE_CLOSED, WSManager

pytestmark = pytest.mark.asyncio


class Client:
    """A websocket the manager talks to: what it says goes in with say(), what it gets is in got."""

    def __init__(self):
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.got: list[dict] = []

    async def accept(self):
        pass

    async def receive_text(self):
        text = await self.inbox.get()
        if text is None:
            raise WebSocketDisconnect()
        return text

    async def send_text(self, text):
        self.got.append(json.loads(text))

    def say(self, **msg):
        self.inbox.put_nowait(json.dumps(msg))

    def leave(self):
        self.inbox.put_nowait(None)

    def of(self, kind: str) -> list[dict]:
        return [m for m in self.got if m.get("type") == kind]


async def settle():
    for _ in range(5):
        await asyncio.sleep(0.01)


@pytest_asyncio.fixture
async def mgr():
    manager = WSManager(DroneLink())
    tasks: list[asyncio.Task] = []

    async def join() -> Client:
        client = Client()
        tasks.append(asyncio.create_task(manager.handle_client(client)))
        await settle()
        return client

    manager.join = join
    yield manager
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def assistant(mgr) -> Client:
    client = await mgr.join()
    client.say(type="assistant_hello")
    await settle()
    assert client.of("assistant_welcome")
    return client


def observer_refusal(client: Client) -> bool:
    return any(m.get("error") == lt("err_observer_no_cmd", "zh") for m in client.of("cmd_result"))


class TestNoAuthority:
    async def test_an_assistant_that_came_first_is_not_the_operator(self, mgr):
        await assistant(mgr)
        page = await mgr.join()
        page.say(type="command", cmd="arm")
        await settle()
        assert page.of("cmd_result") and not observer_refusal(page)
        assert mgr.operator() is page

    @pytest.mark.parametrize(
        "msg",
        [
            {"type": "command", "cmd": "arm"},
            {"type": "connect", "port": "tcp:localhost:5770"},
            {"type": "disconnect"},
            {"type": "set_role", "role": "pilot"},
            {"type": "request_handoff"},
            {"type": "assistant_reply", "id": "a1", "ok": True},
        ],
    )
    async def test_an_assistant_sends_nothing_but_its_own_messages(self, mgr, msg):
        ai = await assistant(mgr)
        ai.say(**msg)
        await settle()
        assert ai.of("assistant_error")
        assert not ai.of("cmd_result") and not ai.of("connect_result") and not ai.of("handoff_granted")
        assert mgr._pilot_ws is None

    async def test_a_page_that_turns_assistant_gives_up_the_pilot_role(self, mgr):
        page = await mgr.join()
        page.say(type="request_handoff")
        await settle()
        assert mgr._pilot_ws is page
        page.say(type="assistant_hello")
        await settle()
        assert mgr._pilot_ws is None and mgr.operator() is None

    async def test_pages_do_not_count_assistants(self, mgr):
        await assistant(mgr)
        await mgr.join()
        assert (mgr.client_count, mgr.assistant_count) == (1, 1)

    async def test_an_assistant_gets_no_telemetry_stream(self, mgr):
        ai = await assistant(mgr)
        ai.got.clear()
        await asyncio.sleep(1.3)
        assert not ai.of("state")


class TestAskingThePage:
    async def test_a_request_reaches_the_operator_page_and_its_answer_comes_back(self, mgr):
        page = await mgr.join()
        viewer = await mgr.join()
        ai = await assistant(mgr)
        ai.say(type="assistant_request", id="r-1", kind="status", args={})
        await settle()
        asked = page.of("assistant_request")
        assert [(m["kind"], m["args"]) for m in asked] == [("status", {})]
        assert asked[0]["id"] != "r-1"  # the page sees a key of the manager's, not the assistant's id
        assert not viewer.of("assistant_request")
        page.say(type="assistant_reply", id=asked[0]["id"], ok=True, result={"mode": "LOITER"})
        await settle()
        assert ai.of("assistant_reply") == [
            {"type": "assistant_reply", "id": "r-1", "ok": True, "result": {"mode": "LOITER"}}
        ]

    async def test_the_pilot_is_asked_rather_than_the_first_page(self, mgr):
        first = await mgr.join()
        pilot = await mgr.join()
        pilot.say(type="request_handoff")
        await settle()
        ai = await assistant(mgr)
        ai.say(type="assistant_request", id="r", kind="status", args={})
        await settle()
        assert pilot.of("assistant_request") and not first.of("assistant_request")

    async def test_with_no_page_open_the_answer_says_so_at_once(self, mgr):
        ai = await assistant(mgr)
        ai.say(type="assistant_request", id="r", kind="status", args={})
        await settle()
        assert ai.of("assistant_reply") == [{"type": "assistant_reply", "id": "r", "ok": False, "error": _NO_PAGE}]

    async def test_only_the_page_asked_answers_and_only_once(self, mgr):
        page = await mgr.join()
        other = await mgr.join()
        ai = await assistant(mgr)
        ai.say(type="assistant_request", id="r", kind="status", args={})
        await settle()
        key = page.of("assistant_request")[0]["id"]
        other.say(type="assistant_reply", id=key, ok=True, result="from another page")
        page.say(type="assistant_reply", id=key, ok=True, result="first")
        page.say(type="assistant_reply", id=key, ok=True, result="second")
        await settle()
        assert [m["result"] for m in ai.of("assistant_reply")] == ["first"]

    async def test_a_withdrawal_goes_to_the_page_which_answers_it(self, mgr):
        # Withdrawn if it still waits; its result if the operator has approved it.
        page = await mgr.join()
        ai = await assistant(mgr)
        ai.say(type="assistant_request", id="r", kind="propose_mission", args={"waypoints": []})
        await settle()
        key = page.of("assistant_request")[0]["id"]
        ai.say(type="assistant_cancel", id="r")
        await settle()
        assert page.of("assistant_cancel") == [{"type": "assistant_cancel", "id": key}]
        page.say(type="assistant_reply", id=key, ok=False, error="Withdrawn", result={"outcome": "withdrawn"})
        await settle()
        assert ai.of("assistant_reply") == [
            {
                "type": "assistant_reply",
                "id": "r",
                "ok": False,
                "error": "Withdrawn",
                "result": {"outcome": "withdrawn"},
            }
        ]

    async def test_where_a_request_stands_reaches_the_assistant(self, mgr):
        page = await mgr.join()
        other = await mgr.join()
        ai = await assistant(mgr)
        ai.say(type="assistant_request", id="r", kind="propose_mission", args={})
        await settle()
        key = page.of("assistant_request")[0]["id"]
        page.say(type="assistant_state", id=key, state="waiting")
        other.say(type="assistant_state", id=key, state="running")  # not the page asked
        page.say(type="assistant_state", id=key, state="done")  # no such state
        page.say(type="assistant_state", id=key, state="running")
        await settle()
        assert [m["state"] for m in ai.of("assistant_state")] == ["waiting", "running"]
        assert {m["id"] for m in ai.of("assistant_state")} == {"r"}

    async def test_a_page_that_closes_while_the_change_runs_says_it_may_be_made(self, mgr):
        page = await mgr.join()
        ai = await assistant(mgr)
        ai.say(type="assistant_request", id="r", kind="propose_mission", args={})
        await settle()
        key = page.of("assistant_request")[0]["id"]
        page.say(type="assistant_state", id=key, state="running")
        await settle()
        page.leave()
        await settle()
        assert ai.of("assistant_reply") == [
            {"type": "assistant_reply", "id": "r", "ok": False, "error": _CLOSED_RUNNING}
        ]

    async def test_keys_differ_from_one_backend_to_the_next(self):
        # A page keeps its requests across a restart of the backend: an answer to one of before
        # must not land on a new one.
        pages = [Client(), Client()]
        keys = []
        for page in pages:
            manager = WSManager(DroneLink())
            manager._clients.add(page)
            manager._order.append(page)
            ai = Client()
            manager._clients.add(ai)
            manager._assistants.add(ai)
            await manager._from_assistant(ai, "assistant_request", {"id": "r", "kind": "status", "args": {}})
            keys.append(page.of("assistant_request")[0]["id"])
        assert keys[0] != keys[1]

    async def test_requests_of_an_assistant_that_left_are_withdrawn(self, mgr):
        page = await mgr.join()
        ai = await assistant(mgr)
        assert page.of("assistant_presence")[-1]["count"] == 1
        ai.say(type="assistant_request", id="r", kind="propose_mission", args={})
        await settle()
        ai.leave()
        await settle()
        assert page.of("assistant_cancel")
        assert page.of("assistant_presence")[-1]["count"] == 0

    async def test_requests_to_a_page_that_closed_fail(self, mgr):
        page = await mgr.join()
        ai = await assistant(mgr)
        ai.say(type="assistant_request", id="r", kind="propose_mission", args={})
        await settle()
        page.leave()
        await settle()
        assert ai.of("assistant_reply") == [{"type": "assistant_reply", "id": "r", "ok": False, "error": _PAGE_CLOSED}]

    async def test_a_page_that_opens_later_learns_an_assistant_is_there(self, mgr):
        await assistant(mgr)
        page = await mgr.join()
        assert page.of("assistant_presence") == [{"type": "assistant_presence", "count": 1}]

    async def test_an_assistant_in_a_loop_floods_nobody(self, mgr):
        page = await mgr.join()
        ai = await assistant(mgr)
        for i in range(_MAX_WAITING + 1):
            ai.say(type="assistant_request", id=f"r{i}", kind="status", args={})
        await settle()
        assert len(page.of("assistant_request")) == _MAX_WAITING
        assert [m["id"] for m in ai.of("assistant_reply")] == [f"r{_MAX_WAITING}"]

    @pytest.mark.parametrize(
        "msg",
        [
            {"type": "assistant_request", "kind": "status", "args": {}},
            {"type": "assistant_request", "id": "", "kind": "status", "args": {}},
            {"type": "assistant_request", "id": "x" * 101, "kind": "status", "args": {}},
        ],
    )
    async def test_a_request_without_a_usable_id_is_dropped(self, mgr, msg):
        page = await mgr.join()
        ai = await assistant(mgr)
        ai.say(**msg)
        await settle()
        assert not page.of("assistant_request") and not ai.of("assistant_reply")

    async def test_a_malformed_request_is_answered(self, mgr):
        page = await mgr.join()
        ai = await assistant(mgr)
        ai.say(type="assistant_request", id="r", kind=["status"], args={})
        ai.say(type="assistant_request", id="s", kind="status", args=[])
        await settle()
        assert [m["ok"] for m in ai.of("assistant_reply")] == [False, False]
        assert not page.of("assistant_request")

    async def test_json_that_is_no_object_does_not_end_the_connection(self, mgr):
        page = await mgr.join()
        page.inbox.put_nowait("[1, 2]")
        page.say(type="command", cmd="arm")
        await settle()
        assert page.of("cmd_result")
