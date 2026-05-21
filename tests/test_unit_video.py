"""Unit tests for video module."""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.video import _proc_lock, _ffmpeg_available


class TestVideoModule:
    def test_proc_lock_exists(self):
        assert isinstance(_proc_lock, type(threading.Lock()))

    def test_ffmpeg_check(self):
        result = _ffmpeg_available()
        assert isinstance(result, bool)
