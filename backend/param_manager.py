"""Parameter management — MAVLink PARAM protocol."""
from __future__ import annotations
import json
import struct
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .drone_link import DroneLink


class ParamManager:
    def __init__(self, link: DroneLink):
        self._link = link
        self.params: dict[str, dict] = {}
        self.total_count = -1
        self.received_count = 0
        self.fetching = False
        self._fetch_start = 0.0
        self._messages: list[dict] = []  # kept for backward compat with ws_manager cursor

    def request_all(self) -> None:
        self.params.clear()
        self.total_count = -1
        self.received_count = 0
        self.fetching = True
        self._fetch_start = time.time()
        self._link.add_event('参数: 正在读取...')
        from pllink_proto import bm
        payload = struct.pack('<BB', self._link.sysid, 1)
        self._link.send(bm(21, payload, self._link.sq, 159))

    def handle_param_value(self, p: bytes, pl: int) -> None:
        if pl < 25:
            return
        value = struct.unpack_from('<f', p, 0)[0]
        count = struct.unpack_from('<H', p, 4)[0]
        index = struct.unpack_from('<H', p, 6)[0]
        name = bytes(p[8:24]).split(b'\x00')[0].decode('ascii', 'replace')
        ptype = p[24]

        if self.total_count < 0:
            self.total_count = count

        if name not in self.params:
            self.received_count += 1

        self.params[name] = {
            'name': name, 'value': value, 'type': ptype, 'index': index,
        }

        self._messages.append({
            'type': 'param_value',
            'name': name, 'value': value, 'ptype': ptype,
            'index': index, 'total': self.total_count,
            'received': self.received_count,
        })

        if self.received_count >= self.total_count > 0:
            self.fetching = False
            elapsed = time.time() - self._fetch_start
            self._link.add_event('参数: %d 个已读取 (%.1fs)' % (self.received_count, elapsed))
            self._messages.append({
                'type': 'params_complete', 'count': self.received_count,
            })
            if len(self._messages) > 2000:
                self._messages = self._messages[-1000:]

    def set_param(self, name: str, value: float) -> None:
        param = self.params.get(name)
        ptype = param['type'] if param else 9
        from pllink_proto import bm
        name_bytes = name.encode('ascii')[:16].ljust(16, b'\x00')
        payload = (struct.pack('<f', value) +
                   struct.pack('<BB', self._link.sysid, 1) +
                   name_bytes +
                   struct.pack('<B', ptype))
        self._link.send(bm(23, payload, self._link.sq, 168))
        self._link.add_event('参数: %s → %.4g' % (name, value))

    def save_to_file(self, path: str | None = None) -> str:
        if not path:
            save_dir = Path(__file__).resolve().parent.parent / 'params'
            save_dir.mkdir(exist_ok=True)
            path = str(save_dir / ('params_%s.json' % time.strftime('%Y%m%d_%H%M%S')))
        data = {name: p['value'] for name, p in sorted(self.params.items())}
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        self._link.add_event('参数: 已保存 %d 个 → %s' % (len(data), Path(path).name))
        return path

    def load_from_file(self, path: str) -> list[str]:
        with open(path) as f:
            data = json.load(f)
        changed = []
        for name, value in data.items():
            current = self.params.get(name)
            if current and abs(current['value'] - value) > 1e-7:
                self.set_param(name, value)
                changed.append(name)
                time.sleep(0.02)
        self._link.add_event('参数: 已加载 %d 个, %d 个变更' % (len(data), len(changed)))
        return changed

    def get_status(self) -> dict:
        return {
            'param_count': self.received_count,
            'param_total': self.total_count,
            'param_fetching': self.fetching,
        }
