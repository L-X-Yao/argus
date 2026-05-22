from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from . import commands
from .config import cfg
from .drone_link import DroneLink
from .locale_text import lt

logger = logging.getLogger(__name__)


class WSManager:
    def __init__(self, link: DroneLink):
        self.link = link
        self._clients: set[WebSocket] = set()
        self._pilot_ws: WebSocket | None = None
        self._roles: dict[int, str] = {}

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def broadcast(self, msg: dict) -> None:
        text = json.dumps(msg)
        for ws in list(self._clients):
            try:
                await ws.send_text(text)
            except (ConnectionError, RuntimeError):
                self._clients.discard(ws)

    async def handle_client(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
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

    async def _receive_loop(self, ws: WebSocket) -> None:
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_type = msg.get('type', '')
                if msg_type == 'connect':
                    port = msg.get('port', 'tcp:localhost:5770')
                    baud = msg.get('baud', cfg.SERIAL_BAUD)
                    protocol = msg.get('protocol', 'auto')
                    if not isinstance(port, str) or len(port) > 200 or '\x00' in port:
                        await ws.send_text(json.dumps({
                            'type': 'connect_result', 'ok': False, 'error': 'Invalid port',
                        }))
                        continue
                    try:
                        baud = int(baud)
                    except (TypeError, ValueError):
                        baud = cfg.SERIAL_BAUD
                    if baud not in cfg.VALID_BAUD_RATES:
                        baud = cfg.SERIAL_BAUD
                    if protocol not in cfg.VALID_PROTOCOLS:
                        protocol = 'auto'
                    ok = self.link.connect(port, baud, protocol=protocol)
                    await ws.send_text(json.dumps({
                        'type': 'connect_result', 'ok': ok,
                        'error': '' if ok else lt('err_connect', self.link.locale),
                    }))
                elif msg_type == 'disconnect':
                    self.link.disconnect()
                    await ws.send_text(json.dumps({
                        'type': 'connect_result', 'ok': True, 'error': '',
                    }))
                elif msg_type == 'set_locale':
                    locale = msg.get('locale', 'zh')
                    if locale in ('zh', 'en', 'ja', 'ko', 'de', 'fr', 'es', 'pt', 'ru', 'ar'):
                        self.link.locale = locale
                elif msg_type == 'set_role':
                    role = msg.get('role', 'observer')
                    self._roles[id(ws)] = role
                    if role == 'pilot':
                        self._pilot_ws = ws
                    await self.broadcast({'type': 'role_update', 'clients': self.client_count,
                                          'pilot_connected': self._pilot_ws in self._clients})
                elif msg_type == 'request_handoff':
                    if self._pilot_ws and self._pilot_ws != ws and self._pilot_ws in self._clients:
                        await self._pilot_ws.send_text(json.dumps({'type': 'handoff_request', 'from': id(ws)}))
                    else:
                        self._pilot_ws = ws
                        self._roles[id(ws)] = 'pilot'
                        await ws.send_text(json.dumps({'type': 'handoff_granted'}))
                elif msg_type == 'handoff_accept':
                    target_id = msg.get('target')
                    for client in self._clients:
                        if id(client) == target_id:
                            self._pilot_ws = client
                            self._roles[id(client)] = 'pilot'
                            self._roles[id(ws)] = 'observer'
                            await client.send_text(json.dumps({'type': 'handoff_granted'}))
                            await ws.send_text(json.dumps({'type': 'handoff_released'}))
                            break
                elif msg_type == 'command':
                    cmd = msg.get('cmd', '')
                    param = msg.get('param')
                    result = commands.execute(cmd, param, self.link, data=msg)
                    if result:
                        await ws.send_text(json.dumps({'type': 'cmd_result', **result}))
        except WebSocketDisconnect:
            pass
        except (ConnectionError, RuntimeError):
            logger.warning('receive_loop error', exc_info=True)

    async def _push_loop(self, ws: WebSocket) -> None:
        event_cursor = len(self.link.events)
        param_cursor = len(self.link.param_mgr._messages)
        dl_cursor = len(self.link.mission._dl_messages)
        log_cursor = len(self.link.log_dl._log_messages)
        last_sent: dict = {}
        push_count = 0
        try:
            while True:
                state = self.link.get_state()
                push_count += 1
                if push_count % 10 == 1:
                    delta = state
                else:
                    delta = {k: v for k, v in state.items() if last_sent.get(k) != v}
                    delta['type'] = 'state'
                    delta['connected'] = state['connected']
                if delta:
                    await ws.send_text(json.dumps(delta))
                    last_sent.update(state)
                with self.link._state_lock:
                    events = list(self.link.events)
                    dlmsg = list(self.link.mission._dl_messages)
                    logmsg = list(self.link.log_dl._log_messages)
                    pmsg = list(self.link.param_mgr._messages)
                if event_cursor > len(events):
                    event_cursor = 0
                if len(events) > event_cursor:
                    for ev in events[event_cursor:]:
                        await ws.send_text(json.dumps({
                            'type': 'event',
                            'time': ev['time'],
                            'text': ev['text'],
                            'event_type': ev.get('event_type', ''),
                        }))
                    event_cursor = len(events)
                if dl_cursor > len(dlmsg):
                    dl_cursor = 0
                if len(dlmsg) > dl_cursor:
                    for msg in dlmsg[dl_cursor:]:
                        await ws.send_text(json.dumps(msg))
                    dl_cursor = len(dlmsg)
                if log_cursor > len(logmsg):
                    log_cursor = 0
                if len(logmsg) > log_cursor:
                    for msg in logmsg[log_cursor:]:
                        await ws.send_text(json.dumps(msg))
                    log_cursor = len(logmsg)
                if param_cursor > len(pmsg):
                    param_cursor = 0
                if len(pmsg) > param_cursor:
                    batch = pmsg[param_cursor:]
                    pvals = [m for m in batch if m['type'] == 'param_value']
                    others = [m for m in batch if m['type'] != 'param_value']
                    if pvals:
                        await ws.send_text(json.dumps({
                            'type': 'param_batch', 'params': pvals,
                        }))
                    for msg in others:
                        await ws.send_text(json.dumps(msg))
                    param_cursor = len(pmsg)
                if self.link.inspector_enabled:
                    await ws.send_text(json.dumps({
                        'type': 'inspector',
                        'messages': self.link.get_inspector_data(),
                    }))
                with self.link._state_lock:
                    if self.link._console_buf:
                        text = ''.join(self.link._console_buf)
                        self.link._console_buf.clear()
                    else:
                        text = ''
                if text:
                    await ws.send_text(json.dumps({
                        'type': 'console_output', 'text': text,
                    }))
                interval = cfg.WS_PUSH_INTERVAL_CONNECTED if self.link.connected else cfg.WS_PUSH_INTERVAL_IDLE
                await asyncio.sleep(interval)
        except WebSocketDisconnect:
            pass
        except (ConnectionError, RuntimeError):
            logger.warning('push_loop error', exc_info=True)
