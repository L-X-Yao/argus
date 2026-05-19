"""Integration tests: simulator + backend + WebSocket."""
import asyncio
import json
import sys
from pathlib import Path

import pytest
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def ws_connect(ws_url, timeout=5):
    return await asyncio.wait_for(
        websockets.connect(ws_url),
        timeout=timeout,
    )


async def recv_until(ws, predicate, timeout=10):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=2)
            msg = json.loads(raw)
            if predicate(msg):
                return msg
        except asyncio.TimeoutError:
            continue
    raise TimeoutError('predicate not met within %ds' % timeout)


async def ensure_connected(ws, ws_url, sim_port, timeout=15):
    """Disconnect any prior connection, then connect fresh and wait for telemetry."""
    await ws.send(json.dumps({'type': 'disconnect'}))
    await asyncio.sleep(1.5)
    await ws.send(json.dumps({
        'type': 'connect',
        'port': f'tcp:localhost:{sim_port}',
    }))
    await recv_until(ws, lambda m: m.get('type') == 'connect_result', timeout=10)
    await recv_until(
        ws, lambda m: (m.get('type') == 'state' and m.get('connected')
                       and m.get('gps_sats', 0) > 0),
        timeout=timeout,
    )


class TestConnection:
    def test_health(self, backend_url):
        import httpx
        r = httpx.get(f'{backend_url}/health')
        assert r.status_code == 200
        assert r.json()['ok'] is True

    def test_ports_api(self, backend_url):
        import httpx
        r = httpx.get(f'{backend_url}/api/ports')
        assert r.status_code == 200
        assert 'ports' in r.json()

    def test_ws_connect_receive_state(self, ws_url):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                msg = await recv_until(ws, lambda m: m.get('type') == 'state')
                assert 'connected' in msg
                assert 'mode' in msg
            finally:
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_connect_to_sim(self, ws_url, sim_port):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                    'baud': 57600,
                }))
                msg = await recv_until(ws, lambda m: m.get('type') == 'connect_result')
                assert msg['ok'] is True
                state = await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('connected'),
                    timeout=8,
                )
                assert state['connected']
                assert state['gps_sats'] > 0
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())


class TestTelemetry:
    def test_receives_position(self, ws_url, sim_port):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                }))
                await recv_until(ws, lambda m: m.get('type') == 'connect_result')
                state = await recv_until(
                    ws, lambda m: m.get('type') == 'state' and abs(m.get('lat', 0)) > 1,
                    timeout=10,
                )
                assert abs(state['lat'] - 34.258) < 0.01
                assert abs(state['lon'] - 108.942) < 0.01
                assert state['gps_fix'] in ('3D', 'RTK固定', 'RTK浮动', '差分')
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_receives_battery(self, ws_url, sim_port):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                }))
                await recv_until(ws, lambda m: m.get('type') == 'connect_result')
                state = await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('voltage', 0) > 20,
                    timeout=10,
                )
                assert state['voltage'] > 20
                assert state['remaining'] > 0
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_receives_events(self, ws_url, sim_port):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                }))
                await recv_until(ws, lambda m: m.get('type') == 'connect_result')
                event = await recv_until(
                    ws, lambda m: m.get('type') == 'event',
                    timeout=10,
                )
                assert 'text' in event
                assert 'time' in event
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())


class TestCommands:
    def test_arm_disarm(self, ws_url, sim_port):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                }))
                await recv_until(ws, lambda m: m.get('type') == 'connect_result')
                await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('connected'),
                    timeout=8,
                )
                await ws.send(json.dumps({'type': 'command', 'cmd': 'arm'}))
                armed_state = await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('armed'),
                    timeout=8,
                )
                assert armed_state['armed']

                await ws.send(json.dumps({'type': 'command', 'cmd': 'disarm'}))
                disarmed_state = await recv_until(
                    ws, lambda m: m.get('type') == 'state' and not m.get('armed'),
                    timeout=8,
                )
                assert not disarmed_state['armed']
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_mode_change(self, ws_url, sim_port):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                }))
                await recv_until(ws, lambda m: m.get('type') == 'connect_result')
                await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('connected'),
                    timeout=8,
                )
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mode', 'param': 2,
                }))
                state = await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('mode_id') == 2,
                    timeout=8,
                )
                assert state['mode'] == '定高'
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_disconnect(self, ws_url, sim_port):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                }))
                await recv_until(ws, lambda m: m.get('type') == 'connect_result')
                await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('connected'),
                    timeout=8,
                )
                await ws.send(json.dumps({'type': 'disconnect'}))
                result = await recv_until(
                    ws, lambda m: m.get('type') == 'connect_result',
                    timeout=5,
                )
                assert result['ok']
                state = await recv_until(
                    ws, lambda m: m.get('type') == 'state' and not m.get('connected'),
                    timeout=8,
                )
                assert not state['connected']
            finally:
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())


class TestLogAndReconnect:
    def test_log_active_after_connect(self, ws_url, sim_port):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                }))
                await recv_until(ws, lambda m: m.get('type') == 'connect_result')
                state = await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('connected'),
                    timeout=8,
                )
                assert state.get('log_active') is True
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_log_download_api(self, backend_url, ws_url, sim_port):
        async def run():
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                }))
                await recv_until(ws, lambda m: m.get('type') == 'connect_result')
                await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('connected'),
                    timeout=8,
                )
                await asyncio.sleep(1)
                import httpx
                r = httpx.get(f'{backend_url}/api/log')
                assert r.status_code == 200
                assert 'time,roll,pitch' in r.text
                lines = r.text.strip().split('\n')
                assert len(lines) >= 2
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_log_not_available_disconnected(self, backend_url):
        import httpx
        r = httpx.get(f'{backend_url}/api/log')
        assert r.status_code == 404


class TestMission:
    def test_mission_upload(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(3)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                await asyncio.sleep(1)
                waypoints = [
                    {'lat': 34.259, 'lon': 108.943, 'alt': 30, 'drop': False, 'delay': 0},
                    {'lat': 34.260, 'lon': 108.944, 'alt': 30, 'drop': True, 'delay': 0},
                ]
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_upload',
                    'waypoints': waypoints, 'takeoff_alt': 30,
                }))
                ack = await recv_until(
                    ws, lambda m: m.get('type') == 'event' and '任务确认' in m.get('text', ''),
                    timeout=15,
                )
                assert '成功' in ack['text']
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_mission_clear(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(1)
            ws = await ws_connect(ws_url)
            try:
                await ws.send(json.dumps({
                    'type': 'connect',
                    'port': f'tcp:localhost:{sim_port}',
                }))
                await recv_until(ws, lambda m: m.get('type') == 'connect_result', timeout=8)
                await recv_until(
                    ws, lambda m: m.get('type') == 'state' and m.get('connected'),
                    timeout=12,
                )
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_clear',
                }))
                event = await recv_until(
                    ws, lambda m: m.get('type') == 'event' and '清除' in m.get('text', ''),
                    timeout=12,
                )
                assert '清除' in event['text']
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())
