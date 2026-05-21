from __future__ import annotations
import asyncio
import json
from fastapi import WebSocket, WebSocketDisconnect

from .config import cfg
from .drone_link import DroneLink
from . import commands


class WSManager:
    def __init__(self, link: DroneLink):
        self.link = link
        self._clients: set[WebSocket] = set()

    @property
    def client_count(self) -> int:
        return len(self._clients)

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
        except Exception:
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
                    ok = self.link.connect(port, baud, protocol=protocol)
                    await ws.send_text(json.dumps({
                        'type': 'connect_result', 'ok': ok,
                        'error': '' if ok else '无法连接',
                    }))
                elif msg_type == 'disconnect':
                    self.link.disconnect()
                    await ws.send_text(json.dumps({
                        'type': 'connect_result', 'ok': True, 'error': '',
                    }))
                elif msg_type == 'set_locale':
                    self.link.locale = msg.get('locale', 'zh')
                elif msg_type == 'command':
                    cmd = msg.get('cmd', '')
                    param = msg.get('param')
                    result = commands.execute(cmd, param, self.link, data=msg)
                    if result:
                        await ws.send_text(json.dumps({'type': 'cmd_result', **result}))
        except (WebSocketDisconnect, Exception):
            return

    async def _push_loop(self, ws: WebSocket) -> None:
        event_cursor = len(self.link.events)
        param_cursor = len(self.link.param_mgr._messages)
        dl_cursor = len(self.link._dl_messages)
        log_cursor = len(self.link._log_messages)
        try:
            while True:
                state = self.link.get_state()
                await ws.send_text(json.dumps(state))
                events = self.link.events
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
                dlmsg = self.link._dl_messages
                if dl_cursor > len(dlmsg):
                    dl_cursor = 0
                if len(dlmsg) > dl_cursor:
                    for msg in dlmsg[dl_cursor:]:
                        await ws.send_text(json.dumps(msg))
                    dl_cursor = len(dlmsg)
                logmsg = self.link._log_messages
                if log_cursor > len(logmsg):
                    log_cursor = 0
                if len(logmsg) > log_cursor:
                    for msg in logmsg[log_cursor:]:
                        await ws.send_text(json.dumps(msg))
                    log_cursor = len(logmsg)
                pmsg = self.link.param_mgr._messages
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
                if self.link._console_buf:
                    text = ''.join(self.link._console_buf)
                    self.link._console_buf.clear()
                    await ws.send_text(json.dumps({
                        'type': 'console_output', 'text': text,
                    }))
                interval = cfg.WS_PUSH_INTERVAL_CONNECTED if self.link.connected else cfg.WS_PUSH_INTERVAL_IDLE
                await asyncio.sleep(interval)
        except (WebSocketDisconnect, Exception):
            return
