"""What an AI assistant asked the operator's page, and what the operator decided.

One JSON object per line in `logs/assistant_audit.jsonl`. `backend/ws_manager.py` writes it
where a request and its answer meet, which is the only place that sees both. Positions and
parameter values are in it, as they are in the tlogs; the token and the headers are not.

A failure to write is logged and swallowed: the approval gate must not depend on a file.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import cfg

logger = logging.getLogger(__name__)

# Larger than this and the file moves aside once, on the next write: logs/assistant_audit.jsonl.1
MAX_FILE_BYTES = 5 * 1024 * 1024
# A 500-waypoint proposal at full float precision is about 70 KB, and is kept whole.
MAX_LINE_BYTES = 256 * 1024
_LOCK = threading.Lock()


def log_path() -> Path:
    return cfg.LOG_DIR / "assistant_audit.jsonl"


def _line(entry: dict) -> str:
    return json.dumps(entry, ensure_ascii=False, separators=(",", ":"), default=str)


def _bounded(entry: dict) -> str:
    """A line within MAX_LINE_BYTES. The body goes first; the identity of the entry stays."""
    line = _line(entry)
    if len(line.encode("utf-8")) <= MAX_LINE_BYTES:
        return line
    entry = {k: v for k, v in entry.items() if k not in ("args", "result", "truncated")}
    entry["truncated"] = True
    line = _line(entry)
    if len(line.encode("utf-8")) <= MAX_LINE_BYTES:
        return line
    entry.pop("error", None)
    line = _line(entry)
    if len(line.encode("utf-8")) <= MAX_LINE_BYTES:
        return line
    # Fields this module and the manager set themselves: short, and enough to find the entry.
    entry = {k: entry[k] for k in ("time", "event", "id", "kind", "truncated") if k in entry}
    entry["kind"] = str(entry.get("kind", ""))[:100]
    return _line(entry)


def record(event: str, **fields: Any) -> None:
    """Append one event. Never raises."""
    try:
        entry: dict[str, Any] = {
            "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "event": event,
        }
        entry.update(fields)
        line = _bounded(entry)
        with _LOCK:
            target = log_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                if target.stat().st_size > MAX_FILE_BYTES:
                    target.replace(target.with_name(target.name + ".1"))
            except FileNotFoundError:
                pass
            with target.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:
        logger.warning("assistant audit: could not write %r", event, exc_info=True)
