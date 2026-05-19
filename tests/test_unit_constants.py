"""Unit tests: constants — no English leaks in mode names/buttons."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.constants import COPTER_MODES, PLANE_MODES, COPTER_BTNS, PLANE_BTNS, FIX_NAMES


def _has_english(text):
    return any('a' <= c <= 'z' or 'A' <= c <= 'Z' for c in text)


class TestModeNames:
    def test_copter_modes_chinese(self):
        for mid, name in COPTER_MODES.items():
            assert not _has_english(name), f'COPTER mode {mid} has English: {name}'

    def test_plane_modes_chinese(self):
        for mid, name in PLANE_MODES.items():
            clean = name.replace('A', '').replace('B', '')
            assert not _has_english(clean), f'PLANE mode {mid} has English: {name}'

    def test_fix_names_chinese(self):
        for fix, name in FIX_NAMES.items():
            english_only = all('a' <= c <= 'z' or 'A' <= c <= 'Z' or c.isdigit() for c in name.replace(' ', ''))
            if english_only and name not in ('2D', '3D', 'RTK'):
                assert False, f'FIX {fix} may leak: {name}'


class TestButtons:
    def test_copter_buttons_chinese(self):
        for mid, name in COPTER_BTNS:
            assert not _has_english(name), f'COPTER button {mid} has English: {name}'
            assert mid in COPTER_MODES, f'COPTER button {mid} not in COPTER_MODES'

    def test_plane_buttons_chinese(self):
        for mid, name in PLANE_BTNS:
            assert not _has_english(name), f'PLANE button {mid} has English: {name}'
            assert mid in PLANE_MODES, f'PLANE button {mid} not in PLANE_MODES'


class TestCompleteness:
    def test_copter_has_common_modes(self):
        assert 0 in COPTER_MODES  # Stabilize
        assert 5 in COPTER_MODES  # Loiter
        assert 6 in COPTER_MODES  # RTL
        assert 3 in COPTER_MODES  # Auto

    def test_plane_has_common_modes(self):
        assert 10 in PLANE_MODES  # Auto
        assert 11 in PLANE_MODES  # RTL
        assert 19 in PLANE_MODES  # QLoiter
        assert 21 in PLANE_MODES  # QRTL
