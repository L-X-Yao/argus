"""backend/assistant_audit.py: one JSON line per event, its size limits, and no failure."""

import json
from unittest import mock

from backend import assistant_audit
from backend.config import cfg


def entries(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_one_line_per_event_with_the_fields_as_given(tmp_path):
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        assistant_audit.record("asked", id="a-1", client={"name": "t"}, kind="propose_mission", args={"n": 1})
        assistant_audit.record("answered", id="a-1", ok=True)
    lines = entries(tmp_path / "assistant_audit.jsonl")
    assert [e["event"] for e in lines] == ["asked", "answered"]
    assert lines[0]["id"] == "a-1" and lines[0]["args"] == {"n": 1}
    assert lines[0]["client"] == {"name": "t"}
    assert lines[1]["ok"] is True
    assert all("time" in e for e in lines)


def test_a_body_past_the_line_limit_keeps_the_entry_and_drops_the_body(tmp_path):
    with mock.patch.object(cfg, "LOG_DIR", tmp_path), mock.patch.object(assistant_audit, "MAX_LINE_BYTES", 200):
        assistant_audit.record("asked", id="a-1", kind="propose_mission", args={"waypoints": ["x" * 500]})
    entry = entries(tmp_path / "assistant_audit.jsonl")[0]
    assert entry["truncated"] is True
    assert "args" not in entry and entry["id"] == "a-1"


def test_a_field_the_caller_controls_cannot_make_a_line_past_the_limit(tmp_path):
    with mock.patch.object(cfg, "LOG_DIR", tmp_path), mock.patch.object(assistant_audit, "MAX_LINE_BYTES", 500):
        assistant_audit.record("asked", id="a-1", kind="k" * 2000)
    raw = (tmp_path / "assistant_audit.jsonl").read_text()
    assert len(raw.encode("utf-8")) < 1000
    entry = json.loads(raw)
    assert entry["truncated"] is True and entry["kind"] == "k" * 100


def test_the_file_moves_aside_at_the_size_limit(tmp_path):
    with mock.patch.object(cfg, "LOG_DIR", tmp_path), mock.patch.object(assistant_audit, "MAX_FILE_BYTES", 10):
        assistant_audit.record("first")
        assistant_audit.record("second")
    assert (tmp_path / "assistant_audit.jsonl.1").exists()
    assert [e["event"] for e in entries(tmp_path / "assistant_audit.jsonl")] == ["second"]


def test_a_write_that_fails_is_only_logged(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    with mock.patch.object(cfg, "LOG_DIR", blocker):
        assistant_audit.record("asked", id="a-1")  # must not raise: the gate does not depend on it
