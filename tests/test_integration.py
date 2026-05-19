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


class TestParams:
    def test_param_request_all(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(1)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'param_request_all',
                }))
                batch = await recv_until(
                    ws, lambda m: m.get('type') == 'param_batch',
                    timeout=15,
                )
                assert 'params' in batch
                assert len(batch['params']) > 0
                p0 = batch['params'][0]
                assert 'name' in p0
                assert 'value' in p0
                assert p0['total'] > 10
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_param_set(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(1)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'param_request_all',
                }))
                await recv_until(
                    ws, lambda m: m.get('type') == 'params_complete',
                    timeout=15,
                )
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'param_set',
                    'name': 'BATT_CAPACITY', 'value': 9999,
                }))
                batch = await recv_until(
                    ws, lambda m: (m.get('type') == 'param_batch' and
                                   any(p.get('name') == 'BATT_CAPACITY' and
                                       abs(p.get('value', 0) - 9999) < 1
                                       for p in m.get('params', []))),
                    timeout=10,
                )
                updated = [p for p in batch['params']
                           if p['name'] == 'BATT_CAPACITY'][0]
                assert abs(updated['value'] - 9999) < 1
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_param_state_in_telemetry(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(1)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'param_request_all',
                }))
                state = await recv_until(
                    ws, lambda m: (m.get('type') == 'state' and
                                   m.get('param_total', -1) > 0),
                    timeout=15,
                )
                assert state['param_total'] > 10
                assert state['param_count'] >= 0
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())


class TestFirmwareVersion:
    def test_firmware_version_in_state(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(1)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                state = await recv_until(
                    ws, lambda m: (m.get('type') == 'state' and
                                   m.get('fw_version', '') != ''),
                    timeout=15,
                )
                assert state['fw_version'] == 'v4.5.7'
                assert len(state['fw_git']) > 0
                assert state['board_id'] == 56
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())


class TestMissionDownload:
    def test_upload_then_download(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(2)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                await asyncio.sleep(1)
                waypoints = [
                    {'lat': 34.259, 'lon': 108.943, 'alt': 50, 'drop': False, 'delay': 0},
                    {'lat': 34.260, 'lon': 108.944, 'alt': 60, 'drop': False, 'delay': 0},
                ]
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_upload',
                    'waypoints': waypoints, 'takeoff_alt': 30,
                }))
                await recv_until(
                    ws, lambda m: m.get('type') == 'event' and '任务确认' in m.get('text', '') and '成功' in m.get('text', ''),
                    timeout=15,
                )
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_download',
                }))
                dl = await recv_until(
                    ws, lambda m: m.get('type') == 'mission_downloaded',
                    timeout=15,
                )
                assert len(dl['waypoints']) == 2
                assert abs(dl['waypoints'][0]['lat'] - 34.259) < 0.001
                assert abs(dl['waypoints'][1]['alt'] - 60) < 1
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_download_empty_mission(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(1)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_clear',
                }))
                await recv_until(
                    ws, lambda m: m.get('type') == 'event' and '清除' in m.get('text', ''),
                    timeout=10,
                )
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_download',
                }))
                event = await recv_until(
                    ws, lambda m: m.get('type') == 'event' and '无任务' in m.get('text', ''),
                    timeout=10,
                )
                assert '无任务' in event['text']
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())


class TestDataStreams:
    def test_rc_channels_in_state(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(1)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                state = await recv_until(
                    ws, lambda m: (m.get('type') == 'state' and
                                   len(m.get('rc', [])) >= 4 and
                                   m['rc'][0] > 0),
                    timeout=15,
                )
                assert len(state['rc']) >= 8
                assert 1000 <= state['rc'][0] <= 2000
                assert 'rc_rssi' in state
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_vibration_in_state(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(1)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                state = await recv_until(
                    ws, lambda m: (m.get('type') == 'state' and
                                   len(m.get('vibe', [])) == 3 and
                                   m['vibe'][0] > 0),
                    timeout=15,
                )
                assert state['vibe'][0] > 0
                assert state['vibe'][1] > 0
                assert state['vibe'][2] > 0
                assert len(state['vibe_clip']) == 3
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_servo_output_in_state(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(1)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                state = await recv_until(
                    ws, lambda m: (m.get('type') == 'state' and
                                   len(m.get('servo', [])) >= 4 and
                                   m['servo'][0] > 0),
                    timeout=15,
                )
                assert len(state['servo']) >= 8
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())


class TestMissionAdvanced:
    def test_upload_with_speed_roundtrip(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(2)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                await asyncio.sleep(1)
                waypoints = [
                    {'lat': 34.259, 'lon': 108.943, 'alt': 50, 'drop': False,
                     'delay': 0, 'speed': 8.0, 'type': 'wp', 'loiter_param': 0},
                    {'lat': 34.260, 'lon': 108.944, 'alt': 60, 'drop': False,
                     'delay': 0, 'speed': 0, 'type': 'wp', 'loiter_param': 0},
                ]
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_upload',
                    'waypoints': waypoints, 'takeoff_alt': 30,
                }))
                await recv_until(
                    ws, lambda m: m.get('type') == 'event' and '任务确认' in m.get('text', '') and '成功' in m.get('text', ''),
                    timeout=15,
                )
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_download',
                }))
                dl = await recv_until(
                    ws, lambda m: m.get('type') == 'mission_downloaded',
                    timeout=15,
                )
                assert len(dl['waypoints']) == 2
                assert abs(dl['waypoints'][0]['speed'] - 8.0) < 0.1
                assert dl['waypoints'][1]['speed'] == 0
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())

    def test_upload_with_loiter_roundtrip(self, ws_url, sim_port):
        async def run():
            await asyncio.sleep(2)
            ws = await ws_connect(ws_url)
            try:
                await ensure_connected(ws, ws_url, sim_port, timeout=20)
                await asyncio.sleep(1)
                waypoints = [
                    {'lat': 34.259, 'lon': 108.943, 'alt': 50, 'drop': False,
                     'delay': 0, 'speed': 0, 'type': 'loiter_turns', 'loiter_param': 3},
                    {'lat': 34.260, 'lon': 108.944, 'alt': 60, 'drop': False,
                     'delay': 0, 'speed': 0, 'type': 'loiter_time', 'loiter_param': 15},
                ]
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_upload',
                    'waypoints': waypoints, 'takeoff_alt': 30,
                }))
                await recv_until(
                    ws, lambda m: m.get('type') == 'event' and '任务确认' in m.get('text', '') and '成功' in m.get('text', ''),
                    timeout=15,
                )
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({
                    'type': 'command', 'cmd': 'mission_download',
                }))
                dl = await recv_until(
                    ws, lambda m: m.get('type') == 'mission_downloaded',
                    timeout=15,
                )
                assert len(dl['waypoints']) == 2
                assert dl['waypoints'][0]['type'] == 'loiter_turns'
                assert abs(dl['waypoints'][0]['loiter_param'] - 3) < 0.1
                assert dl['waypoints'][1]['type'] == 'loiter_time'
                assert abs(dl['waypoints'][1]['loiter_param'] - 15) < 0.1
            finally:
                await ws.send(json.dumps({'type': 'disconnect'}))
                await asyncio.sleep(0.5)
                await ws.close()
        asyncio.get_event_loop().run_until_complete(run())
