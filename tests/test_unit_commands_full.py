"""Full coverage for backend/commands.py — remaining 12+ command branches."""
import base64
from unittest.mock import MagicMock

from backend.commands import execute
from backend.drone_link import DroneLink


def make_link():
    link = DroneLink()
    link._ser = MagicMock()
    link.connected = True
    link.vehicle.sysid = 1
    return link


class TestReboot:
    def test_reboot(self):
        link = make_link()
        execute('reboot', None, link)
        assert any('重启飞控' in e['text'] for e in link.events)
        assert link._ser.write.called

    def test_reboot_bootloader(self):
        link = make_link()
        execute('reboot_bootloader', None, link)
        assert any('引导程序' in e['text'] for e in link.events)


class TestMotorTest:
    def test_motor_test(self):
        link = make_link()
        execute('motor_test', None, link, data={'motor': 0, 'throttle': 10, 'duration': 2})
        assert any('电机测试' in e['text'] for e in link.events)
        assert link._ser.write.called

    def test_motor_test_stop(self):
        link = make_link()
        execute('motor_test_stop', None, link)
        assert link._ser.write.call_count >= 8


class TestGimbal:
    def test_gimbal_angle(self):
        link = make_link()
        execute('gimbal_angle', None, link, data={'pitch': -30, 'yaw': 90})
        assert link._ser.write.called

    def test_gimbal_rate(self):
        link = make_link()
        execute('gimbal_rate', None, link, data={'pitch_rate': 10, 'yaw_rate': 5})
        assert link._ser.write.called


class TestCamera:
    def test_camera_trigger(self):
        link = make_link()
        execute('camera_trigger', None, link)
        assert link._ser.write.called

    def test_camera_video_start(self):
        link = make_link()
        execute('camera_video_start', None, link)
        assert link._ser.write.called

    def test_camera_video_stop(self):
        link = make_link()
        execute('camera_video_stop', None, link)
        assert link._ser.write.called

    def test_camera_zoom(self):
        link = make_link()
        execute('camera_zoom', None, link, data={'zoom': 2.5})
        assert link._ser.write.called


class TestSwitchVehicle:
    def test_switch_vehicle(self):
        link = make_link()
        execute('switch_vehicle', None, link, data={'sysid': 3})
        assert link.active_sysid == 3
        assert link.vehicle.sysid == 3
        assert any('sysid=3' in e['text'] for e in link.events)


class TestInjectRtcm:
    def test_inject_rtcm(self):
        link = make_link()
        raw_data = b'\x01\x02\x03\x04\x05'
        b64 = base64.b64encode(raw_data).decode()
        execute('inject_rtcm', None, link, data={'data': b64})
        assert link._ser.write.called

    def test_inject_rtcm_large(self):
        link = make_link()
        raw_data = b'\xAA' * 250
        b64 = base64.b64encode(raw_data).decode()
        execute('inject_rtcm', None, link, data={'data': b64})
        assert link._ser.write.call_count >= 3  # 250/110 = 3 chunks

    def test_inject_rtcm_empty(self):
        link = make_link()
        execute('inject_rtcm', None, link, data={'data': ''})
        assert not link._ser.write.called


class TestRallyUpload:
    def test_rally_upload(self):
        link = make_link()
        points = [
            {'lat': 30.0, 'lon': 120.0, 'alt': 100},
            {'lat': 30.1, 'lon': 120.1, 'alt': 100},
        ]
        execute('rally_upload', None, link, data={'points': points})
        assert any('备降点' in e['text'] for e in link.events)

    def test_rally_upload_empty(self):
        link = make_link()
        execute('rally_upload', None, link, data={'points': []})
        assert not any('备降' in e['text'] for e in link.events)


class TestSerialControl:
    def test_serial_control(self):
        link = make_link()
        execute('serial_control', None, link, data={'text': 'help\n'})
        assert link._ser.write.called

    def test_serial_control_empty(self):
        link = make_link()
        execute('serial_control', None, link, data={'text': ''})
        assert not link._ser.write.called


class TestDoSetRoi:
    def test_do_set_roi(self):
        link = make_link()
        execute('do_set_roi', None, link, data={'lat': 30.5, 'lon': 120.3, 'alt': 100})
        assert link._ser.write.called


class TestInspectorToggle:
    def test_toggle_on(self):
        link = make_link()
        assert link.inspector_enabled is False
        execute('inspector_toggle', None, link)
        assert link.inspector_enabled is True

    def test_toggle_off(self):
        link = make_link()
        link.inspector_enabled = True
        execute('inspector_toggle', None, link)
        assert link.inspector_enabled is False


class TestLogCancel:
    def test_log_cancel_resets(self):
        link = make_link()
        link.log_dl._log_download_id = 5
        execute('log_cancel', None, link)
        assert link.log_dl._log_download_id == -1
