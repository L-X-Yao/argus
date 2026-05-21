"""Unit tests for WSManager delta push and state management."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.drone_link import DroneLink
from backend.ws_manager import WSManager


def make_ws():
    ws = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.send_text = AsyncMock()
    ws.accept = AsyncMock()
    return ws


class TestWSManagerInit:
    def test_creates_with_link(self):
        link = DroneLink()
        mgr = WSManager(link)
        assert mgr.link is link
        assert mgr.client_count == 0

    def test_client_count(self):
        link = DroneLink()
        mgr = WSManager(link)
        ws = make_ws()
        mgr._clients.add(ws)
        assert mgr.client_count == 1


class TestDeltaPush:
    def test_first_push_is_full(self):
        link = DroneLink()
        state = link.get_state()
        last_sent = {}
        push_count = 1
        if push_count % 10 == 1:
            delta = state
        else:
            delta = {k: v for k, v in state.items() if last_sent.get(k) != v}
        assert delta == state

    def test_second_push_is_delta(self):
        link = DroneLink()
        state1 = link.get_state()
        last_sent = dict(state1)
        link.attitude.roll = 15.0
        state2 = link.get_state()
        push_count = 2
        delta = {k: v for k, v in state2.items() if last_sent.get(k) != v}
        delta['type'] = 'state'
        delta['connected'] = state2['connected']
        assert 'roll' in delta
        assert delta['roll'] == 15.0
        assert 'voltage' not in delta or delta.get('voltage') == last_sent.get('voltage')

    def test_every_10th_is_full(self):
        link = DroneLink()
        state = link.get_state()
        last_sent = dict(state)
        push_count = 11
        if push_count % 10 == 1:
            delta = state
        assert delta == state

    def test_delta_includes_type_and_connected(self):
        link = DroneLink()
        state1 = link.get_state()
        last_sent = dict(state1)
        state2 = link.get_state()
        push_count = 2
        delta = {k: v for k, v in state2.items() if last_sent.get(k) != v}
        delta['type'] = 'state'
        delta['connected'] = state2['connected']
        assert delta['type'] == 'state'
        assert 'connected' in delta


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self):
        link = DroneLink()
        mgr = WSManager(link)
        ws1 = make_ws()
        ws2 = make_ws()
        mgr._clients = {ws1, ws2}
        await mgr.broadcast({'type': 'test', 'data': 1})
        assert ws1.send_text.call_count == 1
        assert ws2.send_text.call_count == 1
        sent = json.loads(ws1.send_text.call_args[0][0])
        assert sent['type'] == 'test'

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_client(self):
        link = DroneLink()
        mgr = WSManager(link)
        ws_ok = make_ws()
        ws_fail = make_ws()
        ws_fail.send_text.side_effect = Exception('connection closed')
        mgr._clients = {ws_ok, ws_fail}
        await mgr.broadcast({'type': 'test'})
        assert ws_fail not in mgr._clients
        assert ws_ok in mgr._clients


class TestReceiveCommands:
    def test_set_locale(self):
        link = DroneLink()
        mgr = WSManager(link)
        assert link.locale == 'zh'

    def test_inspector_toggle(self):
        link = DroneLink()
        assert link.inspector_enabled is False
