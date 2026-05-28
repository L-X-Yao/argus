"""Tests for backend/locale_text.py — bilingual event text lookup."""

from backend.locale_text import _T, lt


class TestLt:
    def test_default_returns_chinese(self):
        assert lt("connected") == "已连接 (sysid=%d)"

    def test_english_locale(self):
        assert lt("connected", "en") == "Connected (sysid=%d)"

    def test_unknown_key_returns_key(self):
        assert lt("nonexistent_key_xyz") == "nonexistent_key_xyz"

    def test_unknown_key_with_en(self):
        assert lt("nonexistent_key_xyz", "en") == "nonexistent_key_xyz"


class TestTextTable:
    def test_all_entries_are_pairs(self):
        for key, pair in _T.items():
            assert isinstance(pair, tuple), f"{key}: expected tuple, got {type(pair)}"
            assert len(pair) == 2, f"{key}: expected 2-tuple, got {len(pair)}-tuple"

    def test_all_values_are_strings(self):
        for key, (zh, en) in _T.items():
            assert isinstance(zh, str), f"{key} zh: not a string"
            assert isinstance(en, str), f"{key} en: not a string"

    def test_no_empty_values(self):
        for key, (zh, en) in _T.items():
            assert len(zh) > 0, f"{key} zh: empty"
            assert len(en) > 0, f"{key} en: empty"

    def test_key_count(self):
        assert len(_T) >= 50


class TestSyncLocalesEscaping:
    """Tests for the _escape_ts helper in scripts/sync_locales.py."""

    def test_apostrophe_escaped(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from sync_locales import _escape_ts
        assert _escape_ts("it's here") == r"it\'s here"

    def test_backslash_escaped(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from sync_locales import _escape_ts
        assert _escape_ts("path\\to\\file") == r"path\\to\\file"

    def test_plain_string_unchanged(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from sync_locales import _escape_ts
        assert _escape_ts("Hello World") == "Hello World"
